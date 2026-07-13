from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Deal, QuoteSummary, TradeReview
from app.services.trade_review import classify_trade_result, refresh_trade_reviews, update_trade_review_intent


def test_trade_review_labels_buy_pressure_and_high_entry():
    assert classify_trade_result("BUY", -0.04, None, -0.04) == "买后承压"
    assert classify_trade_result("BUY", -0.02, -0.05, -0.05) == "买到短线高位"


def test_trade_review_labels_sell_fly_and_planned_exit():
    assert classify_trade_result("SELL", -0.04, None, -0.04) == "卖飞"
    assert classify_trade_result("SELL", 0.02, 0.04, 0.04) == "计划内卖出"


def test_trade_review_waits_without_reference_price():
    assert classify_trade_result("BUY", None, None, None) == "等待验证"


def test_refresh_trade_reviews_prefers_daily_kline_close(monkeypatch):
    db = _memory_session()
    now = datetime.now(timezone.utc) - timedelta(days=6)
    db.add(
        Deal(
            deal_id="d_kline",
            order_id="o_kline",
            code="US.AMD",
            side="BUY",
            price=100,
            quantity=1,
            deal_time=now,
            market="US",
            account_id="acc1",
            raw_payload={},
        )
    )
    db.add(
        QuoteSummary(
            code="US.AMD",
            current_price=80,
            change_ratio=0,
            volume=0,
            ma_summary={},
            quote_time=now + timedelta(days=5, minutes=1),
            sync_id="stale_snapshot",
        )
    )
    db.commit()

    class FakeAdapter:
        def fetch_daily_close_after(self, code, target):
            return 110 if target.date() == (now + timedelta(days=5)).date() else 103

    monkeypatch.setattr("app.services.trade_review.FutuReadOnlyAdapter", FakeAdapter)

    refresh_trade_reviews(db, fetch_market_data=True)
    db.commit()

    review = db.scalar(select(TradeReview).where(TradeReview.deal_id == "d_kline"))
    assert review is not None
    assert review.one_day_price == 103
    assert review.five_day_price == 110
    assert round(review.five_day_return or 0, 4) == 0.1
    assert review.result_label == "计划内买入"

    refresh_trade_reviews(db)
    db.commit()
    review = db.scalar(select(TradeReview).where(TradeReview.deal_id == "d_kline"))
    assert review is not None
    assert review.one_day_price == 103
    assert review.five_day_price == 110
    assert review.result_label == "计划内买入"


def test_refresh_trade_reviews_and_note_regenerates_commentary():
    db = _memory_session()
    now = datetime.now(timezone.utc) - timedelta(days=6)
    db.add(
        Deal(
            deal_id="d1",
            order_id="o1",
            code="US.AMD",
            side="BUY",
            price=100,
            quantity=3,
            deal_time=now,
            market="US",
            account_id="acc1",
            raw_payload={},
        )
    )
    db.add(
        QuoteSummary(
            code="US.AMD",
            current_price=94,
            change_ratio=0,
            volume=0,
            ma_summary={},
            quote_time=now + timedelta(days=5, minutes=1),
            sync_id="s1",
        )
    )
    db.commit()

    refresh_trade_reviews(db)
    db.commit()

    review = db.scalar(select(TradeReview).where(TradeReview.deal_id == "d1"))
    assert review is not None
    assert review.result_label == "买到短线高位"
    assert "还没有补充文字理由" in review.ai_commentary

    updated = update_trade_review_intent(db, review.review_id, {"note": "突破前高后追入，计划做短线"})
    assert updated is not None
    assert updated.discipline_label == "已记录交易意图"
    assert "突破前高后追入" in updated.ai_commentary

    updated = update_trade_review_intent(
        db,
        review.review_id,
        {
            "tags": {
                "trend": ["突破", "趋势跟随"],
                "market": ["市场偏强"],
                "fundamental": ["高质量公司"],
                "emotion": ["FOMO"],
            },
            "plan": {"holding_period": "1-5日", "stop_loss_type": "价格止损", "stop_loss_price": "95"},
        },
    )
    assert updated is not None
    assert updated.intent_tags["trend"] == ["突破", "趋势跟随"]
    assert updated.intent_plan["holding_period"] == "1-5日"
    assert "趋势=突破、趋势跟随" in updated.ai_commentary
    assert "计划持有周期=1-5日" in updated.ai_commentary


def _memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
