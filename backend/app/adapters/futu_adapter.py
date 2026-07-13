from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import time
from typing import Any
from urllib import parse, request

from app.config import get_settings
from app.services.providers import normalize_market


@dataclass
class FutuSnapshot:
    accounts: list[dict[str, Any]]
    account_snapshots: list[dict[str, Any]]
    positions: list[dict[str, Any]]
    deals: list[dict[str, Any]]
    watchlist: list[dict[str, Any]]
    quotes: list[dict[str, Any]]
    news: list[dict[str, Any]]
    news_error: str = ""


class FutuReadOnlyAdapter:
    """Thin read-only adapter around futu-api.

    This class intentionally exposes no order, cancel, modify, or unlock methods.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def health(self) -> tuple[bool, str]:
        try:
            futu = self._import_futu()
            ctx = futu.OpenQuoteContext(host=self.settings.futu_host, port=self.settings.futu_port)
            ret, data = ctx.get_global_state()
            ctx.close()
            if ret == futu.RET_OK:
                return True, "connected"
            return False, str(data)
        except Exception as exc:  # pragma: no cover - depends on OpenD
            return False, _safe_error(exc)

    def account_access(self) -> tuple[bool, int, str]:
        """Check whether the logged-in OpenD session can read trading accounts."""
        try:
            futu = self._import_futu()
            accounts = self._fetch_accounts(futu)
            return True, len(accounts), "账户列表读取成功"
        except Exception as exc:  # pragma: no cover - depends on local OpenD
            return False, 0, _safe_error(exc)

    def fetch_snapshot(self) -> FutuSnapshot:
        futu = self._import_futu()
        now = datetime.now(timezone.utc)
        accounts = self._fetch_accounts(futu)
        account_snapshots: list[dict[str, Any]] = []
        positions: list[dict[str, Any]] = []
        deals: list[dict[str, Any]] = []

        for account in accounts:
            acc_id = account["account_id"]
            market = _pick_market(account.get("markets", []))
            portfolio = self._fetch_portfolio(futu, account, market)
            account_snapshots.extend(portfolio["account_snapshots"])
            positions.extend(portfolio["positions"])
            deals.extend(self._fetch_deals(futu, acc_id, market))

        codes = [item["code"] for item in positions]
        news, news_error = self._fetch_news(futu, positions, now)
        return FutuSnapshot(
            accounts=accounts,
            account_snapshots=account_snapshots,
            positions=positions,
            deals=deals,
            watchlist=self._fetch_watchlist(futu),
            quotes=self._fetch_quotes(futu, codes, now),
            news=news,
            news_error=news_error,
        )

    def fetch_quote_summaries(self, codes: list[str]) -> list[dict[str, Any]]:
        futu = self._import_futu()
        return self._fetch_quotes(futu, codes, datetime.now(timezone.utc))

    def fetch_news_items(self, positions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
        futu = None if self.settings.news_provider.strip().lower() == "marketaux" else self._import_futu()
        return self._fetch_news(futu, positions, datetime.now(timezone.utc))

    def fetch_kline_rows(self, code: str, ktype_name: str = "K_DAY", count: int = 90) -> dict[str, Any]:
        futu = self._import_futu()
        ctx = futu.OpenQuoteContext(host=self.settings.futu_host, port=self.settings.futu_port)
        try:
            ktype = getattr(futu.KLType, ktype_name)
            ret, data, _ = ctx.request_history_kline(code, ktype=ktype, max_count=count)
            if ret != futu.RET_OK:
                return {"status": "missing", "message": str(data)[:200], "items": []}
            rows = data.to_dict("records")
            items = []
            for row in rows:
                close = _float(row.get("close"))
                if close <= 0:
                    continue
                items.append(
                    {
                        "time_key": str(row.get("time_key") or row.get("date") or ""),
                        "open": _float(row.get("open")),
                        "close": close,
                        "high": _float(row.get("high")),
                        "low": _float(row.get("low")),
                        "volume": _float(row.get("volume")),
                        "turnover": _float(row.get("turnover")),
                    }
                )
            if not items:
                return {"status": "missing", "message": "无有效 K 线数据", "items": []}
            return {"status": "available", "message": "", "items": items}
        except Exception as exc:
            return {"status": "missing", "message": _safe_error(exc), "items": []}
        finally:
            ctx.close()

    def fetch_daily_close_after(self, code: str, target: datetime) -> float | None:
        """Return the first daily K-line close on or after target's calendar date."""
        futu = self._import_futu()
        ctx = futu.OpenQuoteContext(host=self.settings.futu_host, port=self.settings.futu_port)
        try:
            start = target.date().isoformat()
            end = (target + timedelta(days=14)).date().isoformat()
            ret, data, _ = ctx.request_history_kline(
                code,
                start=start,
                end=end,
                ktype=futu.KLType.K_DAY,
                max_count=20,
            )
            if ret != futu.RET_OK:
                return None
            rows = data.to_dict("records")
            for row in rows:
                close = _float(row.get("close"))
                if close > 0:
                    return close
            return None
        finally:
            ctx.close()

    def _import_futu(self):
        try:
            import futu  # type: ignore
        except Exception as exc:  # pragma: no cover - environment specific
            raise RuntimeError(f"futu-api unavailable: {_safe_error(exc)}") from exc
        return futu

    def _fetch_accounts(self, futu) -> list[dict[str, Any]]:
        ctx = futu.OpenSecTradeContext(
            filter_trdmarket=futu.TrdMarket.NONE,
            host=self.settings.futu_host,
            port=self.settings.futu_port,
            security_firm=getattr(futu.SecurityFirm, self.settings.futu_security_firm, futu.SecurityFirm.FUTUSECURITIES),
        )
        try:
            ret, data = ctx.get_acc_list()
            if ret != futu.RET_OK:
                raise RuntimeError(str(data))
            rows = data.to_dict("records")
            return [
                {
                    "account_id": str(row.get("acc_id")),
                    "source_name": "futu",
                    "broker_provider": "futu",
                    "display_name": f"Futu {row.get('acc_id')}",
                    "institution": "Futu",
                    "import_mode": "api",
                    "enabled": True,
                    "account_type": str(row.get("acc_type", "")),
                    "trade_env": str(row.get("trd_env", self.settings.futu_trd_env)),
                    "markets": _normalize_market_auth(row.get("trdmarket_auth")),
                    "base_currency": str(row.get("currency", "HKD") or "HKD"),
                }
                for row in rows
                if str(row.get("trd_env", self.settings.futu_trd_env)).upper() == self.settings.futu_trd_env.upper()
            ]
        finally:
            ctx.close()

    def _fetch_portfolio(self, futu, account: dict[str, Any], market: str) -> dict[str, list[dict[str, Any]]]:
        acc_id = account["account_id"]
        base_currency = _normalize_currency(account.get("base_currency") or "HKD")
        ctx = futu.OpenSecTradeContext(
            filter_trdmarket=getattr(futu.TrdMarket, market, futu.TrdMarket.US),
            host=self.settings.futu_host,
            port=self.settings.futu_port,
            security_firm=getattr(futu.SecurityFirm, self.settings.futu_security_firm, futu.SecurityFirm.FUTUSECURITIES),
        )
        now = datetime.now(timezone.utc)
        try:
            trd_env = getattr(futu.TrdEnv, self.settings.futu_trd_env, futu.TrdEnv.REAL)
            ret_acc, accinfo = ctx.accinfo_query(trd_env=trd_env, acc_id=int(acc_id), refresh_cache=True)
            ret_pos, pos = ctx.position_list_query(trd_env=trd_env, acc_id=int(acc_id), refresh_cache=True)
            if ret_acc != futu.RET_OK:
                raise RuntimeError(str(accinfo))
            if ret_pos != futu.RET_OK:
                raise RuntimeError(str(pos))
            acc_row = accinfo.to_dict("records")[0] if len(accinfo) else {}
            total_assets = _float(acc_row.get("total_assets"))
            cash = _float(acc_row.get("cash"))
            market_value = _float(acc_row.get("market_val") or acc_row.get("market_value"))
            position_rows = pos.to_dict("records")
            raw_position_values: dict[str, float] = defaultdict(float)
            normalized_rows = []
            for row in position_rows:
                raw_mv = _float(row.get("market_val") or row.get("market_value"))
                code = str(row.get("code", ""))
                raw_currency = _position_currency(row, code, base_currency)
                raw_position_values[raw_currency] += raw_mv
                normalized_rows.append((row, code, raw_mv, raw_currency))
            exchange_rates = _derive_position_exchange_rates(raw_position_values, base_currency, market_value)
            positions = []
            for row, code, raw_mv, raw_currency in normalized_rows:
                exchange_rate = _exchange_rate_to_base(raw_currency, base_currency)
                if exchange_rate is None:
                    exchange_rate = exchange_rates.get(raw_currency)
                normalized_mv = raw_mv * exchange_rate if exchange_rate is not None else raw_mv
                positions.append(
                    {
                        "account_id": acc_id,
                        "code": code,
                        "name": str(row.get("stock_name", row.get("name", ""))),
                        "market": code.split(".")[0],
                        "asset_type": _infer_asset_type(code, str(row.get("stock_name", ""))),
                        "quantity": _float(row.get("qty")),
                        "average_cost": _float(row.get("average_cost") or row.get("cost_price")),
                        "current_price": _float(row.get("nominal_price") or row.get("current_price")),
                        "raw_market_value": raw_mv,
                        "raw_currency": raw_currency,
                        "normalized_market_value": normalized_mv,
                        "normalized_currency": base_currency,
                        "exchange_rate_to_base": exchange_rate,
                        "position_weight": normalized_mv / total_assets if total_assets else 0,
                        "profit_loss_ratio": _float(row.get("pl_ratio_avg_cost") or row.get("pl_ratio")) / 100,
                        "snapshot_time": now,
                    }
                )
            return {
                "account_snapshots": [
                    {
                        "account_id": acc_id,
                        "total_assets": total_assets,
                        "cash": cash,
                        "market_value": market_value,
                        "raw_currency_values": acc_row,
                        "snapshot_time": now,
                    }
                ],
                "positions": positions,
            }
        finally:
            ctx.close()

    def _fetch_deals(self, futu, acc_id: str, market: str) -> list[dict[str, Any]]:
        ctx = futu.OpenSecTradeContext(
            filter_trdmarket=getattr(futu.TrdMarket, market, futu.TrdMarket.US),
            host=self.settings.futu_host,
            port=self.settings.futu_port,
            security_firm=getattr(futu.SecurityFirm, self.settings.futu_security_firm, futu.SecurityFirm.FUTUSECURITIES),
        )
        try:
            trd_env = getattr(futu.TrdEnv, self.settings.futu_trd_env, futu.TrdEnv.REAL)
            ret, data = ctx.history_deal_list_query(trd_env=trd_env, acc_id=int(acc_id))
            if ret != futu.RET_OK:
                return []
            return [
                {
                    "deal_id": str(row.get("deal_id")),
                    "order_id": str(row.get("order_id", "")),
                    "code": str(row.get("code", "")),
                    "side": str(row.get("trd_side", "")),
                    "price": _float(row.get("price")),
                    "quantity": _float(row.get("qty")),
                    "deal_time": _parse_datetime(row.get("create_time")),
                    "market": str(row.get("code", "")).split(".")[0],
                    "account_id": acc_id,
                    "raw_payload": row,
                }
                for row in data.to_dict("records")
            ]
        finally:
            ctx.close()

    def _fetch_watchlist(self, futu) -> list[dict[str, Any]]:
        try:
            ctx = futu.OpenQuoteContext(host=self.settings.futu_host, port=self.settings.futu_port)
            ret, data = ctx.get_user_security("全部")
            ctx.close()
            if ret != futu.RET_OK:
                return []
            now = datetime.now(timezone.utc)
            return [
                {
                    "group_name": str(row.get("group_name", "全部")),
                    "code": str(row.get("code", "")),
                    "name": str(row.get("name", "")),
                    "source": "futu",
                    "updated_at": now,
                }
                for row in data.to_dict("records")
            ]
        except Exception:
            return []

    def _fetch_quotes(self, futu, codes: list[str], now: datetime) -> list[dict[str, Any]]:
        if not codes:
            return []
        ctx = futu.OpenQuoteContext(host=self.settings.futu_host, port=self.settings.futu_port)
        try:
            ret, data = ctx.get_market_snapshot(codes[:400])
            if ret != futu.RET_OK:
                return []
            return [
                {
                    "code": str(row.get("code", "")),
                    "provider": "futu",
                    "market": normalize_market(str(row.get("code", "")).split(".")[0]),
                    "exchange": str(row.get("code", "")).split(".")[0],
                    "is_delayed": False,
                    "license_note": "Futu / moomoo OpenD 账户授权行情；使用与缓存需遵守券商许可。",
                    "current_price": _float(row.get("last_price")),
                    "change_ratio": _float(row.get("change_rate")) / 100,
                    "volume": _float(row.get("volume")),
                    "ma_summary": {},
                    "support_price": None,
                    "resistance_price": None,
                    "quote_time": now,
                }
                for row in data.to_dict("records")
            ]
        finally:
            ctx.close()

    def _fetch_news(self, futu, positions: list[dict[str, Any]], now: datetime) -> tuple[list[dict[str, Any]], str]:
        provider = self.settings.news_provider.strip().lower()
        if provider == "marketaux":
            return self._fetch_marketaux_news(positions, now)
        if provider not in {"", "futu"}:
            return [], f"不支持的 NEWS_PROVIDER：{self.settings.news_provider}"
        return self._fetch_futu_news(futu, positions, now)

    def _fetch_marketaux_news(self, positions: list[dict[str, Any]], now: datetime) -> tuple[list[dict[str, Any]], str]:
        token = self.settings.marketaux_api_token.strip()
        if not token:
            return [], "未配置 MARKETAUX_API_TOKEN"

        us_positions = [item for item in positions if str(item.get("code", "")).startswith("US.")]
        if not us_positions:
            return [], "Marketaux 当前仅同步美股代码"

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        first_error = ""
        published_after = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
        for index, position in enumerate(us_positions):
            if index:
                time.sleep(0.25)
            code = str(position.get("code", ""))
            ticker = code.split(".", 1)[1]
            params = parse.urlencode(
                {
                    "api_token": token,
                    "symbols": ticker,
                    "filter_entities": "true",
                    "language": "en",
                    "limit": "3",
                    "published_after": published_after,
                }
            )
            url = f"https://api.marketaux.com/v1/news/all?{params}"
            try:
                req = request.Request(url, headers={"User-Agent": "ai-stock-agent/0.1"})
                with request.urlopen(req, timeout=12) as resp:  # nosec - user configured market data source
                    payload = json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                first_error = first_error or f"Marketaux 请求失败：{_safe_error(exc)}"
                continue

            if isinstance(payload, dict) and payload.get("error"):
                first_error = first_error or str(payload.get("error"))[:300]
                continue
            for item in payload.get("data", []) if isinstance(payload, dict) else []:
                title = str(item.get("title", "")).strip()
                article_url = str(item.get("url", "")).strip()
                publish_time = _parse_datetime(item.get("published_at"))
                fingerprint = article_url or f"{title}:{publish_time}"
                key = (code, fingerprint)
                if not title or key in seen:
                    continue
                seen.add(key)
                source = item.get("source") or ""
                rows.append(
                    {
                        "news_id": _news_id(code, title, article_url, publish_time),
                        "code": code,
                        "provider": "marketaux",
                        "market": normalize_market(code.split(".")[0]),
                        "news_type": "news",
                        "title": title,
                        "news_sub_type": "NEWS",
                        "source": str(source),
                        "publish_time": publish_time,
                        "view_count": 0,
                        "related_securities": _jsonable(item.get("entities")),
                        "url": article_url,
                        "fetched_at": now,
                    }
                )

        if rows:
            return rows, ""
        return [], first_error or "Marketaux 未返回最近 3 天美股资讯"

    def _fetch_futu_news(self, futu, positions: list[dict[str, Any]], now: datetime) -> tuple[list[dict[str, Any]], str]:
        if not positions:
            return [], ""
        try:
            news_sub_type = getattr(futu.NewsSubType, "ALL")
            ctx = futu.OpenQuoteContext(host=self.settings.futu_host, port=self.settings.futu_port)
        except Exception as exc:
            return [], f"富途资讯接口初始化失败：{_safe_error(exc)}"

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        first_error = ""
        try:
            for index, position in enumerate(positions):
                if index:
                    time.sleep(3.1)
                code = str(position.get("code", ""))
                keyword = _news_keyword(position)
                if not code or not keyword or not hasattr(ctx, "get_search_news"):
                    if not hasattr(ctx, "get_search_news"):
                        first_error = first_error or "当前 OpenD/SDK 未提供 get_search_news"
                    continue
                try:
                    ret, data = ctx.get_search_news(keyword, 8, news_sub_type=news_sub_type)
                    if ret != futu.RET_OK:
                        first_error = first_error or str(data)
                        continue
                    for row in data.to_dict("records"):
                        title = str(row.get("title", "")).strip()
                        url = str(row.get("url", "")).strip()
                        publish_time = _parse_datetime(row.get("publish_time"))
                        fingerprint = url or f"{title}:{publish_time}"
                        key = (code, fingerprint)
                        if not title or key in seen:
                            continue
                        seen.add(key)
                        rows.append(
                            {
                                "news_id": _news_id(code, title, url, publish_time),
                                "code": code,
                                "provider": "futu",
                                "market": normalize_market(code.split(".")[0]),
                                "news_type": "news",
                                "title": title,
                                "news_sub_type": str(row.get("news_sub_type", "")),
                                "source": str(row.get("source", "")),
                                "publish_time": publish_time,
                                "view_count": int(_float(row.get("view_count"))),
                                "related_securities": _jsonable(row.get("related_securities")),
                                "url": url,
                                "fetched_at": now,
                            }
                        )
                except Exception as exc:
                    first_error = first_error or _safe_error(exc)
                    continue
        finally:
            ctx.close()
        return rows, first_error

    def fetch_technical_summaries(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        futu = self._import_futu()
        ctx = futu.OpenQuoteContext(host=self.settings.futu_host, port=self.settings.futu_port)
        try:
            result: dict[str, dict[str, Any]] = {}
            for code in codes:
                result[code] = {
                    "daily": self._fetch_kline_summary(futu, ctx, code, "K_DAY", 120),
                    "weekly": self._fetch_kline_summary(futu, ctx, code, "K_WEEK", 104),
                }
            return result
        finally:
            ctx.close()

    def _fetch_kline_summary(self, futu, ctx, code: str, ktype_name: str, count: int) -> dict[str, Any]:
        try:
            ktype = getattr(futu.KLType, ktype_name)
            ret, data, _ = ctx.request_history_kline(code, ktype=ktype, max_count=count)
            if ret != futu.RET_OK:
                return {"status": "missing", "message": str(data)[:200]}
            rows = data.to_dict("records")
            closes = [_float(row.get("close")) for row in rows if _float(row.get("close")) > 0]
            if not closes:
                return {"status": "missing", "message": "无有效收盘价"}
            return _summarize_closes(closes)
        except Exception as exc:
            return {"status": "missing", "message": _safe_error(exc)}


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:300]


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_currency(value: Any) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "HK": "HKD",
        "HONG KONG DOLLAR": "HKD",
        "US": "USD",
        "UNITED STATES DOLLAR": "USD",
        "CN": "CNH",
        "CNY": "CNH",
        "RMB": "CNH",
        "YUAN": "CNH",
    }
    return aliases.get(text, text or "HKD")


