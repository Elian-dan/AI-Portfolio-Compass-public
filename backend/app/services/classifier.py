from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


POSITION_LAYERS = {"核心长期仓", "中期配置仓", "短期交易仓", "期权仓", "遗留观察仓"}


@dataclass
class PositionFacts:
    code: str
    asset_type: str = "stock"
    position_weight: float = 0
    first_buy_time: datetime | None = None
    buy_count: int = 0
    sell_count: int = 0
    has_round_trip: bool = False
    profit_loss_ratio: float = 0
    is_leveraged_etf: bool = False
    manual_layer: str | None = None
    data_days: int = 365
    now: datetime | None = None


@dataclass
class LayerResult:
    layer: str
    confidence: str
    source: str
    reason: str


def holding_days(facts: PositionFacts) -> int | None:
    if not facts.first_buy_time:
        return None
    now = facts.now or datetime.now(timezone.utc)
    first = facts.first_buy_time
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    return max((now - first).days, 0)


def classify_position(facts: PositionFacts) -> LayerResult:
    if facts.manual_layer in POSITION_LAYERS:
        return LayerResult(facts.manual_layer, "高", "user", "用户手动修正优先")

    confidence = "低" if facts.data_days < 90 else "中" if facts.data_days < 365 else "高"
    code = facts.code.upper()
    asset_type = facts.asset_type.lower()
    days = holding_days(facts)

    if "option" in asset_type or _looks_like_option(code):
        return LayerResult("期权仓", confidence, "system", "标的识别为期权合约")

    if facts.is_leveraged_etf and days is not None and days < 21:
        return LayerResult("短期交易仓", confidence, "system", "杠杆 ETF 且持有时间短")

    if facts.buy_count == 0 and facts.position_weight > 0:
        return LayerResult("遗留观察仓", confidence, "system", "查询期内无买入记录但当前仍持有")

    if facts.profit_loss_ratio <= -0.30 and (days is None or days >= 180):
        return LayerResult("遗留观察仓", confidence, "system", "长期持有且浮亏超过 30%")

    if facts.has_round_trip or (days is not None and days < 21):
        return LayerResult("短期交易仓", confidence, "system", "持有周期短或存在完整买卖闭环")

    if days is not None and days >= 180:
        return LayerResult("核心长期仓", confidence, "system", "持有时间达到 180 天以上")

    if asset_type in {"etf", "fund"} and facts.buy_count >= 2 and not facts.has_round_trip:
        return LayerResult("核心长期仓", confidence, "system", "ETF/基金多次加仓且无短线闭环")

    if days is not None and 21 <= days < 180:
        return LayerResult("中期配置仓", confidence, "system", "持有时间处于 21-180 天")

    return LayerResult("中期配置仓", "低", "system", "信号冲突或历史数据不足，等待用户确认")


def _looks_like_option(code: str) -> bool:
    return any(marker in code for marker in ("C", "P")) and any(char.isdigit() for char in code[-8:])
