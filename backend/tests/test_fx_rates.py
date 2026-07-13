from datetime import datetime, timedelta, timezone

import pytest


pytest.importorskip("sqlalchemy")

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import ExchangeRate  # noqa: E402
from app.services import fx_rates  # noqa: E402


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_fresh_cache_skips_frankfurter(monkeypatch):
    _clear_rates()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(
            ExchangeRate(
                base_currency="CNY",
                quote_currency="USD",
                rate=0.14,
                source="frankfurter",
                rate_time=now,
                fetched_at=now,
                expires_at=now + timedelta(minutes=10),
                is_stale=False,
                raw_payload={"rate": 0.14},
            )
        )
        db.commit()
        monkeypatch.setattr(fx_rates, "fetch_frankfurter_rate", lambda *_: (_ for _ in ()).throw(AssertionError("should not fetch")))

        result = fx_rates.get_rate(db, "CNY", "USD", now=now)

    assert result.rate == 0.14
    assert result.is_stale is False


def test_expired_cache_refreshes_and_writes(monkeypatch):
    _clear_rates()
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(fx_rates, "fetch_frankfurter_rate", lambda base, quote: {"rate": 0.15, "date": "2026-07-08"})
    with SessionLocal() as db:
        db.add(
            ExchangeRate(
                base_currency="CNY",
                quote_currency="USD",
                rate=0.14,
                source="frankfurter",
                rate_time=now - timedelta(days=1),
                fetched_at=now - timedelta(hours=1),
                expires_at=now - timedelta(minutes=1),
                is_stale=False,
                raw_payload={"rate": 0.14},
            )
        )
        db.commit()

        result = fx_rates.get_rate(db, "CNY", "USD", now=now)

    assert result.rate == 0.15
    assert result.is_stale is False


def test_failed_fetch_uses_24h_cache_as_stale(monkeypatch):
    _clear_rates()
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(fx_rates, "fetch_frankfurter_rate", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    with SessionLocal() as db:
        db.add(
            ExchangeRate(
                base_currency="CNY",
                quote_currency="HKD",
                rate=1.08,
                source="frankfurter",
                rate_time=now - timedelta(hours=1),
                fetched_at=now - timedelta(hours=1),
                expires_at=now - timedelta(minutes=1),
                is_stale=False,
                raw_payload={"rate": 1.08},
            )
        )
        db.commit()

        result = fx_rates.get_rate(db, "CNY", "HKD", now=now)

    assert result.rate == 1.08
    assert result.is_stale is True


def test_failed_fetch_without_cache_uses_static_fallback(monkeypatch):
    _clear_rates()
    monkeypatch.setattr(fx_rates, "fetch_frankfurter_rate", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
    with SessionLocal() as db:
        result = fx_rates.get_rate(db, "CNY", "USD", now=datetime.now(timezone.utc))

    assert result.rate == pytest.approx(1 / 7.2)
    assert result.source == "static_fallback"
    assert result.is_stale is True


def test_inverted_cache_rate_is_normalized(monkeypatch):
    _clear_rates()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(
            ExchangeRate(
                base_currency="CNY",
                quote_currency="USD",
                rate=7.8,
                source="frankfurter",
                rate_time=now,
                fetched_at=now,
                expires_at=now + timedelta(minutes=10),
                is_stale=False,
                raw_payload={"rate": 7.8},
            )
        )
        db.commit()
        monkeypatch.setattr(fx_rates, "fetch_frankfurter_rate", lambda *_: (_ for _ in ()).throw(AssertionError("should not fetch")))

        result = fx_rates.get_rate(db, "CNY", "USD", now=now)

    assert result.rate == pytest.approx(1 / 7.8)
    assert result.is_stale is False


def test_display_rates_handles_cnh_as_cny(monkeypatch):
    _clear_rates()
    monkeypatch.setattr(fx_rates, "fetch_frankfurter_rate", lambda base, quote: {"rate": 0.14 if quote == "USD" else 1.1, "date": "2026-07-08"})
    with SessionLocal() as db:
        rates, meta = fx_rates.display_rates(db, "CNY", ["CNY", "CNH", "USD", "HKD"])

    assert rates["CNY"] == 1
    assert rates["CNH"] == 1
    assert rates["USD"] == 0.14
    assert rates["HKD"] == 1.1
    assert meta["USD"]["source"] == "frankfurter"


def _clear_rates() -> None:
    with SessionLocal() as db:
        db.query(ExchangeRate).delete()
        db.commit()
