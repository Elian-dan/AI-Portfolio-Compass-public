from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.adapters.futu_adapter import FutuReadOnlyAdapter
from app.config import get_settings
from app.models import DecisionCard, PositionSnapshot
from app.services.ai_engine import call_llm_chat_completion, _sanitize_output
from app.services.ai_runtime import active_ai_runtime, runtime_can_call_external
from app.services.freshness import evaluate_freshness
from app.services.sync import latest_account_snapshots, latest_positions, recent_news_for_code


ALLOWED_RECOMMENDATIONS = {"继续持有", "观察", "减仓关注", "止损关注", "等待买点", "不建议追高", "信息不足"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}

LAYER_FRAMEWORKS: dict[str, dict[str, Any]] = {
    "核心长期仓": {
        "focus": ["长期逻辑是否破坏", "组合集中度", "周线趋势", "基本面或主题是否仍成立"],
        "avoid": ["不能仅因短期浮亏输出止损关注"],
        "preferred_recommendations": ["继续持有", "观察", "减仓关注", "信息不足"],
    },
    "中期配置仓": {
        "focus": ["中期趋势", "日线和周线结构", "成本区", "阶段性支撑压力", "计划失效条件"],
        "avoid": ["不能只给结论，必须说明减仓或止损依据"],
        "preferred_recommendations": ["继续持有", "观察", "减仓关注", "止损关注", "信息不足"],
    },
    "短期交易仓": {
        "focus": ["交易理由是否仍成立", "日线趋势", "浮亏是否扩大", "止盈止损计划是否需要复核"],
        "avoid": ["不能用长期持有逻辑淡化短线交易风险"],
        "preferred_recommendations": ["止损关注", "观察", "不建议追高", "信息不足"],
    },
    "期权仓": {
        "focus": ["到期日", "时间价值", "方向风险", "波动率风险", "仓位占比"],
        "avoid": ["不能只按正股涨跌判断"],
        "preferred_recommendations": ["观察", "减仓关注", "止损关注", "信息不足"],
    },
    "遗留观察仓": {
        "focus": ["是否仍有持有理由", "亏损是否长期占用资金", "是否需要重新归类"],
        "avoid": ["不能套短线止损逻辑"],
        "preferred_recommendations": ["观察", "减仓关注", "信息不足"],
    },
}


SYSTEM_INSTRUCTION = """你是一个只做辅助决策的持仓诊断卡 Agent，任务是为输入中的单个持仓生成一张持仓诊断卡。

你会收到一个 JSON，上下文包含：
- portfolio：组合层面的总资产、持仓市值、现金比例、最大单票权重、全部持仓摘要。
- position：当前要诊断的单个持仓，包括市场、资产类型、数量、价格、成本、市值、仓位占比、盈亏比例、仓位分层。
- analysis_framework：该仓位分层的分析重点、禁忌和推荐候选。
- technical：日线/周线等技术摘要，可能缺失。
- recent_news：最近消息面，可能为空。
- freshness：持仓和消息数据的新鲜度。
- missing_data_hint：系统已识别的缺失数据。
- peer_weights：组合内权重最高的若干持仓，用于判断集中度和相对优先级。
- allowed_recommendations：允许输出的 recommendation 候选。

分析流程必须按以下顺序执行：
1. 先做数据质量检查：如果 position、technical、news 等关键数据过期或缺失，必须降低结论强度，优先输出“信息不足”或“观察”，并把缺失项写入 missing_data。
2. 先从组合视角判断，再看单票：检查现金比例、最大单票权重、当前持仓在组合中的相对权重、是否存在集中度过高或单票拖累组合的问题。
3. 严格按 position.position_layer 和 analysis_framework 分层分析：
   - 核心长期仓：重点判断长期逻辑、组合集中度、周线结构和基本面/主题是否破坏；不能因为短期波动直接给短线止损逻辑。
   - 中期配置仓：重点判断中期趋势、成本区、阶段性支撑压力、仓位是否需要调整。
   - 短期交易仓：重点判断交易理由是否仍成立、浮亏是否扩大、是否触发止损/止盈复核。
   - 期权仓：重点判断到期日、时间价值、方向风险、波动率风险和仓位占比；不能只按正股涨跌判断。
   - 遗留观察仓：重点判断是否仍有持有理由、是否长期占用资金、是否需要重新归类。
4. 结合 technical 和 recent_news，但不得虚构未提供的数据；没有技术或新闻时必须明确写入 missing_data 或 risks。
5. recommendation 只能从 allowed_recommendations 中选择，priority 只能从 P0/P1/P2/P3 中选择。
6. priority 规则：
   - P0：只用于极端风险、数据严重异常或必须立即复核的情况。
   - P1：用于止损关注、减仓关注、集中度风险明显、短线交易理由明显失效。
   - P2：用于信息不足、观察但需要补数据或继续跟踪。
   - P3：用于正常跟踪、继续持有、等待买点等低紧急度事项。
7. confidence 必须根据数据完整度和一致性给出“高 / 中 / 低”。数据缺失或互相矛盾时不能给“高”。

安全边界：
- 你不得输出立即买入、立即卖出、必涨、必跌、稳赚、满仓等强指令。
- 你只能做辅助决策和风险提示，不能承诺收益，不能替用户下单。
- 不得把短期交易仓、核心长期仓、中期配置仓套成同一种止盈止损逻辑。

输出严格 JSON，不要 Markdown。字段必须包含：
recommendation, priority, confidence, conclusion, reasons, risks, invalid_conditions, missing_data。
字段要求：
- conclusion：一句话给出持仓诊断结论，必须体现仓位分层和组合视角。
- reasons：最多 3 条，优先写组合权重/分层逻辑/技术或消息证据。
- risks：最多 2 条，写最重要的组合风险或单票风险。
- invalid_conditions：最多 2 条，写什么条件出现后当前结论失效。
- missing_data：列出缺失或过期的数据项；没有则输出空数组。
"""


