from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.futu_adapter import FutuReadOnlyAdapter
from app.models import Deal, DecisionCard, PositionSnapshot, QuoteSummary, TradeReview


REVIEW_MOVE_THRESHOLD = 0.03
INTENT_TAG_CATEGORIES = ("trend", "market", "fundamental", "emotion")


def refresh_trade_reviews(db: Session, fetch_market_data: bool = False) -> None:
    deals = list(db.scalars(select(Deal).order_by(Deal.deal_time.desc(), Deal.id.desc())).all())
    positions = _latest_positions_by_code(db)
    kline_cache: dict[tuple[str, str], float | None] = {}
    for deal in deals:
        review = db.scalar(
            select(TradeReview).where(
                TradeReview.account_id == deal.account_id,
                TradeReview.deal_id == deal.deal_id,
            )
        )
        if not review:
            review = TradeReview(
                review_id=f"trade_review_{uuid4().hex}",
                account_id=deal.account_id,
                deal_id=deal.deal_id,
                created_at=datetime.now(timezone.utc),
            )
        apply_trade_review_facts(db, review, deal, positions.get(deal.code), kline_cache, fetch_market_data)
        db.add(review)


def apply_trade_review_facts(
    db: Session,
    review: TradeReview,
    deal: Deal,
    position: Optional[PositionSnapshot] = None,
    kline_cache: dict[tuple[str, str], float | None] | None = None,
    fetch_market_data: bool = False,
) -> TradeReview:
    now = datetime.now(timezone.utc)
    if fetch_market_data:
        one_day_price = _price_after(db, deal.code, deal.deal_time, days=1, kline_cache=kline_cache, fetch_market_data=True)
        five_day_price = _price_after(db, deal.code, deal.deal_time, days=5, kline_cache=kline_cache, fetch_market_data=True)
    else:
        one_day_price = review.one_day_price if review.one_day_price is not None else _price_after(db, deal.code, deal.deal_time, days=1)
        five_day_price = review.five_day_price if review.five_day_price is not None else _price_after(db, deal.code, deal.deal_time, days=5)
    latest_price = _latest_price(db, deal.code)
    one_day_return = _trade_return(deal.side, deal.price, one_day_price)
    five_day_return = _trade_return(deal.side, deal.price, five_day_price)
    latest_return = _trade_return(deal.side, deal.price, latest_price)
    result_label = classify_trade_result(deal.side, one_day_return, five_day_return, latest_return)
    user_note = review.user_note or ""
    intent_tags = normalize_intent_tags(review.intent_tags or {})
    intent_plan = normalize_intent_plan(review.intent_plan or {})
    discipline_label = _discipline_label(db, deal, user_note, intent_tags)

    review.order_id = deal.order_id
    review.code = deal.code
    review.side = deal.side
    review.price = deal.price
    review.quantity = deal.quantity
    review.deal_time = deal.deal_time
    review.one_day_price = one_day_price
    review.five_day_price = five_day_price
    review.latest_price = latest_price
    review.one_day_return = one_day_return
    review.five_day_return = five_day_return
    review.latest_return = latest_return
    review.result_label = result_label
    review.discipline_label = discipline_label
    review.confidence = _confidence(one_day_return, five_day_return)
    review.fact_summary = {
        "position_layer": position.position_layer if position else "",
        "position_layer_reason": position.layer_reason if position else "",
        "basis": "事实标签由成交价和成交后 1/5 日 K 线收盘价按规则生成；K 线缺失时回退本地行情快照。AI 只解释，不改写事实。",
        "threshold": REVIEW_MOVE_THRESHOLD,
        "intent_tag_count": sum(len(tags) for tags in intent_tags.values()),
    }
    review.user_note = user_note
    review.intent_tags = intent_tags
    review.intent_plan = intent_plan
    review.ai_commentary = build_trade_review_commentary(review)
    review.generated_by = "rule_local_ai"
    review.updated_at = now
    return review


def trade_review_payload(
    db: Session,
    code: str | None = None,
    side: str | None = None,
    label: str | None = None,
    account_id: str | None = None,
    fetch_market_data: bool = False,
) -> dict:
    refresh_trade_reviews(db, fetch_market_data=fetch_market_data)
    db.commit()
    query = select(TradeReview).order_by(TradeReview.deal_time.desc(), TradeReview.created_at.desc())
    if code:
        query = query.where(TradeReview.code == code)
    if side:
        query = query.where(TradeReview.side == side)
    if label:
        query = query.where(TradeReview.result_label == label)
    if account_id and account_id != "all":
        query = query.where(TradeReview.account_id == account_id)
    items = list(db.scalars(query.limit(200)).all())
    return {
        "empty": not items,
        "summary": _summary(items),
        "items": [_to_dict(item) for item in items],
    }


