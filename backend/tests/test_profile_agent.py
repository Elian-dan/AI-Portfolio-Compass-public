from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AIWorkflowRun, AccountSnapshot, KlineSnapshot, PositionSnapshot, QuoteSummary
from app.services import profile_agent_tools
from app.services.profile_agent import _next_action, _stream_chaptered_deepseek_report, stream_agent_workflow
from app.services.profile_agent_tools import SKILL_FILES, annotate_model_derived_percentages, default_tool_registry, validate_report


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _account(account_id: str, total_assets: float, cash: float, market_value: float, currency: str) -> AccountSnapshot:
    return AccountSnapshot(
        account_id=account_id,
        total_assets=total_assets,
        cash=cash,
        market_value=market_value,
        raw_currency_values={"currency": currency},
        snapshot_time=datetime.now(timezone.utc),
        sync_id="sync",
    )


def _position(account_id: str, code: str, value: float, currency: str, account_weight: float) -> PositionSnapshot:
    return PositionSnapshot(
        account_id=account_id,
        code=code,
        name=code,
        market=code.split(".")[0],
        asset_type="stock",
        quantity=1,
        average_cost=100,
        current_price=100,
        raw_market_value=value,
        raw_currency=currency,
        normalized_market_value=value,
        normalized_currency=currency,
        exchange_rate_to_base=1,
        position_weight=account_weight,
        profit_loss_ratio=0.01,
        position_layer="核心长期仓",
        layer_source="test",
        layer_confidence="高",
        layer_reason="test",
        snapshot_time=datetime.now(timezone.utc),
        sync_id="sync",
    )


def test_skill_files_are_registered_and_readable():
    registry = default_tool_registry()
    assert "read_skill_doc" in registry.names()
    assert set(SKILL_FILES) == {"customer_profile", "portfolio_diagnosis", "asset_allocation"}

    db = _session()
    state = {"workflow_type": "portfolio_diagnosis"}
    result = registry.run(db, "all", "read_skill_doc", {"workflow_type": "portfolio_diagnosis"}, state)

    assert result["status"] == "ok"
    assert "position_exposures.weight" in result["content"]


def test_skill_files_contain_institutional_report_constraints():
    skill_dir = SKILL_FILES
    registry = default_tool_registry()
    db = _session()

    for workflow_type in skill_dir:
        state = {"workflow_type": workflow_type}
        result = registry.run(db, "all", "read_skill_doc", {"workflow_type": workflow_type}, state)
        content = result["content"]
        for heading in ("角色与边界", "工具调用顺序", "核心计算口径", "报告写作协议", "逐章节写作模板", "缺失数据降级规则", "质量校验清单", "禁止事项"):
            assert heading in content
        assert "validate_report" in content
        assert "非云端自主 Agent" in content
        assert "事实" in content
        assert "Agent 判断" in content
        assert "建议关注" in content


def test_customer_profile_skill_requires_stated_vs_revealed_risk():
    registry = default_tool_registry()
    result = registry.run(_session(), "all", "read_skill_doc", {"workflow_type": "customer_profile"}, {"workflow_type": "customer_profile"})
    content = result["content"]

    assert "stated risk" in content
    assert "revealed risk" in content
    assert "主观风险偏好数据不足" in content
    assert "画像缺口" in content
    assert "年龄区间" in content
    assert "流动性需求" in content


def test_portfolio_diagnosis_skill_locks_weight_and_attribution_basis():
    registry = default_tool_registry()
    result = registry.run(_session(), "all", "read_skill_doc", {"workflow_type": "portfolio_diagnosis"}, {"workflow_type": "portfolio_diagnosis"})
    content = result["content"]

    assert "明确禁止相加 `account_weight`" in content
    assert "收益贡献必须使用 `weight × profit_loss_ratio`" in content
    assert "未取得 K线，技术判断降级" in content
    assert "风险雷达" in content
    assert "集中度、波动、流动性、货币、主题、数据缺失" in content