def _position_currency(row: dict[str, Any], code: str, default_currency: str) -> str:
    for key in ("currency", "stock_currency", "trd_currency"):
        if row.get(key):
            return _normalize_currency(row.get(key))
    market = code.split(".")[0].upper()
    market_currency = {
        "US": "USD",
        "HK": "HKD",
        "SH": "CNH",
        "SZ": "CNH",
        "CN": "CNH",
        "SG": "SGD",
        "JP": "JPY",
        "AU": "AUD",
        "CA": "CAD",
    }
    return market_currency.get(market, default_currency)


def _exchange_rate_to_base(raw_currency: str, base_currency: str) -> float | None:
    raw = _normalize_currency(raw_currency)
    base = _normalize_currency(base_currency)
    if raw == base:
        return 1.0
    return None


def _summarize_closes(closes: list[float]) -> dict[str, Any]:
    latest = closes[-1]
    high = max(closes)
    drawdown = latest / high - 1 if high else 0
    ma20 = _moving_average(closes, 20)
    ma60 = _moving_average(closes, 60)
    ma120 = _moving_average(closes, 120)
    return {
        "status": "available",
        "latest_close": latest,
        "ma20": ma20,
        "ma60": ma60,
        "ma120": ma120,
        "change_20": _period_change(closes, 20),
        "change_60": _period_change(closes, 60),
        "drawdown_from_period_high": drawdown,
        "above_ma20": latest >= ma20 if ma20 is not None else None,
        "above_ma60": latest >= ma60 if ma60 is not None else None,
        "above_ma120": latest >= ma120 if ma120 is not None else None,
        "trend_summary": _trend_summary(latest, ma20, ma60, ma120),
    }


