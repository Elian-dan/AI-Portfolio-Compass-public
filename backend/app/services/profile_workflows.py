from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import re
import time
from typing import Any, Iterable, Optional
from urllib.parse import quote
from urllib import request
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    AIWorkflowRun,
    AccountSnapshot,
    Deal,
    InvestorPreference,
    NewsItem,
    PositionSnapshot,
    ProfileVersion,
    QuoteSummary,
    WatchlistItem,
)
from app.services.sync import latest_account_snapshots, latest_positions, latest_profile
from app.services.ai_runtime import active_ai_runtime, runtime_can_call_external


WORKFLOW_TYPES = {"customer_profile", "portfolio_diagnosis", "asset_allocation"}

WORKFLOW_LABELS = {
    "customer_profile": "客户画像分析",
    "portfolio_diagnosis": "持仓诊断分析",
    "asset_allocation": "资产配置建议",
}

WORKFLOW_QUESTIONS = {
    "customer_profile": "分析我的用户画像：基于基本信息、KYC、风险偏好、资金流向和真实持仓。",
    "portfolio_diagnosis": "持仓分析：诊断当前组合的集中度、收益、波动、估值和风险。",
    "asset_allocation": "资产配置：给出可执行的资产配置建议，包括比例、标的、金额和预期收益。",
}

KYC_FIELD_SPECS = [
    ("age_range", "年龄区间", "kyc_profile"),
    ("employment_status", "就业状态", "kyc_profile"),
    ("occupation_industry", "详细职业与行业", "kyc_profile"),
    ("annual_income", "年收入范围", "kyc_profile"),
    ("income_stability", "收入稳定性", "kyc_profile"),
    ("net_worth", "净资产范围", "kyc_profile"),
    ("liquid_assets", "可投资/流动资产", "kyc_profile"),
    ("liabilities", "负债与杠杆情况", "kyc_profile"),
    ("monthly_cash_flow", "月度现金流状况", "kyc_profile"),
    ("source_of_funds", "投资资金来源", "kyc_profile"),
    ("source_of_wealth", "财富来源", "kyc_profile"),
    ("tax_residency", "税务身份/居民地", "kyc_profile"),
    ("other_investments", "其他投资/持仓", "kyc_profile"),
    ("investment_objective", "投资目标", "kyc_profile"),
    ("investment_experience", "投资经验", "kyc_profile"),
    ("product_knowledge", "熟悉产品", "kyc_profile"),
    ("knowledge_confirmation", "产品知识确认", "kyc_profile"),
    ("loss_tolerance", "可承受最大回撤", "kyc_profile"),
    ("risk_tolerance", "风险承受能力", "root"),
    ("investment_horizon", "投资期限", "root"),
    ("liquidity_needs", "流动性需求", "root"),
    ("major_expense_plan", "重大资金用途", "kyc_profile"),
    ("target_return", "目标收益", "root"),
    ("investment_restrictions", "投资限制/禁忌", "kyc_profile"),
]

SKILL_NAMES = {
    "customer_profile": "customer_profile_skill",
    "portfolio_diagnosis": "portfolio_diagnosis_skill",
    "asset_allocation": "asset_allocation_skill",
}

SYSTEM_INSTRUCTION = (
    "你是一个只做辅助决策的投资组合分析 Agent。必须基于用户提供的 JSON 数据实时分析，"
    "不得声称使用了未提供的数据，不得输出立即买入、立即卖出、必涨、必跌、稳赚、满仓等强指令。"
    "用中文 Markdown 输出，结构清晰，包含数据缺失说明和风险提示。"
)


def get_investor_preference(db: Session, account_id: str = "all") -> InvestorPreference | None:
    return db.scalar(
        select(InvestorPreference)
        .where(InvestorPreference.account_id == account_id)
        .order_by(InvestorPreference.updated_at.desc())
        .limit(1)
    )


def upsert_investor_preference(db: Session, account_id: str, payload: dict[str, Any]) -> InvestorPreference:
    now = datetime.now(timezone.utc)
    preference = get_investor_preference(db, account_id)
    if not preference:
        preference = InvestorPreference(preference_id=f"pref_{uuid4().hex}", account_id=account_id, updated_at=now)
    preference.kyc_profile = _dict_payload(payload.get("kyc_profile"))
    preference.risk_tolerance = str(payload.get("risk_tolerance") or "")
    preference.investment_horizon = str(payload.get("investment_horizon") or "")
    preference.liquidity_needs = str(payload.get("liquidity_needs") or "")
    preference.target_return = str(payload.get("target_return") or "")
    preference.notes = str(payload.get("notes") or "")
    preference.updated_at = now
    db.add(preference)
    db.commit()
    db.refresh(preference)
    return preference