def test_asset_allocation_skill_requires_target_table_and_rebalance_rules():
    registry = default_tool_registry()
    result = registry.run(_session(), "all", "read_skill_doc", {"workflow_type": "asset_allocation"}, {"workflow_type": "asset_allocation"})
    content = result["content"]

    assert "当前比例 / 目标比例 / 偏离 / 金额 / 参考标的" in content
    assert "| 资产类别 | 目标比例 | 当前比例 | 偏离 | 估算金额 | 参考标的 | 理由 |" in content
    assert "任一资产类别偏离目标比例 5% 以上时复核" in content
    assert "乐观" in content
    assert "中性" in content
    assert "压力" in content


def test_tool_registry_rejects_unknown_tool():
    registry = default_tool_registry()
    result = registry.run(_session(), "all", "place_order", {}, {})

    assert result["status"] == "error"
    assert "place_order" in result["error"]


def test_get_latest_quotes_uses_local_snapshot_and_marks_unsupported():
    db = _session()
    db.add(
        QuoteSummary(
            code="US.QQQ",
            current_price=100,
            change_ratio=0,
            volume=1,
            ma_summary={},
            support_price=None,
            resistance_price=None,
            quote_time=datetime(2026, 7, 4, tzinfo=timezone.utc),
            sync_id="old",
        )
    )
    db.commit()

    result = default_tool_registry().run(db, "all", "get_latest_quotes", {"codes": ["US.QQQ", "FUND.006479"]}, {})

    assert result["status"] == "ok"
    assert result["items"][0]["current_price"] == 100
    assert result["items"][0]["source"] == "local_cache"
    assert result["unsupported_codes"] == ["FUND.006479"]


def test_audit_pack_carries_quote_and_kline_observations():
    db = _session()
    state = {
        "workflow_type": "portfolio_diagnosis",
        "context": {
            "data_version": "test",
            "generated_at": "now",
            "portfolio": {"weight_basis": "CNY total_assets", "cash_ratio": 0.1, "total_assets": 1000, "market_value": 900, "cash": 100, "base_currency": "CNY"},
            "positions": [],
            "position_exposures": [{"code": "US.QQQ", "weight": 0.5, "profit_loss_ratio": 0.02, "market_value": 500, "account_positions": []}],
            "news": [],
        },
        "artifacts": [{"artifact_id": "asset_allocation", "title": "资产类型分布", "data": [{"label": "股票", "value": 0.9}, {"label": "现金", "value": 0.1}]}],
        "tool_trace": [
            {
                "tool_name": "get_latest_quotes",
                "observation": {
                    "status": "ok",
                    "items": [{"code": "US.QQQ", "current_price": 123.45, "change_ratio": 0.01}],
                    "missing_codes": [],
                    "unsupported_codes": ["FUND.006479"],
                },
            },
            {
                "tool_name": "get_kline_summary",
                "observation": {
                    "status": "ok",
                    "items": {"US.QQQ": {"daily": {"status": "available", "trend_summary": "价格位于主要均线之上"}}},
                    "unsupported_codes": [],
                },
            },
        ],
    }

    result = default_tool_registry().run(db, "all", "calculate_audit_pack", {}, state)
    pack = result["calculation_audit_pack"]

    assert pack["latest_quotes"][0]["current_price"] == 123.45
    assert pack["kline_summary"]["US.QQQ"]["daily"]["status"] == "available"
    assert pack["data_quality"]["kline_status"] == "ok"


