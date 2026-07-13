from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class FreshnessRule:
    data_type: str
    trading_seconds: int
    non_trading_seconds: int
    stale_action: str


FRESHNESS_RULES: dict[str, FreshnessRule] = {
    "quote": FreshnessRule("quote", 5 * 60, 24 * 60 * 60, "行情过期，仅作价格参考"),
    "position": FreshnessRule("position", 15 * 60, 24 * 60 * 60, "持仓过期，不生成仓位强提醒"),
    "deal": FreshnessRule("deal", 15 * 60, 24 * 60 * 60, "成交过期，不更新复盘关联"),
    "watchlist": FreshnessRule("watchlist", 24 * 60 * 60, 24 * 60 * 60, "自选股可能过期"),
    "fx_rate": FreshnessRule("fx_rate", 24 * 60 * 60, 24 * 60 * 60, "汇率过期，不生成归一化仓位强提醒"),
    "news": FreshnessRule("news", 60 * 60, 24 * 60 * 60, "资讯过期，不生成重大事件提醒"),
    "profile": FreshnessRule("profile", 24 * 60 * 60, 24 * 60 * 60, "画像可能滞后"),
    "decision_card": FreshnessRule("decision_card", 5 * 60, 24 * 60 * 60, "建议过期或失效"),
}


def evaluate_freshness(data_type: str, data_time: datetime | None, trading_session: bool = True) -> dict:
    rule = FRESHNESS_RULES[data_type]
    if not data_time:
        return {
            "data_type": data_type,
            "status": "missing",
            "age_seconds": None,
            "valid_seconds": rule.trading_seconds if trading_session else rule.non_trading_seconds,
            "message": "数据缺失",
            "stale_action": rule.stale_action,
        }

    now = datetime.now(timezone.utc)
    if data_time.tzinfo is None:
        data_time = data_time.replace(tzinfo=timezone.utc)
    age_seconds = max(int((now - data_time).total_seconds()), 0)
    valid_seconds = rule.trading_seconds if trading_session else rule.non_trading_seconds
    status = "fresh" if age_seconds <= valid_seconds else "stale"
    return {
        "data_type": data_type,
        "status": status,
        "age_seconds": age_seconds,
        "valid_seconds": valid_seconds,
        "message": "数据有效" if status == "fresh" else rule.stale_action,
        "stale_action": rule.stale_action,
    }


def page_freshness_summary(latest_times: dict[str, datetime | None], trading_session: bool = True) -> list[dict]:
    return [
        evaluate_freshness(data_type, latest_times.get(data_type), trading_session)
        for data_type in ("position", "deal", "watchlist", "news", "profile", "decision_card")
    ]


def alert_cooldown_seconds(alert_type: str) -> int:
    if alert_type in {"组合风险", "减仓关注", "止损关注"}:
        return 30 * 60
    if alert_type in {"可等待买点", "不建议追高"}:
        return 60 * 60
    if "期权" in alert_type:
        return 24 * 60 * 60
    if "数据" in alert_type:
        return 30 * 60
    return 30 * 60