def preference_to_dict(item: InvestorPreference | None, account_id: str = "all") -> dict[str, Any]:
    if not item:
        payload = {
            "empty": True,
            "account_id": account_id,
            "kyc_profile": {},
            "risk_tolerance": "",
            "investment_horizon": "",
            "liquidity_needs": "",
            "target_return": "",
            "notes": "",
            "updated_at": None,
        }
        return _with_kyc_completeness(payload)
    payload = {
        "empty": False,
        "preference_id": item.preference_id,
        "account_id": item.account_id,
        "kyc_profile": item.kyc_profile or {},
        "risk_tolerance": item.risk_tolerance,
        "investment_horizon": item.investment_horizon,
        "liquidity_needs": item.liquidity_needs,
        "target_return": item.target_return,
        "notes": item.notes,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
    return _with_kyc_completeness(payload)


def _with_kyc_completeness(payload: dict[str, Any]) -> dict[str, Any]:
    kyc_profile = _dict_payload(payload.get("kyc_profile"))
    filled_fields: list[str] = []
    missing_fields: list[str] = []
    values: dict[str, Any] = {}
    for key, label, source in KYC_FIELD_SPECS:
        value = kyc_profile.get(key) if source == "kyc_profile" else payload.get(key)
        if _has_meaningful_value(value):
            filled_fields.append(label)
            values[label] = value
        else:
            missing_fields.append(label)
    payload["kyc_completeness"] = {
        "filled_count": len(filled_fields),
        "total_count": len(KYC_FIELD_SPECS),
        "ratio": len(filled_fields) / len(KYC_FIELD_SPECS),
        "filled_fields": filled_fields,
        "missing_fields": missing_fields,
        "values": values,
    }
    return payload


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip() != "未填写"
    return bool(value)


def create_workflow_run(
    db: Session,
    workflow_type: str,
    account_id: str,
    question: str | None = None,
    use_external_model: bool | None = None,
    model_override: str | None = None,
    planning_model_override: str | None = None,
    system_instruction_override: str | None = None,
) -> AIWorkflowRun:
    if workflow_type not in WORKFLOW_TYPES:
        raise ValueError("Unsupported workflow type")
    now = datetime.now(timezone.utc)
    settings = get_settings()
    runtime = active_ai_runtime(db)
    provider = str(runtime.get("provider") or settings.ai_provider).lower() if runtime_can_call_external(runtime) and use_external_model is not False else "local"
    selected_model = model_override or str(runtime.get("model") or settings.deepseek_model)
    selected_prompt = system_instruction_override or SYSTEM_INSTRUCTION
    model = selected_model if provider != "local" else "local_workflow"
    run = AIWorkflowRun(
        run_id=f"wf_{uuid4().hex}",
        workflow_type=workflow_type,
        account_id=account_id,
        question=question or WORKFLOW_QUESTIONS[workflow_type],
        status="pending",
        steps=_initial_steps(workflow_type),
        output={"use_external_model": provider != "local", "system_prompt": selected_prompt, "planning_model": planning_model_override or selected_model},
        provider=provider,
        model=model,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def latest_workflow_runs(db: Session, account_id: str = "all", limit: Optional[int] = None) -> list[AIWorkflowRun]:
    stmt = select(AIWorkflowRun).order_by(AIWorkflowRun.created_at.desc())
    if account_id != "all":
        stmt = stmt.where(AIWorkflowRun.account_id == account_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def workflow_run_to_dict(run: AIWorkflowRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "workflow_type": run.workflow_type,
        "workflow_label": WORKFLOW_LABELS.get(run.workflow_type, run.workflow_type),
        "account_id": run.account_id,
        "question": run.question,
        "status": run.status,
        "steps": run.steps or [],
        "input_context": run.input_context or {},
        "output": run.output or {},
        "artifacts": run.artifacts or [],
        "provider": run.provider,
        "model": run.model,
        "data_version": run.data_version,
        "error_message": run.error_message,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def cancel_workflow_run(db: Session, run_id: str) -> AIWorkflowRun:
    run = db.get(AIWorkflowRun, run_id)
    if not run:
        raise ValueError("Workflow run not found")
    if run.status in {"completed", "failed", "cancelled"}:
        return run
    now = datetime.now(timezone.utc)
    run.status = "cancelled"
    run.error_message = "用户已终止生成"
    run.output = {**(run.output or {}), "cancel_requested": True}
    run.steps = [
        {**step, "status": "failed" if step.get("status") == "running" else step.get("status", "pending")}
        for step in (run.steps or [])
    ]
    run.updated_at = now
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def delete_workflow_run(db: Session, run_id: str) -> None:
    run = db.get(AIWorkflowRun, run_id)
    if not run:
        raise ValueError("Workflow run not found")
    db.delete(run)
    db.commit()


def workflow_markdown_filename(run: AIWorkflowRun) -> str:
    label = WORKFLOW_LABELS.get(run.workflow_type, run.workflow_type)
    created = run.created_at.strftime("%Y%m%d_%H%M%S") if run.created_at else run.run_id
    safe_label = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", label).strip("_") or "AI投顾报告"
    return quote(f"{safe_label}_{created}_{run.run_id[:8]}.md")


def stream_workflow_run(run_id: str) -> Iterable[str]:
    from app.services.profile_agent import stream_agent_workflow

    yield from stream_agent_workflow(run_id)


def build_workflow_context(db: Session, account_id: str) -> dict[str, Any]:
    positions = latest_positions(db, account_id)
    accounts = latest_account_snapshots(db, account_id)
    profile = latest_profile(db)
    preference = get_investor_preference(db, account_id) or get_investor_preference(db, "all")
    deals = _latest_deals(db, account_id)
    watchlist = list(db.scalars(select(WatchlistItem).order_by(WatchlistItem.updated_at.desc()).limit(50)).all())
    quotes = _latest_quotes(db, [item.code for item in positions])
    news = list(db.scalars(select(NewsItem).order_by(NewsItem.publish_time.desc().nullslast(), NewsItem.fetched_at.desc()).limit(30)).all())
    now = datetime.now(timezone.utc)
    base_currency = _base_currency(accounts, positions, account_id)
    total_assets = sum(_money_to_base(item.total_assets, _snapshot_currency(item), base_currency) for item in accounts)
    market_value = sum(_money_to_base(item.market_value, _snapshot_currency(item), base_currency) for item in accounts)
    cash = sum(_money_to_base(item.cash, _snapshot_currency(item), base_currency) for item in accounts)
    if not total_assets:
        total_assets = sum(_position_market_value_base(item, base_currency) for item in positions)
    if not market_value:
        market_value = sum(_position_market_value_base(item, base_currency) for item in positions)
    position_contexts = sorted(
        [_position_context(item, quotes.get(item.code), base_currency, total_assets) for item in positions],
        key=lambda item: item["weight"],
        reverse=True,
    )
    position_exposures = _merge_position_exposures(position_contexts)
    return {
        "data_version": now.strftime("%Y%m%d%H%M%S"),
        "generated_at": now.isoformat(),
        "portfolio": {
            "account_count": len(accounts),
            "position_count": len(positions),
            "exposure_count": len(position_exposures),
            "total_assets": total_assets,
            "market_value": market_value,
            "cash": cash,
            "cash_ratio": cash / total_assets if total_assets else max(0, 1 - sum(item["weight"] for item in position_contexts)),
            "base_currency": base_currency,
            "max_position_weight": max((item["weight"] for item in position_exposures), default=0),
            "weight_basis": f"{base_currency} total_assets",
        },
        "positions": position_contexts,
        "position_exposures": position_exposures,
        "preference": preference_to_dict(preference, account_id),
        "profile": _profile_context(profile),
        "deals": [_deal_context(item) for item in deals],
        "watchlist": [{"code": item.code, "name": item.name, "group_name": item.group_name} for item in watchlist],
        "news": [{"code": item.code, "title": item.title, "source": item.source} for item in news],
    }


def build_artifacts(workflow_type: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    exposures = context.get("position_exposures") or context["positions"]
    portfolio = context["portfolio"]
    by_asset = _sum_ratio(exposures, "asset_type", extra=[{"label": "现金", "value": portfolio.get("cash_ratio") or 0}])
    by_currency = _sum_ratio(exposures, "source_currency", extra=[{"label": portfolio.get("base_currency") or "现金", "value": portfolio.get("cash_ratio") or 0}])
    by_theme = _theme_distribution(exposures, cash_ratio=float(portfolio.get("cash_ratio") or 0))
    artifacts = [
        {"artifact_id": "asset_allocation", "type": "donut", "title": "资产类型分布", "data": by_asset},
        {"artifact_id": "currency_allocation", "type": "donut", "title": "货币分布", "data": by_currency},
        {"artifact_id": "theme_concentration", "type": "bar", "title": "行业/主题集中度", "data": by_theme},
    ]
    if workflow_type == "portfolio_diagnosis":
        artifacts.append({"artifact_id": "holding_return_rank", "type": "bar", "title": "持仓收益贡献", "data": _return_contribution_rank(exposures)})
    if workflow_type == "asset_allocation":
        artifacts.append({"artifact_id": "target_allocation", "type": "donut", "title": "建议配置比例", "data": _target_allocation(context)})
    return artifacts


def build_calculation_audit_pack(context: dict[str, Any], artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    portfolio = context.get("portfolio") or {}
    positions = context.get("positions") or []
    exposures = context.get("position_exposures") or []
    artifacts = artifacts or build_artifacts("portfolio_diagnosis", context)
    top5 = exposures[:5]
    return {
        "data_version": context.get("data_version"),
        "generated_at": context.get("generated_at"),
        "portfolio": {
            "weight_basis": portfolio.get("weight_basis"),
            "base_currency": portfolio.get("base_currency"),
            "total_assets": portfolio.get("total_assets"),
            "market_value": portfolio.get("market_value"),
            "cash": portfolio.get("cash"),
            "cash_ratio": portfolio.get("cash_ratio"),
            "account_count": portfolio.get("account_count"),
            "position_count": portfolio.get("position_count"),
            "exposure_count": portfolio.get("exposure_count"),
        },
        "formulas": {
            "position_weight": "weight = normalized_market_value_in_base_currency / portfolio.total_assets",
            "merged_exposure_weight": "merged_weight = sum(position.weight for same code)",
            "return_contribution": "return_contribution = weight * profit_loss_ratio",
            "distribution_total": "distribution_total = sum(component.value), cash included where applicable",
        },
        "raw_positions": positions,
        "merged_exposures": exposures,
        "account_sources_by_code": {
            str(item.get("code")): item.get("account_positions", [])
            for item in exposures
        },
        "largest_exposure": exposures[0] if exposures else None,
        "top5_weights": [
            {"code": item.get("code"), "weight": item.get("weight"), "market_value": item.get("market_value")}
            for item in top5
        ],
        "top5_weight_total": sum(float(item.get("weight") or 0) for item in top5),
        "return_contribution_rank": _return_contribution_rank(exposures),
        "distribution_checks": _distribution_checks(artifacts),
        "artifacts": artifacts,
        "data_quality": {
            "missing_quotes": _missing_quote_codes(exposures),
            "kline_status": "unknown_until_get_kline_summary_runs",
            "news_status": "available" if context.get("news") else "missing",
        },
    }


def audit_calculation_pack_locally(pack: dict[str, Any], report_markdown: str = "") -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    exposures = pack.get("merged_exposures") or []
    top5 = pack.get("top5_weights") or []
    distribution_artifact_ids = {"asset_allocation", "currency_allocation", "theme_concentration", "target_allocation"}
    if exposures:
        sorted_codes = [item.get("code") for item in sorted(exposures, key=lambda item: float(item.get("weight") or 0), reverse=True)]
        if pack.get("largest_exposure", {}).get("code") != sorted_codes[0]:
            issues.append("第一大合并标的与 merged_exposures.weight 排序不一致")
        if [item.get("code") for item in top5] != sorted_codes[: len(top5)]:
            issues.append("Top5 权重列表与 merged_exposures.weight 排序不一致")
    for check in pack.get("distribution_checks") or []:
        if check.get("artifact_id") not in distribution_artifact_ids:
            continue
        total = float(check.get("total") or 0)
        if not 0.98 <= total <= 1.02:
            issues.append(f"{check.get('artifact_id')} 合计不接近 100%：{total:.4f}")
    expected = {
        str(item.get("label")): float(item.get("value") or 0)
        for item in pack.get("return_contribution_rank") or []
    }
    for item in exposures:
        code = str(item.get("code") or "")
        contribution = float(item.get("weight") or 0) * float(item.get("profit_loss_ratio") or 0)
        if code in expected and abs(expected[code] - contribution) > 0.000001:
            issues.append(f"{code} 收益贡献不等于 weight × profit_loss_ratio")
    if "account_weight" in report_markdown and "禁止" not in report_markdown:
        warnings.append("报告提到 account_weight，但未明确禁止跨账户相加")
    return {"status": "ok" if not issues else "failed", "issues": issues, "warnings": warnings}


def build_markdown_report(workflow_type: str, context: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    if workflow_type == "customer_profile":
        return _customer_profile_report(context, artifacts)
    if workflow_type == "portfolio_diagnosis":
        return _portfolio_diagnosis_report(context, artifacts)
    return _asset_allocation_report(context, artifacts)


def _agent_decide_step(
    settings,
    run: AIWorkflowRun,
    step: dict[str, Any],
    context: dict[str, Any],
    artifacts: list[dict[str, Any]],
    completed_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    use_external_model = bool((run.output or {}).get("use_external_model"))
    if use_external_model and settings.ai_provider.lower() == "deepseek" and settings.deepseek_api_key:
        try:
            return _call_deepseek_agent_step(settings, run, step, context, artifacts, completed_steps)
        except Exception as exc:
            local = _local_agent_step(run.workflow_type, step, context, artifacts)
            local["detail"] = f"{local['detail']}（模型步骤判断失败，已使用本地决策：{str(exc)[:120]}）"
            return local
    return _local_agent_step(run.workflow_type, step, context, artifacts)


def _call_deepseek_agent_step(
    settings,
    run: AIWorkflowRun,
    step: dict[str, Any],
    context: dict[str, Any],
    artifacts: list[dict[str, Any]],
    completed_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    endpoint = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": run.model or settings.deepseek_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是投资组合分析 workflow 的步骤规划 Agent。你必须基于已知数据决定当前步骤要做什么，"
                    "输出严格 JSON，不要 Markdown。不要输出隐藏推理链，只输出可展示给用户的步骤说明。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "workflow": {
                            "type": run.workflow_type,
                            "label": WORKFLOW_LABELS.get(run.workflow_type, run.workflow_type),
                            "question": run.question,
                        },
                        "current_step": step,
                        "completed_steps": completed_steps,
                        "context_summary": _agent_context_summary(context),
                        "artifact_summary": [{"artifact_id": item.get("artifact_id"), "title": item.get("title")} for item in artifacts],
                        "allowed_output_schema": {
                            "title": "一句话步骤标题",
                            "detail": "面向用户展示的本步判断，说明为什么要做这步、需要哪些数据、下一步动作；不要超过120字",
                            "action_label": "本步将执行的动作标签",
                            "agent_note": "一句很短的可展示决策说明",
                        },
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=25) as resp:  # nosec - user configured endpoint
        data = json.loads(resp.read().decode("utf-8"))
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"detail": text}
    return _normalize_agent_step(step, parsed)


def _local_agent_step(workflow_type: str, step: dict[str, Any], context: dict[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    portfolio = context.get("portfolio", {})
    position_count = int(portfolio.get("position_count") or 0)
    max_weight = float(portfolio.get("max_position_weight") or 0)
    cash_ratio = float(portfolio.get("cash_ratio") or 0)
    templates = {
        "analysis": f"先判断用户问题属于{WORKFLOW_LABELS.get(workflow_type, workflow_type)}，需要结合{position_count}个持仓、现金比例{_pct(cash_ratio)}和风险偏好。",
        "plan": "根据当前目标拆解为数据读取、组合结构判断、图表生成和报告生成，避免直接给出未经验证的结论。",
        "skill": f"选择{SKILL_NAMES.get(workflow_type, 'workflow_skill')}，按该技能关注集中度、分层、偏好约束和缺失数据。",
        "query": f"读取账户、持仓、成交、投顾偏好、自选和新闻摘要；当前最大单票约{_pct(max_weight)}。",
        "artifact": f"基于已读取数据决定生成{len(artifacts) or '组合'}图表，优先展示资产、货币、主题和收益贡献。",
        "report": "数据与图表已准备，开始按辅助决策边界生成结构化报告，并标注风险和缺失项。",
    }
    detail = templates.get(str(step.get("action_type")), str(step.get("detail") or "执行当前步骤"))
    return _normalize_agent_step(
        step,
        {
            "title": step.get("title"),
            "detail": detail,
            "action_label": step.get("action_label"),
            "agent_note": "本地 agent 已完成本步判断",
        },
    )


def _normalize_agent_step(base_step: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or base_step.get("title") or "")
    detail = str(payload.get("detail") or base_step.get("detail") or "")
    action_label = str(payload.get("action_label") or base_step.get("action_label") or "")
    agent_note = str(payload.get("agent_note") or "")
    if agent_note and agent_note not in detail:
        detail = f"{detail} {agent_note}"
    return {
        "title": _sanitize_text(title)[:80],
        "detail": _sanitize_text(detail)[:240],
        "action_label": _sanitize_text(action_label)[:80],
        "agent_note": _sanitize_text(agent_note)[:120],
    }


def _agent_context_summary(context: dict[str, Any]) -> dict[str, Any]:
    compact = _compact_context(context)
    compact["top_positions"] = [
        {
            "code": item.get("code"),
            "weight": item.get("weight"),
            "profit_loss_ratio": item.get("profit_loss_ratio"),
            "layer": item.get("layer"),
        }
        for item in (context.get("position_exposures") or context.get("positions", []))[:8]
    ]
    return compact


def _stream_deepseek_report(
    settings,
    workflow_type: str,
    context: dict[str, Any],
    artifacts: list[dict[str, Any]],
    model: str | None = None,
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> Iterable[str]:
    endpoint = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model or settings.deepseek_model,
        "messages": [
            {
                "role": "system",
                "content": system_instruction,
            },
            {
                "role": "user",
                "content": (
                    f"请执行「{WORKFLOW_LABELS[workflow_type]}」工作流。"
                    "请像 AI 聊天窗口一样逐段生成报告，保留标题、表格和要点。\n"
                    "权重计算必须使用 position_exposures.weight 或 positions.weight。"
                    "account_weight 仅表示单个账户内部权重，禁止跨账户相加。"
                    "判断第一大持仓、最大单票、集中度时优先使用 position_exposures，并说明这是统一币种后的总资产口径。\n"
                    "输入数据如下：\n"
                    + json.dumps(
                        {
                            "workflow_type": workflow_type,
                            "question": WORKFLOW_QUESTIONS[workflow_type],
                            "context": _compact_context(context),
                            "artifacts": artifacts,
                            "guardrails": {
                                "decision_boundary": "只做分析建议，不自动下单",
                                "forbidden_phrases": ["立即买入", "立即卖出", "必涨", "必跌", "稳赚", "满仓"],
                            },
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                ),
            },
        ],
        "temperature": 0.2,
        "stream": True,
    }
    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=60) as resp:  # nosec - user configured endpoint
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data == "[DONE]":
                break
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = payload.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if delta:
                yield _sanitize_text(str(delta))


def _local_report_stream(workflow_type: str, context: dict[str, Any], artifacts: list[dict[str, Any]]) -> Iterable[str]:
    markdown = build_markdown_report(workflow_type, context, artifacts)
    for part in _report_chunks(markdown):
        for line in part.splitlines(keepends=True):
            if line:
                yield _sanitize_text(line)
                time.sleep(0.08)
        if not part.endswith("\n"):
            yield "\n"
        time.sleep(0.2)


def _initial_steps(workflow_type: str) -> list[dict[str, Any]]:
    skill_name = SKILL_NAMES[workflow_type]
    return [
        _step(1, "正在分析问题", "理解问题，确认所需数据", "analysis", "分析问题"),
        _step(2, "制定执行计划", f"选择 {skill_name} 并拆解查询、绘图和报告任务", "plan", "制定执行计划"),
        _step(3, "学习技能文档", f"读取 {skill_name} 的分析框架与输出约束", "skill", f"学习技能文档 - {skill_name}"),
        _step(4, "执行技能查询", "查询账户、持仓、成交、画像偏好、自选和行情摘要", "query", "执行脚本 - 查询画像上下文"),
        _step(5, "委托子 Agent 执行子任务", "生成图表和表格 artifact", "artifact", "委托Agent - 可视化智能体"),
        _step(6, "生成分析报告", "组合结构、风险、建议和缺失数据说明流式输出", "report", "保存可执行文件"),
    ]


def _step(step_no: int, title: str, detail: str, action_type: str, action_label: str) -> dict[str, Any]:
    return {
        "step_no": step_no,
        "title": title,
        "detail": detail,
        "action_type": action_type,
        "action_label": action_label,
        "status": "pending",
        "artifact_ids": [],
    }


def _customer_profile_report(context: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    pref = context["preference"]
    portfolio = context["portfolio"]
    positions = context.get("position_exposures") or context["positions"]
    completeness = pref.get("kyc_completeness") or {}
    missing_fields = list(completeness.get("missing_fields") or [])
    filled_count = int(completeness.get("filled_count") or 0)
    total_count = int(completeness.get("total_count") or len(KYC_FIELD_SPECS))
    missing_pref = pref.get("empty") or filled_count < total_count
    top = positions[:5]
    return "\n".join(
        [
            "# 您的投资者画像分析",
            "",
            "## 一、核心结论",
            f"当前组合共 {portfolio['position_count']} 条持仓记录、{portfolio.get('exposure_count', portfolio['position_count'])} 个合并标的，现金比例约 {_pct(portfolio['cash_ratio'])}，最大单一标的约 {_pct(portfolio['max_position_weight'])}。",
            f"以下权重均按「{portfolio.get('weight_basis', '总资产口径')}」计算；单账户内部权重只作辅助参考。",
            "画像判断偏向：真实持仓驱动 + 本地风险偏好校准。",
            f"KYC 完整度：已填写 {filled_count}/{total_count} 项。" + (f" 仍缺少：{'、'.join(missing_fields[:8])}。" if missing_fields else ""),
            "主观风险偏好数据不足，以下结论会降低置信度。" if missing_pref else f"您填写的风险承受能力为「{pref.get('risk_tolerance')}」，投资期限为「{pref.get('investment_horizon')}」，目标收益为「{pref.get('target_return')}」。",
            "",
            "## 二、资产配置画像",
            _artifact_table("资产类型分布", artifacts, "asset_allocation"),
            _artifact_table("货币分布", artifacts, "currency_allocation"),
            "",
            "## 三、投资主题与交易特征",
            _artifact_table("行业/主题集中度", artifacts, "theme_concentration"),
            f"近期待观察的核心持仓包括：{', '.join(item['code'] for item in top) if top else '暂无持仓'}。",
            f"历史成交样本数：{len(context['deals'])}，自选股样本数：{len(context['watchlist'])}。",
            "",
            "## 四、风险偏好画像",
            f"- 年龄区间：{pref.get('kyc_profile', {}).get('age_range') or '未填写'}",
            f"- 详细职业与行业：{pref.get('kyc_profile', {}).get('occupation_industry') or '未填写'}",
            f"- 年收入/净资产：{pref.get('kyc_profile', {}).get('annual_income') or '未填写'} / {pref.get('kyc_profile', {}).get('net_worth') or '未填写'}",
            f"- 负债与现金流：{pref.get('kyc_profile', {}).get('liabilities') or '未填写'} / {pref.get('kyc_profile', {}).get('monthly_cash_flow') or '未填写'}",
            f"- 资金与财富来源：{pref.get('kyc_profile', {}).get('source_of_funds') or '未填写'} / {pref.get('kyc_profile', {}).get('source_of_wealth') or '未填写'}",
            f"- 税务身份/居民地：{pref.get('kyc_profile', {}).get('tax_residency') or '未填写'}",
            f"- 其他投资/持仓：{pref.get('kyc_profile', {}).get('other_investments') or '未填写'}",
            f"- 风险承受能力：{pref.get('risk_tolerance') or '未填写'}",
            f"- 投资期限：{pref.get('investment_horizon') or '未填写'}",
            f"- 流动性需求：{pref.get('liquidity_needs') or '未填写'}",
            f"- 目标收益：{pref.get('target_return') or '未填写'}",
            f"- 投资限制/禁忌：{pref.get('kyc_profile', {}).get('investment_restrictions') or '未填写'}",
            "",
            "## 五、需要补充的数据",
            f"- 画像缺口：{'、'.join(missing_fields) if missing_fields else '暂无 KYC 缺口'}。",
            "- 若需要更精细的风格识别，建议同步更长周期成交记录。",
        ]
    )


def _portfolio_diagnosis_report(context: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    portfolio = context["portfolio"]
    positions = context.get("position_exposures") or context["positions"]
    top = positions[:10]
    concentration = "偏高" if portfolio["max_position_weight"] >= 0.25 else "可控"
    return "\n".join(
        [
            "# 持仓组合综合诊断分析",
            "",
            "## 一、总体结论",
            f"组合最大单一标的权重为 {_pct(portfolio['max_position_weight'])}，集中度判断为「{concentration}」。现金比例约 {_pct(portfolio['cash_ratio'])}，当前更适合做结构复核而不是强交易指令。",
            f"权重口径：{portfolio.get('weight_basis', '总资产口径')}；同一代码跨账户持仓已先折算并合并，未直接相加账户内权重。",
            "",
            "## 二、持仓概览",
            "| 标的代码 | 持仓占比 | 近况 | 当前盈亏 |",
            "| --- | ---: | --- | ---: |",
            *[f"| {item['code']} | {_pct(item['weight'])} | {item['layer']} | {_pct(item['profit_loss_ratio'])} |" for item in top],
            "",
            "## 三、行业与主题集中度",
            _artifact_table("行业/主题集中度", artifacts, "theme_concentration"),
            "",
            "## 四、风险指标深度分析",
            _artifact_table("持仓收益贡献", artifacts, "holding_return_rank"),
            f"组合集中度：最大单一标的 {_pct(portfolio['max_position_weight'])}；若超过 25%，建议优先复核该标的是否仍符合原始持仓理由。",
            "K线、估值和宏观数据如未同步成功，本报告只使用本地快照和行情摘要，结论强度自动下调。",
            "",
            "## 五、实时行情关注点",
            *[f"- {item['code']}：当前价 {item['current_price']:.2f}，仓位 {_pct(item['weight'])}，分层为 {item['layer']}。" for item in top[:5]],
            "",
            "## 六、综合评估与风险提示",
            "- 本报告只做辅助决策，不构成交易指令。",
            "- 数据刷新后若持仓、现金或行情明显变化，应重新生成诊断。",
        ]
    )


def _asset_allocation_report(context: dict[str, Any], artifacts: list[dict[str, Any]]) -> str:
    pref = context["preference"]
    portfolio = context["portfolio"]
    total_assets = float(portfolio["total_assets"] or portfolio["market_value"] or 0)
    target = _target_allocation(context)
    rows = []
    for item in target:
        ratio = float(item["value"])
        rows.append(
            f"| {item['label']} | {_pct(ratio)} | {_money(total_assets * ratio, portfolio['base_currency'])} | {item.get('examples', '')} |"
        )
    return "\n".join(
        [
            "# 资产配置建议",
            "",
            "## 一、核心结论",
            f"基于当前组合和本地风险偏好，建议采用「哑铃结构」：一端保留 AI/科技核心资产，另一端补足现金、短债或黄金等防御资产。当前目标收益填写为：{pref.get('target_return') or '未填写'}。",
            "",
            "## 二、当前持仓诊断",
            f"当前现金比例约 {_pct(portfolio['cash_ratio'])}，最大单一标的约 {_pct(portfolio['max_position_weight'])}。权重口径为 {portfolio.get('weight_basis', '总资产口径')}。若最大单一标的超过风险承受能力，应先做集中度再平衡。",
            _artifact_table("资产类型分布", artifacts, "asset_allocation"),
            "",
            "## 三、建议目标配置方案",
            "| 资产类别 | 建议比例 | 估算金额 | 参考标的 |",
            "| --- | ---: | ---: | --- |",
            *rows,
            "",
            "## 四、具体调仓建议",
            "- 对超过目标权重的科技/半导体持仓，可考虑分批降至目标区间，而不是一次性处理。",
            "- 对现金或短债仓位不足的账户，可考虑用短债 ETF 或货币现金类资产提高防御性。",
            "- 黄金或长债只作为组合对冲工具，建议小比例配置，并结合利率环境复核。",
            "",
            "## 五、预期收益与风险情景",
            "- 乐观情景：科技主线延续，组合弹性主要来自 AI/科技核心持仓。",
            "- 中性情景：指数震荡，短债/现金降低组合波动。",
            "- 悲观情景：高估值科技回撤，防御资产用于缓冲净值波动。",
            "",
            "## 六、关键时间点",
            "- 财报季、FOMC、重大产品发布和指数再平衡前后建议重新生成配置建议。",
            "",
            "风险提示：以上分析基于本地数据和当前快照，不构成投资建议或收益承诺。",
        ]
    )


def _target_allocation(context: dict[str, Any]) -> list[dict[str, Any]]:
    pref = context["preference"]
    risk = str(pref.get("risk_tolerance") or "")
    if "保守" in risk:
        return [
            {"label": "AI/科技核心股票", "value": 0.25, "examples": "QQQ、NVDA、MSFT"},
            {"label": "宽基ETF", "value": 0.25, "examples": "SPY、VOO"},
            {"label": "短债/现金管理", "value": 0.30, "examples": "SHY、BIL"},
            {"label": "黄金ETF", "value": 0.10, "examples": "GLD"},
            {"label": "现金储备", "value": 0.10, "examples": "账户现金"},
        ]
    if "激进" in risk or "高" in risk:
        return [
            {"label": "AI/科技核心股票", "value": 0.40, "examples": "QQQ、NVDA、AMD、TSM"},
            {"label": "宽基ETF", "value": 0.20, "examples": "SPY、VOO"},
            {"label": "半导体/成长主题", "value": 0.15, "examples": "SOX、SMH"},
            {"label": "短债/现金管理", "value": 0.15, "examples": "SHY、BIL"},
            {"label": "黄金ETF", "value": 0.05, "examples": "GLD"},
            {"label": "现金储备", "value": 0.05, "examples": "账户现金"},
        ]
    return [
        {"label": "AI/科技核心股票", "value": 0.35, "examples": "QQQ、NVDA、MSFT"},
        {"label": "宽基ETF", "value": 0.25, "examples": "SPY、VOO"},
        {"label": "短债/现金管理", "value": 0.20, "examples": "SHY、BIL"},
        {"label": "黄金ETF", "value": 0.10, "examples": "GLD"},
        {"label": "现金储备", "value": 0.10, "examples": "账户现金"},
    ]


def _latest_deals(db: Session, account_id: str) -> list[Deal]:
    stmt = select(Deal).order_by(Deal.deal_time.desc().nullslast()).limit(100)
    if account_id != "all":
        stmt = stmt.where(Deal.account_id == account_id)
    return list(db.scalars(stmt).all())


def _latest_quotes(db: Session, codes: list[str]) -> dict[str, QuoteSummary]:
    if not codes:
        return {}
    rows = list(db.scalars(select(QuoteSummary).where(QuoteSummary.code.in_(codes)).order_by(QuoteSummary.quote_time.desc()).limit(500)).all())
    result = {}
    for row in rows:
        result.setdefault(row.code, row)
    return result


def _position_context(item: PositionSnapshot, quote: QuoteSummary | None, base_currency: str, total_assets: float) -> dict[str, Any]:
    market_value = _position_market_value_base(item, base_currency)
    return {
        "account_id": item.account_id,
        "code": item.code,
        "name": item.name,
        "market": item.market,
        "asset_type": item.asset_type,
        "currency": base_currency,
        "source_currency": item.raw_currency or item.normalized_currency,
        "quantity": item.quantity,
        "current_price": item.current_price or (quote.current_price if quote else 0),
        "average_cost": item.average_cost,
        "market_value": market_value,
        "raw_market_value": item.normalized_market_value,
        "account_weight": item.position_weight,
        "weight": market_value / total_assets if total_assets else 0,
        "profit_loss_ratio": item.profit_loss_ratio,
        "layer": item.position_layer,
        "change_ratio": quote.change_ratio if quote else 0,
    }


def _merge_position_exposures(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in positions:
        groups[str(item.get("code") or "")].append(item)
    exposures = []
    for code, group in groups.items():
        first = group[0]
        market_value = sum(float(item.get("market_value") or 0) for item in group)
        weight = sum(float(item.get("weight") or 0) for item in group)
        weighted_pl = _weighted_ratio(group, "profit_loss_ratio", "market_value")
        weighted_change = _weighted_ratio(group, "change_ratio", "market_value")
        exposures.append(
            {
                **first,
                "code": code,
                "market_value": market_value,
                "weight": weight,
                "profit_loss_ratio": weighted_pl,
                "change_ratio": weighted_change,
                "account_count": len(group),
                "account_positions": [
                    {
                        "account_id": item.get("account_id"),
                        "market_value": item.get("market_value"),
                        "currency": item.get("currency"),
                        "weight": item.get("weight"),
                        "account_weight": item.get("account_weight"),
                    }
                    for item in group
                ],
            }
        )
    return sorted(exposures, key=lambda item: item["weight"], reverse=True)


def _weighted_ratio(items: list[dict[str, Any]], value_key: str, weight_key: str) -> float:
    total = sum(abs(float(item.get(weight_key) or 0)) for item in items)
    if not total:
        return 0
    return sum(float(item.get(value_key) or 0) * abs(float(item.get(weight_key) or 0)) for item in items) / total


def _deal_context(item: Deal) -> dict[str, Any]:
    return {
        "code": item.code,
        "side": item.side,
        "price": item.price,
        "quantity": item.quantity,
        "deal_time": item.deal_time.isoformat() if item.deal_time else None,
    }


def _profile_context(item: ProfileVersion | None) -> dict[str, Any]:
    if not item:
        return {"confidence": "未知", "tags": [], "ratios": {}}
    return {
        "confidence": item.confidence,
        "tags": item.tags,
        "ratios": {
            "核心长期仓": item.core_position_ratio,
            "中期配置仓": item.mid_position_ratio,
            "短期交易仓": item.trade_position_ratio,
            "期权仓": item.option_position_ratio,
        },
    }


def _compact_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "data_version": context["data_version"],
        "portfolio": context["portfolio"],
        "preference": context["preference"],
        "profile": context["profile"],
        "positions": context["positions"][:30],
        "position_exposures": context.get("position_exposures", [])[:30],
        "weight_note": "positions.weight 和 position_exposures.weight 均为统一币种后的总资产口径权重；account_weight 才是单账户内部权重，禁止跨账户相加。",
        "deal_count": len(context["deals"]),
        "watchlist_count": len(context["watchlist"]),
        "news_count": len(context["news"]),
    }


def _sum_ratio(positions: list[dict[str, Any]], key: str, extra: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    totals = defaultdict(float)
    for item in positions:
        label = _distribution_label(key, str(item.get(key) or "未知"))
        totals[label] += float(item.get("weight") or 0)
    for item in extra or []:
        label = str(item.get("label") or "未知")
        totals[label] += float(item.get("value") or 0)
    return [{"label": label, "value": value} for label, value in sorted(totals.items(), key=lambda pair: pair[1], reverse=True)]


def _distribution_label(key: str, value: str) -> str:
    if key == "asset_type":
        return {"stock": "股票", "fund": "基金/ETF", "etf": "ETF", "cash": "现金"}.get(value.lower(), value)
    return value


def _theme_distribution(positions: list[dict[str, Any]], cash_ratio: float = 0) -> list[dict[str, Any]]:
    totals = defaultdict(float)
    for item in positions:
        code = str(item.get("code") or "")
        name = str(item.get("name") or "")
        label = _theme_label(code, name, str(item.get("asset_type") or ""))
        totals[label] += float(item.get("weight") or 0)
    if cash_ratio:
        totals["现金/流动性"] += cash_ratio
    return [{"label": key, "value": value} for key, value in sorted(totals.items(), key=lambda pair: pair[1], reverse=True)]


def _theme_label(code: str, name: str, asset_type: str) -> str:
    text = f"{code} {name}".upper()
    if any(token in text for token in ("QQQ", "SPY", "VOO", "纳斯达克", "NASDAQ", "标普", "S&P")):
        return "宽基/成长ETF"
    if any(token in text for token in ("黄金", "GOLD", "GLD", "白银", "SILVER")):
        return "贵金属"
    if any(token in text for token in ("债券", "BOND", "SHY", "BIL", "TLT", "IEF")):
        return "债券/现金管理"
    if any(token in text for token in ("NVDA", "AMD", "TSM", "MU", "SMH", "SOX", "PLTR", "AI")):
        return "AI/半导体"
    if any(token in text for token in ("TSLA", "NIO", "LI", "XPEV")):
        return "新能源车"
    if "ETF" in asset_type.upper() or "ETF" in text:
        return "ETF/宽基或主题"
    if code.startswith("HK."):
        return "港股资产"
    return "其他"


def _return_contribution_rank(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in positions:
        contribution = float(item.get("weight") or 0) * float(item.get("profit_loss_ratio") or 0)
        rows.append({"label": item["code"], "value": contribution})
    return sorted(rows, key=lambda item: abs(item["value"]), reverse=True)[:12]


def _distribution_checks(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    for artifact in artifacts:
        data = artifact.get("data") or []
        total = sum(float(item.get("value") or 0) for item in data)
        checks.append(
            {
                "artifact_id": artifact.get("artifact_id"),
                "title": artifact.get("title"),
                "total": total,
                "status": "ok" if 0.98 <= total <= 1.02 else "warning",
            }
        )
    return checks


def _missing_quote_codes(exposures: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("code"))
        for item in exposures
        if item.get("code") and not float(item.get("current_price") or 0)
    ]


def _workflow_summary(workflow_type: str, context: dict[str, Any]) -> str:
    portfolio = context["portfolio"]
    if workflow_type == "asset_allocation":
        return f"建议围绕总资产 {portfolio['base_currency']} 口径做结构再平衡，优先处理集中度和现金防御。"
    if workflow_type == "portfolio_diagnosis":
        return f"组合共 {portfolio['position_count']} 个持仓，最大单票 {_pct(portfolio['max_position_weight'])}。"
    return f"画像基于 {portfolio['position_count']} 个持仓、本地偏好和成交记录生成。"


def build_home_summary_cards(workflow_type: str, context: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if workflow_type != "portfolio_diagnosis":
        return []
    portfolio = context.get("portfolio") or {}
    exposures = context.get("position_exposures") or context.get("positions") or []
    top5_weight = sum(float(item.get("weight") or 0) for item in exposures[:5])
    top = exposures[0] if exposures else {}
    top_label = str(top.get("name") or top.get("code") or "第一大持仓")
    top_weight = float(top.get("weight") or portfolio.get("max_position_weight") or 0)
    cash_ratio = float(portfolio.get("cash_ratio") or 0)
    loss_items = [item for item in exposures if float(item.get("profit_loss_ratio") or 0) < -0.15]
    concentration_risk = top_weight >= 0.25 or top5_weight >= 0.65
    loss_risk = bool(loss_items)
    cash_risk = cash_ratio < 0.05
    review_items = _home_priority_review_items(exposures)
    if concentration_risk:
        verdict = f"组合偏集中，先复核 {top_label} 等核心暴露"
        tone = "risk"
    elif loss_risk:
        verdict = "组合存在较深亏损持仓，先复核亏损理由和复盘记录"
        tone = "risk"
    elif cash_risk:
        verdict = "现金缓冲偏低，阶段性复核时先确认流动性安排"
        tone = "watch"
    elif exposures:
        verdict = "组合暂无突出预警，保持定期复核即可"
        tone = "ok"
    else:
        verdict = "导入或同步持仓后，首页会显示组合体检结论"
        tone = "info"
    return [
        {
            "key": "overall_verdict",
            "label": "本次体检结论",
            "tone": tone,
            "summary": _home_card_text(verdict),
            "value": _home_card_text(verdict),
            "items": _home_card_items(
                [
                    {"text": "集中度复核", "reason": f"{top_label} / Top5 进入重点观察区间"} if concentration_risk else None,
                    {"text": "亏损复盘", "reason": f"{len(loss_items)} 只持仓亏损超过 15%"} if loss_risk else None,
                    {"text": "流动性检查", "reason": "现金缓冲偏低"} if cash_risk else None,
                ]
            ),
            "source": "local_rules",
        },
        {
            "key": "priority_review",
            "label": "优先复核",
            "tone": "watch" if review_items else "ok",
            "summary": "先看这些标的，原因比仓位数字更重要" if review_items else "暂无需要立即复核的单一标的",
            "value": "先看这些标的，原因比仓位数字更重要" if review_items else "暂无需要立即复核的单一标的",
            "items": review_items,
            "source": "local_rules",
        },
    ]


def _home_priority_review_items(exposures: list[dict[str, Any]]) -> list[dict[str, str]]:
    candidates = []
    for item in exposures:
        weight = float(item.get("weight") or 0)
        profit_loss_ratio = float(item.get("profit_loss_ratio") or 0)
        reasons = []
        if weight >= 0.25:
            reasons.append(f"仓位 {_pct(weight)}，需确认集中暴露")
        if profit_loss_ratio < -0.15:
            reasons.append(f"亏损 {_pct(abs(profit_loss_ratio))}，需复核买入理由")
        if not reasons:
            continue
        score = weight * 3 + max(0, -profit_loss_ratio) + len(reasons) * 0.2
        candidates.append(
            {
                "score": score,
                "text": str(item.get("name") or item.get("code") or "未命名持仓"),
                "code": str(item.get("code") or ""),
                "reason": reasons[0],
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return _home_card_items(candidates)


def _home_card_items(items: list[Any]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        text = _home_card_text(str(raw.get("text") or ""))
        if not text:
            continue
        item = {"text": text}
        reason = _home_card_text(str(raw.get("reason") or ""))
        code = _home_card_text(str(raw.get("code") or ""))
        if reason:
            item["reason"] = reason
        if code:
            item["code"] = code
        cleaned.append(item)
        if len(cleaned) >= 3:
            break
    return cleaned


def _first_artifact_item(artifacts: list[dict[str, Any]], artifact_id: str) -> dict[str, Any] | None:
    artifact = next((item for item in artifacts if item.get("artifact_id") == artifact_id), None)
    data = artifact.get("data") if isinstance(artifact, dict) else None
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    return first if isinstance(first, dict) else None


def _home_card_text(value: str) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split()).strip()
    blocked = [
        "calculation_audit",
        "audit_pack",
        "account_weight",
        "total_assets",
        "distribution_checks",
        "portfolio_status",
        "main_risk",
        "opportunity",
        "next_action",
    ]
    if any(token.lower() in text.lower() for token in blocked):
        return "数据不足，建议补充数据后重新诊断"
    return text[:84]


def _artifact_table(title: str, artifacts: list[dict[str, Any]], artifact_id: str) -> str:
    artifact = next((item for item in artifacts if item["artifact_id"] == artifact_id), None)
    if not artifact:
        return f"{title}：暂无数据。"
    rows = [f"{item['label']} {_pct(float(item['value']))}" for item in artifact.get("data", [])[:8]]
    return f"{title}：" + ("；".join(rows) if rows else "暂无数据。")


def _report_chunks(markdown: str) -> list[str]:
    sections = markdown.split("\n## ")
    if not sections:
        return [markdown]
    chunks = [sections[0]]
    chunks.extend("\n## " + item for item in sections[1:])
    return chunks


def _set_step(run: AIWorkflowRun, index: int, step: dict[str, Any]) -> None:
    steps = list(run.steps or [])
    steps[index] = step
    run.steps = steps
    run.updated_at = datetime.now(timezone.utc)


def _base_currency(accounts: list[AccountSnapshot], positions: list[PositionSnapshot], account_id: str = "all") -> str:
    if account_id == "all":
        return "CNY"
    for item in accounts:
        currency = (item.raw_currency_values or {}).get("currency")
        if currency:
            return str(currency)
    for item in positions:
        if item.normalized_currency:
            return item.normalized_currency
    return "HKD"


def _snapshot_currency(snapshot: AccountSnapshot) -> str:
    return str((snapshot.raw_currency_values or {}).get("currency") or "CNY")


def _position_market_value_base(position: PositionSnapshot, base_currency: str) -> float:
    return _money_to_base(position.normalized_market_value, position.normalized_currency or position.raw_currency, base_currency)


def _money_to_base(value: float, currency: str, base_currency: str) -> float:
    currency = (currency or base_currency or "CNY").upper()
    base_currency = (base_currency or currency).upper()
    return float(value or 0) * _currency_rate_to_cny(currency) / _currency_rate_to_cny(base_currency)


def _currency_rate_to_cny(currency: str) -> float:
    rates = {"CNY": 1.0, "CNH": 1.0, "USD": 7.2, "HKD": 0.92}
    return rates.get(currency.upper(), 1.0)


def _dict_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _money(value: float, currency: str) -> str:
    return f"{currency} {value:,.0f}"


def _sanitize_text(text: str) -> str:
    for phrase in ("立即买入", "立即卖出", "必涨", "必跌", "稳赚", "满仓"):
        text = text.replace(phrase, "关注")
    return text


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