def test_audit_pack_tools_are_registered_and_validate_report_blocks_unknown_percent():
    registry = default_tool_registry()
    assert "calculate_audit_pack" in registry.names()
    assert "audit_calculation_pack" in registry.names()
    state = {
        "calculation_audit_pack": {
            "portfolio": {"weight_basis": "CNY total_assets", "cash_ratio": 0.1},
            "largest_exposure": {"code": "US.QQQ", "weight": 0.5},
            "top5_weights": [{"code": "US.QQQ", "weight": 0.5}],
            "top5_weight_total": 0.5,
            "merged_exposures": [{"code": "US.QQQ", "weight": 0.5, "profit_loss_ratio": 0.02, "change_ratio": 0}],
            "return_contribution_rank": [{"label": "US.QQQ", "value": 0.01}],
            "distribution_checks": [{"artifact_id": "asset_allocation", "total": 1}],
            "artifacts": [{"artifact_id": "asset_allocation", "data": [{"label": "股票", "value": 0.5}, {"label": "现金", "value": 0.5}]}],
        },
        "context": {"portfolio": {"weight_basis": "CNY total_assets"}},
        "artifacts": [{"artifact_id": "asset_allocation", "title": "资产类型分布", "data": [{"label": "股票", "value": 0.5}, {"label": "现金", "value": 0.5}]}],
        "tool_trace": [],
    }

    result = validate_report("权重口径 CNY total_assets。组合事实：US.QQQ 50.0%，另有未知数字 37.0%。", state)

    assert result["status"] == "failed"
    assert "37.0%" in result["issues"][0]


def test_validate_report_allows_auditable_derived_percentages():
    state = {
        "calculation_audit_pack": {
            "portfolio": {"weight_basis": "CNY total_assets", "cash_ratio": 0.1},
            "largest_exposure": {"code": "US.QQQ", "weight": 0.2115},
            "top5_weights": [{"code": "US.QQQ", "weight": 0.2115}],
            "merged_exposures": [
                {"code": "US.QQQ", "weight": 0.2115, "profit_loss_ratio": 0.0241, "change_ratio": 0},
                {"code": "US.NVDA", "weight": 0.1835, "profit_loss_ratio": -0.0061, "change_ratio": 0},
                {"code": "SPCX", "weight": 0.5213, "profit_loss_ratio": -0.1436, "change_ratio": 0},
            ],
            "return_contribution_rank": [{"label": "US.QQQ", "value": 0.0051}],
            "distribution_checks": [],
            "artifacts": [],
        },
        "context": {"portfolio": {"weight_basis": "CNY total_assets"}},
        "artifacts": [],
        "tool_trace": [],
    }

    result = validate_report(
        "权重口径 CNY total_assets。QQQ 与 NVDA 合计 39.50%。前三大合计 91.63%，剩余 8.37%。SPCX 盈亏率 -14.36%。",
        state,
    )

    assert result["status"] == "ok"


def test_annotate_model_derived_percentages_marks_unsourced_values():
    state = {
        "calculation_audit_pack": {
            "portfolio": {"weight_basis": "CNY total_assets", "cash_ratio": 0.1},
            "largest_exposure": {"code": "US.QQQ", "weight": 0.2115},
            "top5_weights": [{"code": "US.QQQ", "weight": 0.2115}],
            "merged_exposures": [{"code": "US.QQQ", "weight": 0.2115, "profit_loss_ratio": 0.0241, "change_ratio": 0}],
            "return_contribution_rank": [],
            "distribution_checks": [],
            "artifacts": [],
        },
        "context": {"portfolio": {"weight_basis": "CNY total_assets"}},
        "artifacts": [],
        "tool_trace": [],
    }

    markdown = annotate_model_derived_percentages("权重口径 CNY total_assets。QQQ 权重 21.15%，模型建议区间 37.0%。", state)

    assert "21.15%（数据来源为模型推荐）" not in markdown
    assert "37.0%（数据来源为模型推荐）" in markdown
    assert validate_report(markdown, state)["status"] == "ok"


def test_validation_issues_are_quality_result_not_generation_failure():
    import app.services.profile_agent as profile_agent

    result = profile_agent._quality_result({"status": "failed", "issues": ["报告缺少权重口径说明"]})

    assert result == {"status": "needs_review", "issues": ["报告缺少权重口径说明"]}