def update_trade_review_intent(db: Session, review_id: str, payload: dict) -> TradeReview | None:
    review = db.get(TradeReview, review_id)
    if not review:
        return None
    if "note" in payload:
        review.user_note = str(payload.get("note") or "").strip()[:1000]
    if "tags" in payload:
        review.intent_tags = normalize_intent_tags(payload.get("tags") or {})
    if "plan" in payload:
        review.intent_plan = normalize_intent_plan(payload.get("plan") or {})
    deal = db.scalar(select(Deal).where(Deal.account_id == review.account_id, Deal.deal_id == review.deal_id))
    if deal:
        apply_trade_review_facts(db, review, deal, _latest_positions_by_code(db).get(deal.code), {}, False)
    else:
        review.discipline_label = _discipline_from_intent(review.user_note, review.intent_tags or {})
        review.ai_commentary = build_trade_review_commentary(review)
        review.updated_at = datetime.now(timezone.utc)
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def classify_trade_result(
    side: str,
    one_day_return: float | None,
    five_day_return: float | None,
    latest_return: float | None,
) -> str:
    side_text = side.upper()
    score = five_day_return if five_day_return is not None else one_day_return
    if score is None:
        score = latest_return
    if score is None:
        return "等待验证"
    if "BUY" in side_text:
        if score <= -REVIEW_MOVE_THRESHOLD:
            return "买到短线高位" if five_day_return is not None else "买后承压"
        return "计划内买入" if score >= 0 else "买后承压"
    if "SELL" in side_text:
        if score <= -REVIEW_MOVE_THRESHOLD:
            return "卖飞"
        return "计划内卖出" if score >= 0 else "过早卖出待确认"
    return "等待验证"


def build_trade_review_commentary(review: TradeReview) -> str:
    side_name = "买入" if "BUY" in review.side.upper() else "卖出" if "SELL" in review.side.upper() else "成交"
    user_note = review.user_note or ""
    tag_text = _intent_tag_text(review.intent_tags or {})
    plan_text = _intent_plan_text(review.intent_plan or {})
    note_part = f"你当时记录的理由是“{user_note}”。" if user_note else "这笔交易还没有补充文字理由，纪律判断会先保持保守。"
    tag_part = f"意图标签显示：{tag_text}。" if tag_text else "意图标签还未记录。"
    plan_part = f"计划信息：{plan_text}。" if plan_text else ""
    result_part = _result_sentence(review)
    discipline_part = (
        "先按计划复核，再看盈亏结果；结果赚钱不代表动作一定稳，结果承压也不等于当时一定错。"
    )
    return f"这笔{side_name}当前标记为“{review.result_label}”。{result_part}{tag_part}{plan_part}{note_part}{discipline_part}"


def normalize_intent_tags(value: dict) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for category in INTENT_TAG_CATEGORIES:
        raw_tags = value.get(category, []) if isinstance(value, dict) else []
        if not isinstance(raw_tags, list):
            raw_tags = []
        seen = set()
        tags = []
        for tag in raw_tags:
            text = str(tag).strip()
            if text and text not in seen:
                tags.append(text[:40])
                seen.add(text)
        normalized[category] = tags
    return normalized


def normalize_intent_plan(value: dict) -> dict[str, str]:
    if not isinstance(value, dict):
        value = {}
    allowed_keys = [
        "holding_period",
        "stop_loss_type",
        "take_profit_type",
        "stop_loss_price",
        "take_profit_price",
    ]
    return {key: str(value.get(key) or "").strip()[:80] for key in allowed_keys}


def _result_sentence(review: TradeReview) -> str:
    one_day = _format_optional_percent(review.one_day_return)
    five_day = _format_optional_percent(review.five_day_return)
    latest = _format_optional_percent(review.latest_return)
    return f"成交后 1 日表现为 {one_day}，5 日表现为 {five_day}，最新可用表现为 {latest}。"


def _price_after(
    db: Session,
    code: str,
    deal_time: datetime | None,
    days: int,
    kline_cache: dict[tuple[str, str], float | None] | None = None,
    fetch_market_data: bool = False,
) -> float | None:
    if not deal_time:
        return None
    target = deal_time + timedelta(days=days)
    target_for_compare = target if target.tzinfo else target.replace(tzinfo=timezone.utc)
    if target_for_compare > datetime.now(timezone.utc):
        return None

    if fetch_market_data:
        kline_price = _daily_kline_price_after(code, target, kline_cache)
        if kline_price is not None:
            return kline_price

    quote = db.scalar(
        select(QuoteSummary)
        .where(QuoteSummary.code == code, QuoteSummary.quote_time >= target)
        .order_by(QuoteSummary.quote_time.asc())
        .limit(1)
    )
    return quote.current_price if quote else None


