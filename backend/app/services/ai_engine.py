from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib import request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AIAnalysis, PositionSnapshot, ProfileVersion
from app.services.ai_runtime import active_ai_runtime, runtime_can_call_external
from app.services.sync import recent_news_for_code


SYSTEM_INSTRUCTION = """你是一个只做辅助决策的股票分析 Agent。
要求：
1. 不得输出立即买入、立即卖出、必涨、必跌、稳赚、满仓等强指令。
2. 必须区分长期仓、中期仓、短期仓、期权仓、遗留观察仓。
3. 直接基于输入中的当前持仓快照进行分析，不评价快照、行情、新闻的时间有效性，
   不得因 snapshot_time、publish_time、data_version 等时间字段降低建议强度。
4. 新闻为空时仍应基于持仓快照完成分析，不得因此输出“信息不足”。
5. 输出必须包含结论、理由、风险、失效条件、需要补充的数据。
"""

SNAPSHOT_ONLY_INSTRUCTION = """本场景的固定分析口径：
- 只基于当前持仓快照中的价格、成本、仓位、盈亏和仓位分层进行分析。
- 新闻为空也不影响对当前持仓快照的分析。
"""


def latest_ai_analysis(db: Session, code: str) -> AIAnalysis | None:
    return db.scalar(select(AIAnalysis).where(AIAnalysis.code == code).order_by(AIAnalysis.created_at.desc()).limit(1))