def test_json_safe_converts_datetime_before_json_column_save():
    import app.services.profile_agent as profile_agent

    now = datetime(2026, 7, 8, 15, 25, tzinfo=timezone.utc)
    result = profile_agent._json_safe({"output": {"snapshot_time": now, "items": [now]}})

    assert result == {"output": {"snapshot_time": "2026-07-08T15:25:00+00:00", "items": ["2026-07-08T15:25:00+00:00"]}}


def test_save_sanitizes_workflow_json_columns():
    import app.services.profile_agent as profile_agent

    db = _session()
    now = datetime(2026, 7, 8, 15, 27, tzinfo=timezone.utc)
    run = AIWorkflowRun(
        run_id="wf_json_safe",
        workflow_type="portfolio_diagnosis",
        account_id="all",
        question="测试 JSON 清洗",
        status="failed",
        steps=[{"at": now}],
        input_context={"snapshot_time": now},
        output={"calculation_audit_pack": {"snapshot_time": now}},
        artifacts=[{"data": [{"time": now}]}],
        provider="deepseek",
        model="deepseek-v4-pro",
        data_version="",
        error_message="",
        created_at=now,
        updated_at=now,
    )

    profile_agent._save(db, run)
    db.refresh(run)

    assert run.steps[0]["at"] == "2026-07-08T15:27:00+00:00"
    assert run.input_context["snapshot_time"] == "2026-07-08T15:27:00+00:00"
    assert run.output["calculation_audit_pack"]["snapshot_time"] == "2026-07-08T15:27:00+00:00"
    assert run.artifacts[0]["data"][0]["time"] == "2026-07-08T15:27:00+00:00"


def test_chapter_timeout_fails_report_without_local_fallback(monkeypatch):
    import app.services.profile_agent as profile_agent

    def fake_chapter(_settings, _run, _state, _context, _artifacts, _index, title, _brief):
        if title == "三、集中度与重叠风险":
            raise TimeoutError("chapter timeout")
        yield f"\n\n## {title}\n\nDeepSeek 段落。\n"

    monkeypatch.setattr(profile_agent, "_stream_deepseek_chapter", fake_chapter)
    run = AIWorkflowRun(
        run_id="wf_chapter",
        workflow_type="portfolio_diagnosis",
        account_id="all",
        question="测试章节",
        status="running",
        steps=[],
        input_context={},
        output={},
        artifacts=[],
        provider="deepseek",
        model="deepseek-v4-pro",
        data_version="",
        error_message="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    context = {
        "data_version": "test",
        "generated_at": "now",
        "portfolio": {"weight_basis": "CNY total_assets", "cash_ratio": 0.1, "total_assets": 1000, "market_value": 900, "cash": 100, "base_currency": "CNY"},
        "positions": [],
        "position_exposures": [{"code": "US.QQQ", "weight": 0.5, "profit_loss_ratio": 0.02, "asset_type": "fund", "source_currency": "USD", "account_positions": []}],
        "news": [],
    }
    artifacts = [{"artifact_id": "asset_allocation", "title": "资产类型分布", "data": [{"label": "基金/ETF", "value": 0.5}, {"label": "现金", "value": 0.1}]}]
    state = {"tool_trace": [], "calculation_audit_pack": profile_agent.build_calculation_audit_pack(context, artifacts)}

    events = []
    with pytest.raises(RuntimeError, match="集中度与重叠风险"):
        for event in _stream_chaptered_deepseek_report(object(), run, state, context, artifacts):
            events.append(event)
    deltas = "".join(str(event["payload"].get("delta") or "") for event in events if event["event"] == "content_delta")

    assert "本地模板降级段落" not in deltas
    assert any(item["chapter"] == "三、集中度与重叠风险" and item["status"] == "failed" for item in state["chapter_statuses"])