def _moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _period_change(values: list[float], period: int) -> float | None:
    if len(values) <= period or values[-period - 1] == 0:
        return None
    return values[-1] / values[-period - 1] - 1


def _trend_summary(latest: float, ma20: float | None, ma60: float | None, ma120: float | None) -> str:
    available = [item for item in (ma20, ma60, ma120) if item is not None]
    if not available:
        return "均线数据不足"
    above_count = sum(1 for item in available if latest >= item)
    if above_count == len(available):
        return "价格位于主要均线之上"
    if above_count == 0:
        return "价格位于主要均线之下"
    return "价格处于均线混合区间"


def _derive_position_exchange_rates(raw_values: dict[str, float], base_currency: str, account_market_value: float) -> dict[str, float]:
    base = _normalize_currency(base_currency)
    rates = {base: 1.0}
    foreign_values = {currency: value for currency, value in raw_values.items() if currency != base and value}
    if len(foreign_values) != 1 or not account_market_value:
        return rates

    base_value = raw_values.get(base, 0)
    currency, raw_value = next(iter(foreign_values.items()))
    converted_foreign_value = account_market_value - base_value
    if converted_foreign_value <= 0:
        return rates
    rates[currency] = converted_foreign_value / raw_value
    return rates


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _news_keyword(position: dict[str, Any]) -> str:
    name = str(position.get("name") or "").strip()
    code = str(position.get("code") or "").strip()
    if name:
        return name
    if "." in code:
        return code.split(".", 1)[1]
    return code


def _news_id(code: str, title: str, url: str, publish_time: datetime | None) -> str:
    raw = f"{code}|{url}|{title}|{publish_time.isoformat() if publish_time else ''}"
    return "news_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _normalize_market_auth(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if not value:
        return []
    text = str(value).replace("[", "").replace("]", "").replace("'", "")
    return [part.strip() for part in text.split(",") if part.strip()]


def _pick_market(markets: list[str]) -> str:
    for market in ("US", "HK", "HKCC"):
        if market in markets:
            return market
    return markets[0] if markets else "US"


def _infer_asset_type(code: str, name: str) -> str:
    upper = f"{code} {name}".upper()
    if any(marker in upper for marker in ("CALL", "PUT")) or ("C" in code[-12:] and any(ch.isdigit() for ch in code[-8:])):
        return "option"
    if "ETF" in upper:
        return "leveraged_etf" if any(token in upper for token in ("2X", "3X", "ULTRA", "SHORT", "BEAR")) else "etf"
    return "stock"
