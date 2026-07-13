from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from urllib import parse, request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExchangeRate


FRANKFURTER_BASE_URL = "https://api.frankfurter.dev"
FX_CACHE_TTL = timedelta(minutes=15)
FX_STALE_TTL = timedelta(hours=24)
SOURCE = "frankfurter"


@dataclass(frozen=True)
class FxRateResult:
    currency: str
    rate: float
    source: str
    rate_time: datetime | None
    fetched_at: datetime | None
    expires_at: datetime | None
    is_stale: bool


STATIC_RATE_TO_CNY = {"CNY": 1.0, "CNH": 1.0, "USD": 7.2, "HKD": 0.92}


def display_rates(db: Session, base_currency: str, target_currencies: list[str]) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    base = normalize_currency(base_currency or "CNY")
    ordered_targets = _ordered_unique([base, *target_currencies])
    rates: dict[str, float] = {}
    meta: dict[str, dict[str, Any]] = {}
    now = _now()
    for currency in ordered_targets:
        quote = normalize_currency(currency)
        result = get_rate(db, base, quote, now=now)
        rates[currency] = result.rate
        meta[currency] = _meta(result)
    return rates, meta


def get_rate(db: Session, base_currency: str, quote_currency: str, now: datetime | None = None) -> FxRateResult:
    now = now or _now()
    base = normalize_currency(base_currency or "CNY")
    quote = normalize_currency(quote_currency or base)
    requested_quote = (quote_currency or quote).upper()
    if base == quote:
        return FxRateResult(requested_quote, 1.0, SOURCE, now, now, now + FX_CACHE_TTL, False)

    cached = _find_cached(db, base, quote)
    if cached and cached.expires_at and _aware(cached.expires_at) > now and not cached.is_stale:
        return _from_model(requested_quote, cached, False)

    try:
        payload = fetch_frankfurter_rate(base, quote)
        rate = _normalize_rate(base, quote, float(payload["rate"]))
        rate_time = _parse_rate_time(payload.get("date")) or now
        model = _upsert_rate(db, base, quote, rate, rate_time, now, payload, False)
        return _from_model(requested_quote, model, False)
    except Exception:
        if cached and cached.fetched_at and _aware(cached.fetched_at) >= now - FX_STALE_TTL:
            cached.is_stale = True
            db.add(cached)
            db.commit()
            return _from_model(requested_quote, cached, True)
        rate = _static_rate(base, quote)
        return FxRateResult(requested_quote, rate, "static_fallback", None, None, None, True)


def fetch_frankfurter_rate(base_currency: str, quote_currency: str) -> dict[str, Any]:
    url = f"{FRANKFURTER_BASE_URL}/v2/rate/{parse.quote(base_currency)}/{parse.quote(quote_currency)}"
    http_request = request.Request(url, headers={"User-Agent": "AI-Portfolio-Compass/0.1"})
    with request.urlopen(http_request, timeout=5) as response:  # nosec B310 - URL is fixed to Frankfurter.
        payload = json.loads(response.read().decode("utf-8"))
    if "rate" not in payload:
        raise RuntimeError("Frankfurter response missing rate")
    return payload


def normalize_currency(currency: str) -> str:
    text = str(currency or "").strip().upper()
    if text == "CNH":
        return "CNY"
    return text or "CNY"


def _find_cached(db: Session, base: str, quote: str) -> ExchangeRate | None:
    return db.scalar(
        select(ExchangeRate).where(
            ExchangeRate.base_currency == base,
            ExchangeRate.quote_currency == quote,
            ExchangeRate.source == SOURCE,
        )
    )


def _upsert_rate(
    db: Session,
    base: str,
    quote: str,
    rate: float,
    rate_time: datetime,
    fetched_at: datetime,
    payload: dict[str, Any],
    is_stale: bool,
) -> ExchangeRate:
    model = _find_cached(db, base, quote)
    if model is None:
        model = ExchangeRate(base_currency=base, quote_currency=quote, source=SOURCE)
    model.rate = _normalize_rate(base, quote, rate)
    model.rate_time = rate_time
    model.fetched_at = fetched_at
    model.expires_at = fetched_at + FX_CACHE_TTL
    model.is_stale = is_stale
    model.raw_payload = payload
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _from_model(requested_currency: str, model: ExchangeRate, is_stale: bool) -> FxRateResult:
    rate = _normalize_rate(model.base_currency, model.quote_currency, model.rate)
    return FxRateResult(
        requested_currency,
        rate,
        model.source,
        model.rate_time,
        model.fetched_at,
        model.expires_at,
        is_stale,
    )


def _meta(result: FxRateResult) -> dict[str, Any]:
    return {
        "source": result.source,
        "rate_time": _iso(result.rate_time),
        "fetched_at": _iso(result.fetched_at),
        "expires_at": _iso(result.expires_at),
        "is_stale": result.is_stale,
    }


def _static_rate(base: str, quote: str) -> float:
    base_to_cny = STATIC_RATE_TO_CNY.get(base, 1.0)
    quote_to_cny = STATIC_RATE_TO_CNY.get(quote, 1.0)
    return base_to_cny / quote_to_cny if quote_to_cny else 1.0


def _normalize_rate(base: str, quote: str, rate: float) -> float:
    if rate <= 0:
        return _static_rate(base, quote)
    expected = _static_rate(base, quote)
    if not expected:
        return rate
    inverted = 1 / rate
    rate_error = abs(rate / expected - 1)
    inverted_error = abs(inverted / expected - 1)
    if rate_error > 2 and inverted_error < 0.35:
        return inverted
    return rate


def _parse_rate_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware(value).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ordered_unique(currencies: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for currency in currencies:
        text = str(currency or "").strip().upper()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