def test_unplanned_agent_planning_uses_its_own_configured_model(monkeypatch):
    import app.services.profile_agent as profile_agent

    captured = {}

    def fake_call(payload, _api_key, _base_url, timeout=20):
        captured["model"] = payload["model"]
        captured["timeout"] = timeout
        return {
            "thought_summary": "使用快模型决定下一步。",
            "tool_name": "read_skill_doc",
            "tool_args": {"workflow_type": "portfolio_diagnosis"},
            "why": "确认报告约束。",
            "expected_observation": "技能文档摘要。",
        }

    monkeypatch.setattr(profile_agent, "call_llm_payload", fake_call)

    class Settings:
        deepseek_api_key = "key"
        deepseek_base_url = "https://example.test"
        deepseek_model = "deepseek-v4-pro"
        deepseek_agent_model = "deepseek-v4-flash"

    run = AIWorkflowRun(
        run_id="wf_unplanned_planning_model",
        workflow_type="ad_hoc_research",
        account_id="all",
        question="测试前置决策模型",
        status="running",
        steps=[],
        input_context={},
        output={"planning_model": "deepseek-v4-flash"},
        artifacts=[],
        provider="deepseek",
        model="deepseek-v4-pro",
        data_version="",
        error_message="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    state = {}

    action = _next_action(Settings(), run, default_tool_registry(), state, True, 1)

    assert action["tool_name"] == "read_skill_doc"
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["timeout"] == 30
    assert state["planning_model"] == "deepseek-v4-flash"
    assert run.model == "deepseek-v4-pro"


def test_customer_profile_uses_planned_sequence_without_cloud_planning(monkeypatch):
    import app.services.profile_agent as profile_agent

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("customer_profile should use the deterministic tool plan")

    monkeypatch.setattr(profile_agent, "call_llm_payload", fail_if_called)

    class Settings:
        deepseek_api_key = "key"
        deepseek_base_url = "https://example.test"
        deepseek_model = "deepseek-v4-pro"
        deepseek_agent_model = "deepseek-v4-flash"

    run = AIWorkflowRun(
        run_id="wf_customer_profile_plan",
        workflow_type="customer_profile",
        account_id="all",
        question="测试客户画像规划",
        status="running",
        steps=[],
        input_context={},
        output={},
        artifacts=[],
        provider="deepseek",
        model="deepseek-v4-pro",
        data_version="",
        error_message="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    state = {}

    planned_tools = [
        _next_action(Settings(), run, default_tool_registry(), state, True, turn)["tool_name"]
        for turn in range(1, 11)
    ]

    assert planned_tools == [
        "read_skill_doc",
        "get_portfolio_context",
        "get_investor_preferences",
        "get_position_exposures",
        "calculate_allocation_distribution",
        "get_deals_summary",
        "calculate_audit_pack",
        "audit_calculation_pack",
        "create_chart_artifact",
        "finalize_report",
    ]


def test_running_workflow_with_finalize_trace_resumes_report_instead_of_failing_max_turns(monkeypatch):
    import app.services.profile_agent as profile_agent

    db = _session()
    db.add(_account("all", 10000, 1000, 9000, "CNY"))
    db.add(_position("all", "US.QQQ", 9000, "CNY", 0.9))
    run = AIWorkflowRun(
        run_id="wf_resume_after_finalize",
        workflow_type="customer_profile",
        account_id="all",
        question="测试恢复",
        status="running",
        steps=[],
        input_context={},
        output={
            "tool_trace": [
                {"turn": 10, "tool_name": "finalize_report", "observation": {"status": "ok"}},
                {"turn": 11, "tool_name": "get_latest_quotes", "observation": {"status": "ok"}},
                {"turn": 12, "tool_name": "get_kline_summary", "observation": {"status": "ok"}},
                {"turn": 13, "tool_name": "calculate_audit_pack", "observation": {"status": "ok"}},
                {"turn": 14, "tool_name": "audit_calculation_pack", "observation": {"status": "ok"}},
                {"turn": 15, "tool_name": "create_chart_artifact", "observation": {"status": "ok"}},
            ],
            "calculation_audit_pack": {
                "portfolio": {"weight_basis": "CNY total_assets", "cash_ratio": 0.1},
                "merged_exposures": [{"code": "US.QQQ", "weight": 0.9, "profit_loss_ratio": 0.01, "change_ratio": 0}],
                "return_contribution_rank": [],
                "distribution_checks": [],
                "artifacts": [],
            },
        },
        artifacts=[],
        provider="deepseek",
        model="deepseek-v4-pro",
        data_version="",
        error_message="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()

    class LocalSession:
        def __enter__(self):
            return db

        def __exit__(self, *_args):
            return False

    class Settings:
        deepseek_api_key = "key"

    def fake_report(_settings, _run, _state, _context, _artifacts):
        yield {
            "event": "content_delta",
            "payload": {
                "run_id": "wf_resume_after_finalize",
                "delta": "## 一、客户摘要\n\n### 事实数据\n权重口径 CNY total_assets，行情数据不足。\n\n### Agent 判断\n客户画像恢复生成。\n\n### 建议关注\n补充缺失数据。\n\n---\n",
            },
        }

    monkeypatch.setattr(profile_agent, "SessionLocal", lambda: LocalSession())
    monkeypatch.setattr(profile_agent, "get_settings", lambda: Settings())
    monkeypatch.setattr(profile_agent, "_stream_chaptered_deepseek_report", fake_report)

    body = "".join(stream_agent_workflow("wf_resume_after_finalize"))
    db.refresh(run)

    assert "达到最大工具调用轮数" not in body
    assert "event: run_completed" in body
    assert run.status == "completed"


def test_agent_stream_without_deepseek_fails_without_report(monkeypatch):
    import app.services.profile_agent as profile_agent

    db = _session()
    db.add_all(
        [
            _account("hk", 10000, 1000, 9000, "HKD"),
            _account("usd", 100, 20, 80, "USD"),
            _position("hk", "US.QQQ", 8000, "HKD", 0.8),
            _position("usd", "US.NVDA", 80, "USD", 0.8),
        ]
    )
    run = AIWorkflowRun(
        run_id="wf_test_agent",
        workflow_type="portfolio_diagnosis",
        account_id="all",
        question="测试持仓诊断",
        status="pending",
        steps=[],
        input_context={},
        output={"use_external_model": False},
        artifacts=[],
        provider="local",
        model="local_workflow",
        data_version="",
        error_message="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()

    class LocalSession:
        def __enter__(self):
            return db

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(profile_agent, "SessionLocal", lambda: LocalSession())

    body = "".join(stream_agent_workflow("wf_test_agent"))

    assert "event: agent_warning" in body
    assert "event: run_failed" in body
    assert "没有大模型参与时不生成投顾报告" in body
    assert "event: content_delta" not in body
    assert "event: run_completed" not in body


def test_agent_stream_failed_run_emits_failure_without_restart(monkeypatch):
    import app.services.profile_agent as profile_agent

    db = _session()
    run = AIWorkflowRun(
        run_id="wf_test_failed_agent",
        workflow_type="portfolio_diagnosis",
        account_id="all",
        question="测试失败任务",
        status="failed",
        steps=[{"step_no": 1, "title": "调用工具：read_skill_doc", "status": "completed"}],
        input_context={},
        output={},
        artifacts=[],
        provider="deepseek",
        model="deepseek-v4-pro",
        data_version="",
        error_message="The read operation timed out",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()

    class LocalSession:
        def __enter__(self):
            return db

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(profile_agent, "SessionLocal", lambda: LocalSession())

    body = "".join(stream_agent_workflow("wf_test_failed_agent"))
    db.refresh(run)

    assert "event: run_failed" in body
    assert "The read operation timed out" in body
    assert run.status == "failed"
