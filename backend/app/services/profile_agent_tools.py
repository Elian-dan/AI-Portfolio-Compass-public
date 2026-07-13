from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable
from urllib import request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.futu_adapter import FutuReadOnlyAdapter
from app.config import get_settings
from app.models import NewsItem, QuoteSummary
from app.services.profile_workflows import (
    WORKFLOW_TYPES,
    audit_calculation_pack_locally,
    build_artifacts,
    build_calculation_audit_pack,
    build_workflow_context,
)


SKILL_DIR = Path(__file__).resolve().parents[1] / "skills"
SKILL_FILES = {
    "customer_profile": "customer_profile_skill.md",
    "portfolio_diagnosis": "portfolio_diagnosis_skill.md",
    "asset_allocation": "asset_allocation_skill.md",
}


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    handler: Callable[[Session, str, dict[str, Any], dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def list_for_prompt(self) -> list[dict[str, str]]:
        return [{"name": item.name, "description": item.description} for item in self._tools.values()]

    def names(self) -> set[str]:
        return set(self._tools)

    def run(self, db: Session, account_id: str, tool_name: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self._tools:
            return {"status": "error", "error": f"未知工具：{tool_name}", "available_tools": sorted(self._tools)}
        try:
            return self._tools[tool_name].handler(db, account_id, args or {}, state)
        except Exception as exc:  # pragma: no cover - tool boundary
            return {"status": "error", "error": str(exc)[:500], "tool": tool_name}


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(AgentTool("read_skill_doc", "读取当前 workflow 对应的 skill 文档。", read_skill_doc))
    registry.register(AgentTool("get_portfolio_context", "读取本地账户、持仓、合并标的暴露、偏好、成交、自选、新闻和行情摘要。", get_portfolio_context))
    registry.register(AgentTool("get_investor_preferences", "读取本地 KYC 和投资偏好。", get_investor_preferences))
    registry.register(AgentTool("get_positions", "读取单账户持仓记录，权重已统一为总资产口径。", get_positions))
    registry.register(AgentTool("get_position_exposures", "读取同代码跨账户合并后的真实组合暴露。", get_position_exposures))
    registry.register(AgentTool("get_deals_summary", "读取成交摘要，用于判断交易行为和样本数量。", get_deals_summary))
    registry.register(AgentTool("get_watchlist", "读取自选股摘要。", get_watchlist))
    registry.register(AgentTool("get_latest_quotes", "读取本地最近行情摘要。", get_latest_quotes))
    registry.register(AgentTool("get_recent_news", "读取本地最近新闻摘要。", get_recent_news))
    registry.register(AgentTool("get_kline_summary", "通过富途只读接口补查日线/周线 K 线摘要，失败时返回 missing。", get_kline_summary))
    registry.register(AgentTool("calculate_portfolio_metrics", "计算组合核心指标和权重口径。", calculate_portfolio_metrics))
    registry.register(AgentTool("calculate_allocation_distribution", "计算资产、货币、主题分布和收益贡献。", calculate_allocation_distribution))
    registry.register(AgentTool("calculate_audit_pack", "生成可审计计算包，作为报告唯一关键数字来源。", calculate_audit_pack))
    registry.register(AgentTool("audit_calculation_pack", "审计计算包排序、分布合计、收益贡献和报告数字来源。", audit_calculation_pack))
    registry.register(AgentTool("create_chart_artifact", "生成图表 artifact 数据。", create_chart_artifact))
    registry.register(AgentTool("finalize_report", "提示 Agent 进入最终报告阶段；持仓诊断必须在 tool_args.home_summary_cards 中提供首页诊断摘要卡。", finalize_report))
    registry.register(AgentTool("validate_report", "校验报告计算口径、禁用词和缺失数据说明。", validate_report_tool))
    return registry


def read_skill_doc(_db: Session, _account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    workflow_type = str(args.get("workflow_type") or state.get("workflow_type") or "")
    if workflow_type not in WORKFLOW_TYPES:
        return {"status": "error", "error": f"不支持的 workflow_type：{workflow_type}"}
    path = SKILL_DIR / SKILL_FILES[workflow_type]
    content = path.read_text(encoding="utf-8")
    state["skill_doc"] = content
    return {"status": "ok", "workflow_type": workflow_type, "path": str(path), "content": content}


def get_portfolio_context(db: Session, account_id: str, _args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    context = _context(db, account_id, state)
    return {
        "status": "ok",
        "portfolio": context["portfolio"],
        "top_exposures": context.get("position_exposures", [])[:10],
        "position_count": len(context.get("positions", [])),
        "deal_count": len(context.get("deals", [])),
        "watchlist_count": len(context.get("watchlist", [])),
        "news_count": len(context.get("news", [])),
    }


def get_investor_preferences(db: Session, account_id: str, _args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "preference": _context(db, account_id, state).get("preference", {})}


def get_positions(db: Session, account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 30)
    return {"status": "ok", "items": _context(db, account_id, state).get("positions", [])[:limit]}


def get_position_exposures(db: Session, account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 30)
    return {"status": "ok", "items": _context(db, account_id, state).get("position_exposures", [])[:limit]}


def get_deals_summary(db: Session, account_id: str, _args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    deals = _context(db, account_id, state).get("deals", [])
    by_code: dict[str, int] = {}
    by_side: dict[str, int] = {}
    for item in deals:
        by_code[str(item.get("code") or "")] = by_code.get(str(item.get("code") or ""), 0) + 1
        by_side[str(item.get("side") or "")] = by_side.get(str(item.get("side") or ""), 0) + 1
    return {"status": "ok", "deal_count": len(deals), "by_code": by_code, "by_side": by_side, "recent": deals[:20]}


def get_watchlist(db: Session, account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 50)
    return {"status": "ok", "items": _context(db, account_id, state).get("watchlist", [])[:limit]}


FUTU_QUOTE_PREFIXES = {"US", "HK", "SH", "SZ", "SG", "MY", "JP", "CC"}


def get_latest_quotes(db: Session, account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    codes = _requested_codes(args, state)
    if not codes:
        codes = [item["code"] for item in _context(db, account_id, state).get("position_exposures", [])[:12]]
    quote_codes = _futu_quote_codes(codes)
    unsupported_codes = [code for code in codes if code not in quote_codes]
    rows = list(db.scalars(select(QuoteSummary).where(QuoteSummary.code.in_(quote_codes)).order_by(QuoteSummary.quote_time.desc()).limit(200)).all())
    seen = set()
    by_code = {}
    for row in rows:
        if row.code in seen:
            continue
        seen.add(row.code)
        by_code[row.code] = _quote_payload(row.code, row.current_price, row.change_ratio, row.volume, row.quote_time, "local_cache")

    live_error = ""
    live_codes = quote_codes
    if live_codes and args.get("live", True) is not False:
        try:
            for item in FutuReadOnlyAdapter().fetch_quote_summaries(live_codes):
                code = str(item.get("code") or "")
                if code:
                    by_code[code] = {**item, "source": "futu_opend"}
        except Exception as exc:
            live_error = str(exc)[:300]

    found = set(by_code)
    missing_codes = [code for code in quote_codes if code not in found]
    status = "ok" if found and not missing_codes else "partial" if found else "missing"
    return {
        "status": status,
        "items": [by_code[code] for code in quote_codes if code in by_code],
        "missing_codes": missing_codes,
        "unsupported_codes": unsupported_codes,
        "live_error": live_error,
    }


def get_recent_news(db: Session, account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    codes = _requested_codes(args, state)
    limit = int(args.get("limit") or 30)
    stmt = select(NewsItem).order_by(NewsItem.publish_time.desc().nullslast(), NewsItem.fetched_at.desc()).limit(limit)
    if codes:
        stmt = stmt.where(NewsItem.code.in_(codes))
    rows = list(db.scalars(stmt).all())
    return {
        "status": "ok",
        "items": [
            {
                "code": row.code,
                "title": row.title,
                "source": row.source,
                "publish_time": row.publish_time.isoformat() if row.publish_time else None,
                "url": row.url,
            }
            for row in rows
        ],
    }


def get_kline_summary(db: Session, account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    codes = _requested_codes(args, state)
    if not codes:
        codes = [item["code"] for item in _context(db, account_id, state).get("position_exposures", [])[:5]]
    requested_codes = codes
    codes = _futu_quote_codes(codes)[:8]
    unsupported_codes = [code for code in requested_codes if code not in codes]
    if not codes:
        return {"status": "missing", "message": "没有可查询 K 线的市场代码", "unsupported_codes": unsupported_codes}
    try:
        items = FutuReadOnlyAdapter().fetch_technical_summaries(codes)
        return {"status": _kline_overall_status(items), "items": items, "unsupported_codes": unsupported_codes}
    except Exception as exc:
        return {"status": "missing", "message": str(exc)[:300], "items": {}, "unsupported_codes": unsupported_codes}


def calculate_portfolio_metrics(db: Session, account_id: str, _args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    context = _context(db, account_id, state)
    exposures = context.get("position_exposures", [])
    portfolio = context.get("portfolio", {})
    return {
        "status": "ok",
        "portfolio": portfolio,
        "largest_exposure": exposures[0] if exposures else None,
        "top_5_weight": sum(float(item.get("weight") or 0) for item in exposures[:5]),
        "weight_basis": portfolio.get("weight_basis"),
    }


def calculate_allocation_distribution(db: Session, account_id: str, _args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    context = _context(db, account_id, state)
    artifacts = build_artifacts(str(state.get("workflow_type") or "portfolio_diagnosis"), context)
    state["artifacts"] = artifacts
    return {"status": "ok", "artifacts": artifacts}


def calculate_audit_pack(db: Session, account_id: str, _args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    context = _context(db, account_id, state)
    artifacts = state.get("artifacts") or build_artifacts(str(state.get("workflow_type") or "portfolio_diagnosis"), context)
    state["artifacts"] = artifacts
    pack = build_calculation_audit_pack(context, artifacts)
    kline_status = _latest_tool_status(state, "get_kline_summary") or "not_requested"
    latest_quotes = _latest_tool_observation(state, "get_latest_quotes")
    if isinstance(latest_quotes, dict):
        pack["data_quality"]["missing_quotes"] = latest_quotes.get("missing_codes", pack["data_quality"].get("missing_quotes", []))
        pack["data_quality"]["unsupported_quote_codes"] = latest_quotes.get("unsupported_codes", [])
        pack["data_quality"]["quote_live_error"] = latest_quotes.get("live_error", "")
        pack["latest_quotes"] = latest_quotes.get("items", [])
    latest_kline = _latest_tool_observation(state, "get_kline_summary")
    if isinstance(latest_kline, dict):
        pack["kline_summary"] = latest_kline.get("items", {})
        pack["data_quality"]["unsupported_kline_codes"] = latest_kline.get("unsupported_codes", [])
        if latest_kline.get("message"):
            pack["data_quality"]["kline_error"] = latest_kline.get("message")
    pack["data_quality"]["kline_status"] = kline_status
    state["calculation_audit_pack"] = pack
    return {
        "status": "ok",
        "calculation_audit_pack": pack,
        "summary": _audit_pack_summary(pack),
        "artifacts": artifacts,
    }


def audit_calculation_pack(_db: Session, _account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    pack = args.get("calculation_audit_pack") if isinstance(args.get("calculation_audit_pack"), dict) else state.get("calculation_audit_pack")
    if not isinstance(pack, dict):
        return {"status": "error", "error": "缺少 calculation_audit_pack"}
    local_result = audit_calculation_pack_locally(pack, str(args.get("markdown") or state.get("markdown") or ""))
    result = {"status": local_result["status"], "local": local_result, "ai": None}
    settings = get_settings()
    if state.get("use_deepseek") and settings.deepseek_api_key:
        try:
            result["ai"] = _call_deepseek_audit(settings, pack)
        except Exception as exc:
            result["ai"] = {"status": "timeout_or_error", "message": str(exc)[:240]}
            result["status"] = "warning" if local_result["status"] == "ok" else local_result["status"]
    state["calculation_audit_result"] = result
    return result


def create_chart_artifact(db: Session, account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    context = _context(db, account_id, state)
    workflow_type = str(args.get("workflow_type") or state.get("workflow_type") or "portfolio_diagnosis")
    artifacts = build_artifacts(workflow_type, context)
    state["artifacts"] = artifacts
    return {"status": "ok", "artifacts": artifacts}


def finalize_report(_db: Session, _account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    state["ready_to_report"] = True
    cards = _normalize_home_summary_cards(args.get("home_summary_cards"))
    if cards:
        state["home_summary_cards"] = cards
    return {"status": "ok", "message": str(args.get("message") or "可以生成最终报告"), "home_summary_cards": cards}


def _normalize_home_summary_cards(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed = ["overall_verdict", "priority_review"]
    labels = {
        "overall_verdict": "本次体检结论",
        "priority_review": "优先复核",
    }
    cards_by_key: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key not in labels:
            continue
        summary = _clean_home_card_text(str(item.get("summary") or item.get("value") or ""))
        items = _normalize_home_card_items(item.get("items"))
        if not summary and items:
            summary = items[0]["text"]
        if not summary:
            continue
        tone = str(item.get("tone") or "info")
        if tone not in {"info", "ok", "watch", "risk"}:
            tone = "info"
        source = str(item.get("source") or "ai_report")
        if source not in {"ai_report", "local_rules"}:
            source = "ai_report"
        cards_by_key[key] = {
            "key": key,
            "label": labels[key],
            "tone": tone,
            "summary": summary,
            "value": summary,
            "items": items,
            "source": source,
        }
    return [cards_by_key[key] for key in allowed if key in cards_by_key]


def _normalize_home_card_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, str]] = []
    for raw in value:
        if isinstance(raw, str):
            text = _clean_home_card_text(raw)
            if text:
                items.append({"text": text})
            continue
        if not isinstance(raw, dict):
            continue
        text = _clean_home_card_text(str(raw.get("text") or ""))
        if not text:
            continue
        item = {"text": text}
        reason = _clean_home_card_text(str(raw.get("reason") or ""))
        code = _clean_home_card_text(str(raw.get("code") or ""))
        if reason:
            item["reason"] = reason
        if code:
            item["code"] = code
        items.append(item)
        if len(items) >= 3:
            break
    return items


def _clean_home_card_text(value: str) -> str:
    text = " ".join(value.replace("\n", " ").split()).strip()
    blocked = [
        "calculation_audit",
        "audit_pack",
        "account_weight",
        "total_assets",
        "distribution_checks",
        "tool_args",
        "portfolio_status",
        "main_risk",
        "opportunity",
        "next_action",
    ]
    if any(token.lower() in text.lower() for token in blocked):
        return ""
    for phrase in ("立即买入", "立即卖出", "必涨", "必跌", "稳赚", "满仓", "清仓"):
        text = text.replace(phrase, "复核")
    return text[:84]


def validate_report_tool(_db: Session, _account_id: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    markdown = str(args.get("markdown") or state.get("markdown") or "")
    return validate_report(markdown, state)


def validate_report(markdown: str, state: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    context = state.get("context") or {}
    portfolio = context.get("portfolio") or {}
    artifacts = state.get("artifacts") or []
    forbidden = ["立即买入", "立即卖出", "必涨", "必跌", "稳赚", "满仓"]
    for phrase in forbidden:
        if phrase in markdown:
            issues.append(f"报告包含禁用词：{phrase}")
    if portfolio.get("weight_basis") and str(portfolio.get("weight_basis")) not in markdown:
        issues.append("报告缺少权重口径说明")
    for artifact_id in ("asset_allocation", "currency_allocation", "theme_concentration"):
        artifact = next((item for item in artifacts if item.get("artifact_id") == artifact_id), None)
        if artifact:
            total = sum(float(item.get("value") or 0) for item in artifact.get("data", []))
            if not 0.98 <= total <= 1.02:
                issues.append(f"{artifact.get('title') or artifact_id} 合计不是 100%")
    if not any(token in markdown for token in ("数据不足", "缺失", "K线", "行情", "新闻", "资讯")):
        missing_observed = any(_contains_missing(item.get("observation")) for item in state.get("tool_trace", []))
        if missing_observed:
            issues.append("存在缺失数据 observation，但报告未说明数据不足")
    pack = state.get("calculation_audit_pack")
    if isinstance(pack, dict):
        issues.extend(_report_number_source_issues(markdown, pack))
    return {"status": "ok" if not issues else "failed", "issues": issues}


def annotate_model_derived_percentages(markdown: str, state: dict[str, Any]) -> str:
    pack = state.get("calculation_audit_pack")
    if not isinstance(pack, dict) or not markdown:
        return markdown
    matches = _model_derived_percentage_matches(markdown, pack)
    annotated = markdown
    for item in reversed(matches):
        start = int(item["start"])
        end = int(item["end"])
        annotated = annotated[:end] + "（数据来源为模型推荐）" + annotated[end:]
    return annotated


def _context(db: Session, account_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if "context" not in state:
        state["context"] = build_workflow_context(db, account_id)
    return state["context"]


def _requested_codes(args: dict[str, Any], state: dict[str, Any]) -> list[str]:
    raw = args.get("codes")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    if isinstance(raw, str) and raw:
        return [raw]
    return [str(item.get("code")) for item in state.get("selected_exposures", []) if item.get("code")]


def _futu_quote_codes(codes: list[str]) -> list[str]:
    result = []
    seen = set()
    for code in codes:
        text = str(code or "").strip().upper()
        if "." not in text:
            continue
        prefix = text.split(".", 1)[0]
        if prefix not in FUTU_QUOTE_PREFIXES or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _quote_payload(code: str, current_price: float, change_ratio: float, volume: float, quote_time: datetime | None, source: str) -> dict[str, Any]:
    return {
        "code": code,
        "current_price": current_price,
        "change_ratio": change_ratio,
        "volume": volume,
        "quote_time": quote_time.isoformat() if quote_time else None,
        "source": source,
    }


def _kline_overall_status(items: dict[str, Any]) -> str:
    if not items:
        return "missing"
    available = 0
    missing = 0
    for by_period in items.values():
        if not isinstance(by_period, dict):
            missing += 1
            continue
        statuses = [value.get("status") for value in by_period.values() if isinstance(value, dict)]
        if any(status == "available" for status in statuses):
            available += 1
        else:
            missing += 1
    if available and missing:
        return "partial"
    if available:
        return "ok"
    return "missing"


def _contains_missing(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("status") == "missing":
            return True
        return any(_contains_missing(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_missing(item) for item in value)
    return False


def _audit_pack_summary(pack: dict[str, Any]) -> dict[str, Any]:
    portfolio = pack.get("portfolio") or {}
    largest = pack.get("largest_exposure") or {}
    return {
        "weight_basis": portfolio.get("weight_basis"),
        "total_assets": portfolio.get("total_assets"),
        "cash_ratio": portfolio.get("cash_ratio"),
        "largest_exposure": {"code": largest.get("code"), "weight": largest.get("weight")},
        "top5_weight_total": pack.get("top5_weight_total"),
        "distribution_checks": pack.get("distribution_checks"),
    }


def _latest_tool_observation(state: dict[str, Any], tool_name: str) -> Any:
    for item in reversed(state.get("tool_trace") or []):
        if item.get("tool_name") == tool_name:
            return item.get("observation")
    return None


def _latest_tool_status(state: dict[str, Any], tool_name: str) -> str:
    observation = _latest_tool_observation(state, tool_name)
    if isinstance(observation, dict):
        return str(observation.get("status") or "unknown")
    return ""


def _call_deepseek_audit(settings, pack: dict[str, Any]) -> dict[str, Any]:
    endpoint = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    prompt_pack = {
        "portfolio": pack.get("portfolio"),
        "formulas": pack.get("formulas"),
        "largest_exposure": pack.get("largest_exposure"),
        "top5_weights": pack.get("top5_weights"),
        "return_contribution_rank": pack.get("return_contribution_rank"),
        "distribution_checks": pack.get("distribution_checks"),
        "data_quality": pack.get("data_quality"),
    }
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {
                "role": "system",
                "content": "你是计算审计员，只检查 JSON 内数字是否自洽。不得替换事实数字。输出严格 JSON。",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "检查 Top 排序、分布合计、收益贡献公式、是否疑似相加 account_weight。若异常只输出 warning。",
                        "calculation_audit_pack_summary": prompt_pack,
                        "output_schema": {"status": "ok|warning", "warnings": ["..."], "checked_items": ["..."]},
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:  # nosec - user configured endpoint
        data = json.loads(resp.read().decode("utf-8"))
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"status": "warning", "warnings": [text[:300]], "checked_items": []}
    return parsed


def _report_number_source_issues(markdown: str, pack: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for item in _model_derived_percentage_matches(markdown, pack):
        issues.append(f"模型推导或未溯源百分比：{item['percent']}%（上下文：{item['context']}）")
        if len(issues) >= 5:
            break
    return issues


def _model_derived_percentage_matches(markdown: str, pack: dict[str, Any]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if not markdown:
        return matches
    portfolio = pack.get("portfolio") or {}
    allowed = {
        float(portfolio.get("cash_ratio") or 0),
        float(pack.get("top5_weight_total") or 0),
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.50,
        0.60,
        0.65,
        0.70,
        0.80,
        0.90,
    }
    allowed.update(-item for item in list(allowed) if item)
    largest = pack.get("largest_exposure") or {}
    allowed.add(float(largest.get("weight") or 0))
    allowed.update(float(item.get("weight") or 0) for item in pack.get("top5_weights") or [])
    cumulative_weight = 0.0
    for item in pack.get("merged_exposures") or []:
        weight = float(item.get("weight") or 0)
        cumulative_weight += weight
        allowed.add(weight)
        allowed.add(cumulative_weight)
        allowed.add(max(0.0, 1 - cumulative_weight))
        allowed.add(float(item.get("profit_loss_ratio") or 0))
        allowed.add(float(item.get("change_ratio") or 0))
        for account_position in item.get("account_positions") or []:
            allowed.add(float(account_position.get("weight") or 0))
            allowed.add(float(account_position.get("account_weight") or 0))
    for item in pack.get("raw_positions") or []:
        allowed.add(float(item.get("weight") or 0))
        allowed.add(float(item.get("account_weight") or 0))
        allowed.add(float(item.get("profit_loss_ratio") or 0))
        allowed.add(float(item.get("change_ratio") or 0))
    for artifact in pack.get("artifacts") or []:
        cumulative_artifact_value = 0.0
        artifact_values = [float(item.get("value") or 0) for item in artifact.get("data") or []]
        for item in artifact.get("data") or []:
            value = float(item.get("value") or 0)
            cumulative_artifact_value += value
            allowed.add(value)
            allowed.add(cumulative_artifact_value)
            allowed.add(max(0.0, 1 - cumulative_artifact_value))
        for idx, first in enumerate(artifact_values):
            for second in artifact_values[idx + 1:]:
                allowed.add(first + second)
                allowed.add(max(0.0, 1 - first - second))
    allowed.update(float(item.get("value") or 0) for item in pack.get("return_contribution_rank") or [])
    for check in pack.get("distribution_checks") or []:
        allowed.add(float(check.get("total") or 0))
    # Guard against obvious invented percentage figures while allowing section numbers and dates.
    import re

    normalized_markdown = markdown.replace("−", "-")
    for match in re.finditer(r"(?<![\d.])(-?\d+(?:\.\d+)?)%", normalized_markdown):
        percent_text = match.group(1)
        if "数据来源为模型推荐" in normalized_markdown[match.end() : match.end() + 20]:
            continue
        value = float(percent_text) / 100
        if value == 0 or abs(value) >= 1.5:
            continue
        tolerance = 0.01 if "." not in percent_text else 0.001
        if not any(abs(value - item) <= tolerance for item in allowed):
            matches.append(
                {
                    "percent": percent_text,
                    "start": match.start(),
                    "end": match.end(),
                    "context": _percentage_context(normalized_markdown, match.start(), match.end()),
                }
            )
            if len(matches) >= 20:
                break
    return matches


def _percentage_context(markdown: str, start: int, end: int) -> str:
    left = max(markdown.rfind("\n", 0, start), markdown.rfind("。", 0, start), markdown.rfind("；", 0, start), markdown.rfind("，", 0, start))
    right_candidates = [idx for idx in (markdown.find("\n", end), markdown.find("。", end), markdown.find("；", end), markdown.find("，", end)) if idx != -1]
    right = min(right_candidates) if right_candidates else min(len(markdown), end + 40)
    context = markdown[left + 1 : right].strip()
    return context[:120]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