def generate_ai_decision_cards(
    db: Session,
    model_override: str | None = None,
    system_instruction_override: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    runtime = active_ai_runtime(db)
    model = model_override or str(runtime.get("model") or settings.deepseek_model)
    system_instruction = system_instruction_override or SYSTEM_INSTRUCTION
    prompt_hash = hashlib.sha256(system_instruction.encode("utf-8")).hexdigest()[:12]
    if not runtime_can_call_external(runtime):
        return {
            "status": "failed",
            "model": model,
            "prompt_hash": prompt_hash,
            "generated_count": 0,
            "failed": [{"code": item.code, "error": "未配置可用 AI API，未生成新的 AI 决策卡"} for item in latest_positions(db)],
        }

    positions = latest_positions(db)
    if not positions:
        return {"status": "empty", "generated_count": 0, "failed": []}

    technicals = _fetch_technical_summaries([item.code for item in positions])
    portfolio = _portfolio_context(db, positions)
    generated = 0
    failed: list[dict[str, str]] = []

    for position in positions:
        news_items = recent_news_for_code(db, position.code, days=3, limit=12)
        context = _card_context(position, positions, portfolio, technicals.get(position.code, {}), news_items)
        try:
            output = call_llm_chat_completion(
                context,
                str(runtime["api_key"]),
                model,
                str(runtime["base_url"]),
                system_instruction=system_instruction,
            )
            card = _decision_card_from_output(position, output, context, model, "ai")
            db.add(card)
            generated += 1
        except Exception as exc:
            failed.append({"code": position.code, "error": str(exc)[:300]})

    db.commit()
    status = "success" if not failed else "partial_success" if generated else "failed"
    return {"status": status, "model": model, "prompt_hash": prompt_hash, "generated_count": generated, "failed": failed}


def _fetch_technical_summaries(codes: list[str]) -> dict[str, dict[str, Any]]:
    try:
        return FutuReadOnlyAdapter().fetch_technical_summaries(codes)
    except Exception:
        return {code: {"daily": {"status": "missing"}, "weekly": {"status": "missing"}} for code in codes}


def _portfolio_context(db: Session, positions: list[PositionSnapshot]) -> dict[str, Any]:
    account_snapshots = latest_account_snapshots(db)
    total_assets = sum(item.total_assets for item in account_snapshots)
    market_value = sum(item.market_value for item in account_snapshots)
    cash = sum(item.cash for item in account_snapshots)
    return {
        "total_assets": total_assets,
        "market_value": market_value,
        "cash_ratio": cash / total_assets if total_assets else 0,
        "max_position_weight": max((item.position_weight for item in positions), default=0),
        "positions": [
            {
                "code": item.code,
                "name": item.name,
                "position_layer": item.position_layer,
                "position_weight": item.position_weight,
                "profit_loss_ratio": item.profit_loss_ratio,
                "normalized_market_value": item.normalized_market_value,
                "normalized_currency": item.normalized_currency,
            }
            for item in positions
        ],
    }


def _card_context(
    position: PositionSnapshot,
    positions: list[PositionSnapshot],
    portfolio: dict[str, Any],
    technical: dict[str, Any],
    news_items: list[Any] | None = None,
) -> dict[str, Any]:
    freshness = evaluate_freshness("position", position.snapshot_time)
    news_items = news_items or []
    news_freshness = evaluate_freshness("news", max((item.fetched_at for item in news_items), default=None))
    missing_data = []
    if technical.get("daily", {}).get("status") != "available":
        missing_data.append("daily_kline")
    if technical.get("weekly", {}).get("status") != "available":
        missing_data.append("weekly_kline")
    if freshness["status"] != "fresh":
        missing_data.append("position")
    if news_freshness["status"] == "missing":
        missing_data.append("news")

    return {
        "data_version": position.snapshot_time.strftime("%Y%m%d%H%M%S"),
        "allowed_recommendations": sorted(ALLOWED_RECOMMENDATIONS),
        "analysis_framework": _analysis_framework(position.position_layer),
        "portfolio": portfolio,
        "position": {
            "code": position.code,
            "name": position.name,
            "market": position.market,
            "asset_type": position.asset_type,
            "quantity": position.quantity,
            "current_price": position.current_price,
            "average_cost": position.average_cost,
            "raw_market_value": position.raw_market_value,
            "raw_currency": position.raw_currency,
            "normalized_market_value": position.normalized_market_value,
            "normalized_currency": position.normalized_currency,
            "position_weight": position.position_weight,
            "profit_loss_ratio": position.profit_loss_ratio,
            "position_layer": position.position_layer,
            "layer_source": position.layer_source,
            "layer_confidence": position.layer_confidence,
            "layer_reason": position.layer_reason,
            "snapshot_time": position.snapshot_time.isoformat(),
        },
        "technical": technical,
        "recent_news": [_news_context(item) for item in news_items],
        "freshness": {"position": freshness, "news": news_freshness},
        "missing_data_hint": missing_data,
        "peer_weights": [
            {"code": item.code, "position_weight": item.position_weight}
            for item in sorted(positions, key=lambda item: item.position_weight, reverse=True)[:10]
        ],
    }


def _news_context(item: Any) -> dict[str, Any]:
    return {
        "title": item.title,
        "news_sub_type": item.news_sub_type,
        "source": item.source,
        "publish_time": item.publish_time.isoformat() if item.publish_time else None,
        "url": item.url,
    }


def _decision_card_from_output(
    position: PositionSnapshot,
    output: dict[str, Any],
    context: dict[str, Any],
    model: str,
    source: str,
) -> DecisionCard:
    parsed = _normalize_ai_card_output(output, context)
    now = datetime.now(timezone.utc)
    recommendation = parsed["recommendation"]
    priority = parsed["priority"]
    return DecisionCard(
        card_id=f"card_{uuid4().hex}",
        code=position.code,
        position_layer=position.position_layer,
        recommendation=recommendation,
        confidence=parsed["confidence"],
        reasons=parsed["reasons"],
        risks=parsed["risks"],
        key_prices={},
        data_time=position.snapshot_time,
        action_required=priority in {"P0", "P1"} or recommendation in {"减仓关注", "止损关注"},
        data_version=context["data_version"],
        status="数据过期" if "position" in parsed["missing_data"] else "正常",
        priority=priority,
        generation_source=source,
        model=model,
        generated_at=now,
        input_version=context["data_version"],
        analysis_framework=context["analysis_framework"],
        missing_data=parsed["missing_data"],
        invalid_conditions=parsed["invalid_conditions"],
        created_at=now,
        read_status="未读",
    )


def _normalize_ai_card_output(output: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_output(output)
    recommendation = str(sanitized.get("recommendation") or "观察")
    if recommendation not in ALLOWED_RECOMMENDATIONS:
        recommendation = "观察"
    preferred = set(context.get("analysis_framework", {}).get("preferred_recommendations", []))
    if preferred and recommendation not in preferred:
        recommendation = "信息不足" if context.get("missing_data_hint") else "观察"
    priority = str(sanitized.get("priority") or _priority_for_recommendation(recommendation))
    if recommendation not in {"减仓关注", "止损关注"} and priority in {"P0", "P1"}:
        priority = _priority_for_recommendation(recommendation)
    if priority not in ALLOWED_PRIORITIES:
        priority = _priority_for_recommendation(recommendation)
    reasons = _list_of_text(sanitized.get("reasons"), 3)
    conclusion = str(sanitized.get("conclusion") or "").strip()
    if conclusion:
        reasons = [conclusion] + reasons
    risks = _list_of_text(sanitized.get("risks"), 2)
    invalid_conditions = _list_of_text(sanitized.get("invalid_conditions"), 2)
    missing_data = sorted(set(_list_of_text(sanitized.get("missing_data"), 5) + context.get("missing_data_hint", [])))
    return {
        "recommendation": recommendation,
        "priority": priority,
        "confidence": str(sanitized.get("confidence") or "中"),
        "reasons": reasons[:3] or ["AI 已完成持仓体检，但未返回明确依据。"],
        "risks": risks or ["缺少足够反证条件时，应继续跟踪数据变化。"],
        "invalid_conditions": invalid_conditions,
        "missing_data": missing_data,
    }


def _priority_for_recommendation(recommendation: str) -> str:
    if recommendation in {"减仓关注", "止损关注"}:
        return "P1"
    if recommendation == "信息不足":
        return "P2"
    return "P3"


def _analysis_framework(layer: str) -> dict[str, Any]:
    return {"layer": layer, **LAYER_FRAMEWORKS.get(layer, LAYER_FRAMEWORKS["中期配置仓"])}


def _list_of_text(value: Any, limit: int) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = []
    return [item.strip() for item in items if item and item.strip()][:limit]
