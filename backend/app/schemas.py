from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LayerOverrideRequest(BaseModel):
    position_layer: str
    reason: str = ""


class PositionSnapshotSaveRequest(BaseModel):
    original_code: str = ""
    original_snapshot_time: Optional[datetime] = None
    code: str
    name: str = ""
    market: str = ""
    asset_type: str = "stock"
    quantity: float = 0
    average_cost: float = 0
    current_price: float = 0
    market_value: Optional[float] = None
    currency: str = ""
    normalized_market_value: Optional[float] = None
    normalized_currency: str = ""
    exchange_rate_to_base: Optional[float] = None
    profit_loss_ratio: Optional[float] = None
    position_weight: Optional[float] = None
    position_layer: str = "中期配置仓"
    snapshot_time: datetime


class DealSaveRequest(BaseModel):
    original_deal_id: str = ""
    deal_id: str
    order_id: str = ""
    code: str
    side: str = ""
    price: float = 0
    quantity: float = 0
    deal_time: Optional[datetime] = None
    market: str = ""


class DeleteLocalDataRequest(BaseModel):
    confirmation: str = Field(description="Must be DELETE_LOCAL_DATA")