def _daily_kline_price_after(
    code: str,
    target: datetime,
    kline_cache: dict[tuple[str, str], float | None] | None,
) -> float | None:
    cache = kline_cache if kline_cache is not None else {}
    key = (code, target.date().isoformat())
    if key not in cache:
        try:
            cache[key] = FutuReadOnlyAdapter().fetch_daily_close_after(code, target)
        except Exception:
            cache[key] = None
    return cache[key]


def _latest_price(db: Session, code: str) -> float | None:
    quote = db.scalar(
        select(QuoteSummary)
        .where(QuoteSummary.code == code)
        .order_by(QuoteSummary.quote_time.desc())
        .limit(1)
    )
    return quote.current_price if quote else None


def _trade_return(side: str, deal_price: float, ref_price: float | None) -> float | None:
    if not deal_price or ref_price is None:
        return None
    raw_return = ref_price / deal_price - 1
    if "SELL" in side.upper():
        return -raw_return
    return raw_return


def _discipline_label(db: Session, deal: Deal, user_note: str, intent_tags: dict[str, list[str]]) -> str:
    if (user_note or "").strip() or any(intent_tags.values()):
        return _discipline_from_intent(user_note, intent_tags)
    card = db.scalar(
        select(DecisionCard)
        .where(DecisionCard.code == deal.code)
        .order_by(DecisionCard.data_time.desc())
        .limit(1)
    )
    if card:
        return "有建议记录"
    return "待补交易意图"


def _discipline_from_intent(note: str, intent_tags: dict[str, list[str]]) -> str:
    return "已记录交易意图" if note.strip() or any(intent_tags.values()) else "待补交易意图"


def _confidence(one_day_return: float | None, five_day_return: float | None) -> str:
    if five_day_return is not None:
        return "高"
    if one_day_return is not None:
        return "中"
    return "低"


def _latest_positions_by_code(db: Session) -> dict[str, PositionSnapshot]:
    subq = (
        select(PositionSnapshot.code, func.max(PositionSnapshot.snapshot_time).label("latest"))
        .group_by(PositionSnapshot.code)
        .subquery()
    )
    positions = db.scalars(
        select(PositionSnapshot).join(
            subq,
            (PositionSnapshot.code == subq.c.code) & (PositionSnapshot.snapshot_time == subq.c.latest),
        )
    ).all()
    return {item.code: item for item in positions}


def _summary(items: list[TradeReview]) -> dict:
    risk_labels = {"卖飞", "买到短线高位", "买后承压"}
    plan_labels = {"计划内买入", "计划内卖出"}
    return {
        "trade_count": len(items),
        "waiting_count": len([item for item in items if item.result_label == "等待验证"]),
        "risk_count": len([item for item in items if item.result_label in risk_labels]),
        "planned_count": len([item for item in items if item.result_label in plan_labels or item.discipline_label in {"已记录交易意图", "有建议记录"}]),
        "missing_note_count": len([item for item in items if not item.user_note and not any((item.intent_tags or {}).values())]),
        "missing_intent_count": len([item for item in items if not item.user_note and not any((item.intent_tags or {}).values())]),
    }


def _to_dict(item: TradeReview) -> dict:
    return {
        "review_id": item.review_id,
        "account_id": item.account_id,
        "deal_id": item.deal_id,
        "order_id": item.order_id,
        "code": item.code,
        "side": item.side,
        "price": item.price,
        "quantity": item.quantity,
        "deal_time": item.deal_time,
        "one_day_price": item.one_day_price,
        "five_day_price": item.five_day_price,
        "latest_price": item.latest_price,
        "one_day_return": item.one_day_return,
        "five_day_return": item.five_day_return,
        "latest_return": item.latest_return,
        "result_label": item.result_label,
        "discipline_label": item.discipline_label,
        "confidence": item.confidence,
        "fact_summary": item.fact_summary,
        "ai_commentary": item.ai_commentary,
        "user_note": item.user_note,
        "intent_tags": normalize_intent_tags(item.intent_tags or {}),
        "intent_plan": normalize_intent_plan(item.intent_plan or {}),
        "generated_by": item.generated_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "待验证"
    return f"{value:.1%}"


def _intent_tag_text(intent_tags: dict) -> str:
    names = {
        "trend": "趋势",
        "market": "行情",
        "fundamental": "基本面",
        "emotion": "情绪",
    }
    parts = []
    for category in INTENT_TAG_CATEGORIES:
        tags = normalize_intent_tags(intent_tags).get(category, [])
        if tags:
            parts.append(f"{names[category]}={ '、'.join(tags) }")
    return "；".join(parts)


def _intent_plan_text(intent_plan: dict) -> str:
    plan = normalize_intent_plan(intent_plan)
    names = {
        "holding_period": "计划持有周期",
        "stop_loss_type": "计划止损类型",
        "take_profit_type": "计划止盈类型",
        "stop_loss_price": "计划止损价",
        "take_profit_price": "计划止盈价",
    }
    return "；".join(f"{names[key]}={value}" for key, value in plan.items() if value)