def generate_ai_analysis(
    db: Session,
    position: PositionSnapshot,
    model_override: str | None = None,
    system_instruction_override: str | None = None,
) -> AIAnalysis:
    settings = get_settings()
    context = build_ai_context(db, position)
    runtime = active_ai_runtime(db)
    provider = str(runtime.get("provider") or settings.ai_provider or "local").lower()
    requested_model = model_override or str(runtime.get("model") or settings.deepseek_model)
    model = requested_model if runtime_can_call_external(runtime) else "local_reasoning"
    created_at = datetime.now(timezone.utc)

    try:
        if runtime_can_call_external(runtime):
            output = call_llm_chat_completion(
                context,
                str(runtime["api_key"]),
                requested_model,
                str(runtime["base_url"]),
                system_instruction=system_instruction_override or SYSTEM_INSTRUCTION,
            )
            status = "success"
            error = ""
        else:
            output = _local_reasoning(context)
            provider = "local"
            model = "local_reasoning"
            status = "success"
            error = "" if provider == "local" else "未配置可用 AI API Key，使用本地结构化推理"
    except Exception as exc:  # pragma: no cover - depends on external provider
        output = _local_reasoning(context)
        provider = "local_fallback"
        model = "local_reasoning"
        status = "fallback"
        error = str(exc)[:1000]

    analysis = AIAnalysis(
        analysis_id=f"ai_{created_at.strftime('%Y%m%d%H%M%S')}_{position.code.replace('.', '_')}",
        code=position.code,
        provider=provider,
        model=model,
        input_context=context,
        output=output,
        status=status,
        error_message=error,
        data_version=context["data_version"],
        created_at=created_at,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def build_deepseek_request_payload(
    context: dict[str, Any],
    model: str,
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> dict[str, Any]:
    analysis_context = json.loads(json.dumps(context, ensure_ascii=False))
    analysis_context.pop("data_version", None)
    analysis_context.pop("freshness", None)
    if isinstance(analysis_context.get("position"), dict):
        analysis_context["position"].pop("snapshot_time", None)
    filtered_system_instruction = "\n".join(
        line
        for line in system_instruction.splitlines()
        if not any(keyword in line for keyword in ("过期", "新鲜度", "时间有效性", "有效时间", "数据时效"))
    ).strip()
    prompt = (
        "请基于以下 JSON 输出严格 JSON，不要使用 Markdown。输出字段按 system 指令要求；"
        "至少包含 recommendation, conclusion, reasons, risks, invalid_conditions, missing_data。\n"
        + json.dumps(analysis_context, ensure_ascii=False)
    )
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": f"{filtered_system_instruction}\n\n{SNAPSHOT_ONLY_INSTRUCTION}"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }


def call_llm_payload(payload: dict[str, Any], api_key: str, base_url: str, timeout: int = 20) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:  # nosec - user configured endpoint
        data = json.loads(resp.read().decode("utf-8"))
    text = _extract_chat_text(data)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"conclusion": text, "recommendation": "观察", "reasons": [], "risks": [], "invalid_conditions": [], "missing_data": []}
    return _sanitize_output(parsed)


def build_ai_context(db: Session, position: PositionSnapshot) -> dict[str, Any]:
    profile = db.scalar(select(ProfileVersion).order_by(ProfileVersion.generated_at.desc()).limit(1))
    news_items = recent_news_for_code(db, position.code, days=3, limit=12)
    return {
        "data_version": position.snapshot_time.strftime("%Y%m%d%H%M%S"),
        "position": {
            "code": position.code,
            "name": position.name,
            "market": position.market,
            "asset_type": position.asset_type,
            "quantity": position.quantity,
            "current_price": position.current_price,
            "average_cost": position.average_cost,
            "position_weight": position.position_weight,
            "profit_loss_ratio": position.profit_loss_ratio,
            "position_layer": position.position_layer,
            "layer_confidence": position.layer_confidence,
            "layer_reason": position.layer_reason,
            "snapshot_time": position.snapshot_time.isoformat(),
        },
        "recent_news": [_news_context(item) for item in news_items],
        "profile": {
            "confidence": profile.confidence if profile else "未知",
            "tags": profile.tags if profile else [],
            "ratios": {
                "core": profile.core_position_ratio if profile else 0,
                "mid": profile.mid_position_ratio if profile else 0,
                "trade": profile.trade_position_ratio if profile else 0,
                "option": profile.option_position_ratio if profile else 0,
            },
        },
        "guardrails": {
            "forbidden_phrases": ["立即买入", "立即卖出", "必涨", "必跌", "稳赚", "满仓"],
            "decision_boundary": "只辅助决策，不自动下单",
            "analysis_basis": "仅基于当前持仓快照分析",
        },
    }


def _news_context(item) -> dict[str, Any]:
    return {
        "title": item.title,
        "news_sub_type": item.news_sub_type,
        "source": item.source,
        "publish_time": item.publish_time.isoformat() if item.publish_time else None,
        "url": item.url,
    }


def _local_reasoning(context: dict[str, Any]) -> dict[str, Any]:
    position = context["position"]
    layer = position["position_layer"]
    pl_ratio = position["profit_loss_ratio"]
    weight = position["position_weight"]

    if layer == "短期交易仓" and pl_ratio <= -0.08:
        recommendation = "止损关注"
        conclusion = "该标的属于短期交易仓且浮亏扩大，需要优先复核原始交易理由是否仍成立。"
    elif weight >= 0.25:
        recommendation = "减仓关注"
        conclusion = "该标的仓位占比较高，应优先检查组合集中度和回撤承受能力。"
    elif layer == "遗留观察仓":
        recommendation = "观察"
        conclusion = "该持仓更像遗留观察仓，重点不是短线止损，而是确认是否仍有继续持有的理由。"
    else:
        recommendation = "继续持有"
        conclusion = "当前没有触发高优先级风险条件，可继续跟踪关键价位和持仓理由。"

    return _sanitize_output(
        {
            "recommendation": recommendation,
            "conclusion": conclusion,
            "reasons": [
                f"仓位类型为{layer}，分析逻辑按分层仓位处理。",
                f"当前仓位占比约 {weight:.1%}，浮动盈亏约 {pl_ratio:.1%}。",
                "分析直接采用当前持仓快照中的价格、成本、仓位和盈亏数据。",
            ],
            "risks": [
                "持仓快照无法覆盖未来的市场变化，结论应结合后续价格与事件复核。",
                "单一规则无法替代完整基本面和事件信息。",
            ],
            "invalid_conditions": [
                "关键数据刷新后与当前快照明显不一致。",
                "仓位类型被用户手动修正或交易目的发生变化。",
            ],
            "missing_data": [],
        }
    )


def _call_deepseek(
    context: dict[str, Any],
    api_key: str,
    model: str,
    base_url: str,
    system_instruction: str = SYSTEM_INSTRUCTION,
) -> dict[str, Any]:
    return call_llm_chat_completion(context, api_key, model, base_url, system_instruction)


def call_llm_chat_completion(
    context: dict[str, Any],
    api_key: str,
    model: str,
    base_url: str,
    system_instruction: str = SYSTEM_INSTRUCTION,
    timeout: int = 20,
) -> dict[str, Any]:
    payload = build_deepseek_request_payload(context, model, system_instruction)
    return call_llm_payload(payload, api_key, base_url, timeout)


def _extract_chat_text(data: dict[str, Any]) -> str:
    choices = data.get("choices", [])
    if not choices:
        return ""
    content = choices[0].get("message", {}).get("content", "")
    if isinstance(content, str):
        return content.strip()
    return json.dumps(content, ensure_ascii=False)


def _sanitize_output(output: dict[str, Any]) -> dict[str, Any]:
    forbidden = ["立即买入", "立即卖出", "必涨", "必跌", "稳赚", "满仓"]
    text = json.dumps(output, ensure_ascii=False)
    for phrase in forbidden:
        text = text.replace(phrase, "关注")
    return normalize_ai_output(json.loads(text))


def normalize_ai_output(output: Any) -> dict[str, Any]:
    source = output if isinstance(output, dict) else {"conclusion": output}
    normalized = dict(source)
    normalized["recommendation"] = _ai_text(source.get("recommendation"), "观察", prefer_applicable=True)
    normalized["conclusion"] = _ai_text(source.get("conclusion"), "暂无结论")
    for field in ("reasons", "risks", "invalid_conditions", "missing_data"):
        normalized[field] = _ai_text_list(source.get(field))
    return normalized


def _ai_text(value: Any, fallback: str = "", prefer_applicable: bool = False) -> str:
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, dict):
        candidates = [_ai_text(item) for item in value.values()]
        candidates = [item for item in candidates if item]
        if prefer_applicable:
            applicable = [item for item in candidates if not item.startswith(("不适用", "无"))]
            if applicable:
                return applicable[0]
        return candidates[0] if candidates else fallback
    if isinstance(value, list):
        items = [_ai_text(item) for item in value]
        return "；".join(item for item in items if item) or fallback
    if value is None:
        return fallback
    return str(value)


def _ai_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else list(value.values()) if isinstance(value, dict) else [value]
    return [text for item in items if (text := _ai_text(item))]
