from datetime import datetime, timezone

from app.services.ai_engine import _local_reasoning, _sanitize_output, build_deepseek_request_payload, normalize_ai_output


def test_ai_output_sanitizes_forbidden_phrases():
    output = _sanitize_output(
        {
            "recommendation": "立即买入",
            "conclusion": "必涨且稳赚",
            "reasons": ["可以满仓"],
            "risks": ["不要立即卖出"],
            "invalid_conditions": [],
            "missing_data": [],
        }
    )

    text = str(output)
    for phrase in ["立即买入", "立即卖出", "必涨", "稳赚", "满仓"]:
        assert phrase not in text


def test_local_reasoning_ignores_freshness_and_analyzes_snapshot():
    output = _local_reasoning(
        {
            "position": {
                "code": "US.AAPL",
                "position_layer": "中期配置仓",
                "position_weight": 0.12,
                "profit_loss_ratio": 0.03,
            },
            "freshness": {
                "position": {
                    "data_type": "position",
                    "status": "stale",
                    "age_seconds": 999999,
                    "valid_seconds": 900,
                    "message": "持仓过期",
                    "stale_action": "刷新",
                },
                "decision_card": {
                    "data_type": "decision_card",
                    "status": "fresh",
                    "age_seconds": 10,
                    "valid_seconds": 300,
                    "message": "有效",
                    "stale_action": "继续使用",
                },
            },
            "data_version": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        }
    )

    assert output["recommendation"] == "继续持有"
    assert output["missing_data"] == []
    text = str(output)
    assert "过期" not in text
    assert "数据新鲜度" not in text


def test_external_prompt_enforces_snapshot_only_policy_over_saved_legacy_prompt():
    payload = build_deepseek_request_payload(
        {
            "data_version": "20260712163205",
            "freshness": {"position": {"status": "stale", "age_seconds": 37606}},
            "position": {"code": "US.AAPL", "snapshot_time": "2026-07-12T16:32:05"},
        },
        "deepseek-chat",
        "数据过期时必须降级为信息不足。",
    )

    system_prompt = payload["messages"][0]["content"]
    assert "只基于当前持仓快照中的价格" in system_prompt
    assert "过期" not in system_prompt
    user_prompt = payload["messages"][1]["content"]
    assert "freshness" not in user_prompt
    assert "snapshot_time" not in user_prompt
    assert "data_version" not in user_prompt


def test_ai_output_normalizes_object_recommendation_and_non_array_checklists():
    output = normalize_ai_output(
        {
            "recommendation": {
                "mid_term": "不适用（无中期仓）",
                "core_long": "持有并等待，观察关键支撑位",
            },
            "conclusion": "继续跟踪",
            "reasons": "核心长期仓",
            "risks": {"market": "市场波动"},
        }
    )

    assert output["recommendation"] == "持有并等待，观察关键支撑位"
    assert output["reasons"] == ["核心长期仓"]
    assert output["risks"] == ["市场波动"]
    assert output["invalid_conditions"] == []
