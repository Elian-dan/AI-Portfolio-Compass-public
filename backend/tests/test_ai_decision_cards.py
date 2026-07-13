from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.main import _merge_duplicate_detail_cards
from app.models import AccountSnapshot, DecisionCard, PositionSnapshot
from app.services import ai_decision_cards
from app.services.sync import latest_cards


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _position(code: str, layer: str, weight: float, pl_ratio: float) -> PositionSnapshot:
    now = datetime.now(timezone.utc)
    return PositionSnapshot(
        account_id="1",
        code=code,
        name=code,
        market=code.split(".")[0],
        asset_type="stock",
        quantity=1,
        average_cost=100,
        current_price=100 * (1 + pl_ratio),
        raw_market_value=weight * 100000,
        raw_currency="HKD",
        normalized_market_value=weight * 100000,
        normalized_currency="HKD",
        exchange_rate_to_base=1,
        position_weight=weight,
        profit_loss_ratio=pl_ratio,
        position_layer=layer,
        layer_source="user",
        layer_confidence="高",
        layer_reason="test",
        snapshot_time=now,
        sync_id="sync",
    )


def _card(code: str, created_at: datetime, recommendation: str = "观察") -> DecisionCard:
    return DecisionCard(
        card_id=f"card_{code}_{created_at.timestamp()}",
        code=code,
        position_layer="中期配置仓",
        recommendation=recommendation,
        confidence="中",
        reasons=["test"],
        risks=[],
        key_prices={},
        data_time=created_at,
        action_required=False,
        data_version=created_at.strftime("%Y%m%d%H%M%S"),
        status="正常",
        priority="P2",
        created_at=created_at,
    )


def test_latest_cards_returns_one_latest_card_per_code():
    db = _session()
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    new = datetime.now(timezone.utc)
    db.add_all([_card("US.QQQ", old), _card("US.QQQ", new), _card("US.SPCX", new)])
    db.commit()

    cards = latest_cards(db, limit=10)

    assert len([item for item in cards if item.code == "US.QQQ"]) == 1
    assert next(item for item in cards if item.code == "US.QQQ").data_version == new.strftime("%Y%m%d%H%M%S")


def test_detail_cards_merge_duplicate_history_only():
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    middle = datetime.now(timezone.utc) - timedelta(hours=1)
    new = datetime.now(timezone.utc)
    first = _card("US.QQQ", old, "观察")
    second = _card("US.QQQ", middle, "观察")
    different = _card("US.QQQ", new, "减仓关注")

    cards = _merge_duplicate_detail_cards([first, second, different])

    assert len(cards) == 2
    merged = next(item for item in cards if item.recommendation == "观察")
    assert merged.merged_count == 2
    assert merged.merged_first_data_time == old
    assert merged.merged_last_data_time == middle


def test_ai_generation_passes_layer_specific_framework_and_sanitizes(monkeypatch):
    db = _session()
    db.add(AccountSnapshot(account_id="1", total_assets=100000, cash=1000, market_value=99000, raw_currency_values={"currency": "HKD"}, snapshot_time=datetime.now(timezone.utc), sync_id="sync"))
    db.add_all([
        _position("US.CORE", "核心长期仓", 0.3, -0.12),
        _position("US.TRADE", "短期交易仓", 0.05, -0.1),
    ])
    db.commit()
    seen_frameworks = {}

    def fake_call(context, *_args, **_kwargs):
        seen_frameworks[context["position"]["code"]] = context["analysis_framework"]
        if context["position"]["position_layer"] == "核心长期仓":
            return {
                "recommendation": "止损关注",
                "priority": "P1",
                "confidence": "中",
                "conclusion": "不要因为短期浮亏立即卖出",
                "reasons": ["重点复核长期逻辑"],
                "risks": ["组合集中度偏高"],
                "invalid_conditions": ["长期逻辑破坏"],
                "missing_data": [],
            }
        return {
            "recommendation": "止损关注",
            "priority": "P1",
            "confidence": "中",
            "conclusion": "短期交易仓需要复核交易理由",
            "reasons": ["浮亏扩大"],
            "risks": ["交易理由失效"],
            "invalid_conditions": ["日线继续走弱"],
            "missing_data": [],
        }

    monkeypatch.setattr(
        ai_decision_cards,
        "active_ai_runtime",
        lambda _db: {
            "provider": "deepseek",
            "api_key": "key",
            "has_api_key": True,
            "model": "model",
            "base_url": "https://example.com",
            "enabled": True,
        },
    )
    monkeypatch.setattr(ai_decision_cards, "_fetch_technical_summaries", lambda codes: {code: {"daily": {"status": "missing"}, "weekly": {"status": "missing"}} for code in codes})
    monkeypatch.setattr(ai_decision_cards, "call_llm_chat_completion", fake_call)

    result = ai_decision_cards.generate_ai_decision_cards(db)

    assert result["generated_count"] == 2
    assert seen_frameworks["US.CORE"]["layer"] == "核心长期仓"
    assert "不能仅因短期浮亏输出止损关注" in seen_frameworks["US.CORE"]["avoid"]
    assert seen_frameworks["US.TRADE"]["layer"] == "短期交易仓"
    core_card = db.query(DecisionCard).filter(DecisionCard.code == "US.CORE").one()
    assert core_card.recommendation != "止损关注"
    assert "立即卖出" not in str(core_card.reasons)
    assert core_card.generation_source == "ai"
