from datetime import datetime, timedelta, timezone

from app.services.freshness import alert_cooldown_seconds, evaluate_freshness


def test_quote_freshness_stales_after_five_minutes():
    result = evaluate_freshness("quote", datetime.now(timezone.utc) - timedelta(minutes=6))
    assert result["status"] == "stale"
    assert "行情过期" in result["message"]


def test_missing_data_is_explicit():
    result = evaluate_freshness("deal", None)
    assert result["status"] == "missing"
    assert result["message"] == "数据缺失"


def test_alert_cooldown_defaults_to_30_minutes_for_risk():
    assert alert_cooldown_seconds("止损关注") == 30 * 60
