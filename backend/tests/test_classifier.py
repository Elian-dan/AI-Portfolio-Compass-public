from datetime import datetime, timedelta, timezone

from app.services.classifier import PositionFacts, classify_position


def test_manual_override_wins():
    result = classify_position(PositionFacts(code="US.QQQ", manual_layer="核心长期仓"))
    assert result.layer == "核心长期仓"
    assert result.source == "user"


def test_option_priority():
    result = classify_position(PositionFacts(code="US.AAPL260117C250000", asset_type="option", manual_layer=None))
    assert result.layer == "期权仓"


def test_legacy_no_buy_record():
    result = classify_position(PositionFacts(code="HK.03887", buy_count=0, position_weight=0.05))
    assert result.layer == "遗留观察仓"


def test_short_term_round_trip():
    now = datetime.now(timezone.utc)
    result = classify_position(
        PositionFacts(
            code="US.TSLL",
            first_buy_time=now - timedelta(days=3),
            buy_count=1,
            sell_count=1,
            has_round_trip=True,
            now=now,
        )
    )
    assert result.layer == "短期交易仓"


def test_long_holding_core():
    now = datetime.now(timezone.utc)
    result = classify_position(
        PositionFacts(code="US.NVDA", first_buy_time=now - timedelta(days=220), buy_count=3, now=now)
    )
    assert result.layer == "核心长期仓"
