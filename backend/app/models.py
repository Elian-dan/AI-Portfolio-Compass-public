from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .database import Base


class Account(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_name: Mapped[str] = mapped_column(String, default="futu", index=True)
    broker_provider: Mapped[str] = mapped_column(String, default="", index=True)
    display_name: Mapped[str] = mapped_column(String, default="")
    institution: Mapped[str] = mapped_column(String, default="")
    import_mode: Mapped[str] = mapped_column(String, default="api")
    position_import_modes: Mapped[str] = mapped_column(String, default="")
    review_import_modes: Mapped[str] = mapped_column(String, default="")
    market_data_provider: Mapped[str] = mapped_column(String, default="")
    news_data_provider: Mapped[str] = mapped_column(String, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_import_hash: Mapped[str] = mapped_column(String, default="")
    account_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    trade_env: Mapped[str] = mapped_column(String, default="REAL")
    markets: Mapped[list[str]] = mapped_column(JSON, default=list)
    base_currency: Mapped[str] = mapped_column(String, default="HKD")
    total_assets: Mapped[float] = mapped_column(Float, default=0)
    cash: Mapped[float] = mapped_column(Float, default=0)
    market_value: Mapped[float] = mapped_column(Float, default=0)
    last_sync_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, index=True)
    total_assets: Mapped[float] = mapped_column(Float, default=0)
    cash: Mapped[float] = mapped_column(Float, default=0)
    market_value: Mapped[float] = mapped_column(Float, default=0)
    raw_currency_values: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    sync_id: Mapped[str] = mapped_column(String, index=True)


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"
    __table_args__ = (UniqueConstraint("account_id", "code", "snapshot_time", name="uq_position_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String, index=True)
    code: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, default="")
    market: Mapped[str] = mapped_column(String, default="")
    asset_type: Mapped[str] = mapped_column(String, default="stock")
    quantity: Mapped[float] = mapped_column(Float, default=0)
    average_cost: Mapped[float] = mapped_column(Float, default=0)
    current_price: Mapped[float] = mapped_column(Float, default=0)
    raw_market_value: Mapped[float] = mapped_column(Float, default=0)
    raw_currency: Mapped[str] = mapped_column(String, default="")
    normalized_market_value: Mapped[float] = mapped_column(Float, default=0)
    normalized_currency: Mapped[str] = mapped_column(String, default="")
    exchange_rate_to_base: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_weight: Mapped[float] = mapped_column(Float, default=0)
    profit_loss_ratio: Mapped[float] = mapped_column(Float, default=0)
    first_buy_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_trade_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    position_layer: Mapped[str] = mapped_column(String, default="中期配置仓")
    layer_source: Mapped[str] = mapped_column(String, default="system")
    layer_confidence: Mapped[str] = mapped_column(String, default="中")
    layer_reason: Mapped[str] = mapped_column(Text, default="")
    missing_market_code: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    sync_id: Mapped[str] = mapped_column(String, index=True)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("base_currency", "quote_currency", "source", name="uq_exchange_rate_pair_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_currency: Mapped[str] = mapped_column(String, index=True)
    quote_currency: Mapped[str] = mapped_column(String, index=True)
    rate: Mapped[float] = mapped_column(Float, default=1)
    source: Mapped[str] = mapped_column(String, default="frankfurter", index=True)
    rate_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (UniqueConstraint("account_id", "deal_id", name="uq_account_deal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(String, index=True)
    order_id: Mapped[str] = mapped_column(String, default="")
    code: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(String, default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    deal_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    market: Mapped[str] = mapped_column(String, default="")
    account_id: Mapped[str] = mapped_column(String, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("group_name", "code", name="uq_watchlist_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_name: Mapped[str] = mapped_column(String, default="默认")
    code: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="futu")
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class QuoteSummary(Base):
    __tablename__ = "quote_summaries"
    __table_args__ = (UniqueConstraint("code", "quote_time", name="uq_quote_time"),)

    quote_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String, default="futu", index=True)
    market: Mapped[str] = mapped_column(String, default="", index=True)
    exchange: Mapped[str] = mapped_column(String, default="")
    is_delayed: Mapped[bool] = mapped_column(Boolean, default=False)
    license_note: Mapped[str] = mapped_column(Text, default="")
    current_price: Mapped[float] = mapped_column(Float, default=0)
    change_ratio: Mapped[float] = mapped_column(Float, default=0)
    volume: Mapped[float] = mapped_column(Float, default=0)
    ma_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    support_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resistance_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quote_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    sync_id: Mapped[str] = mapped_column(String, index=True)


class KlineSnapshot(Base):
    __tablename__ = "kline_snapshots"
    __table_args__ = (UniqueConstraint("code", "period", "time_key", "snapshot_time", name="uq_kline_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String, default="futu", index=True)
    period: Mapped[str] = mapped_column(String, index=True)
    time_key: Mapped[str] = mapped_column(String, index=True)
    open: Mapped[float] = mapped_column(Float, default=0)
    close: Mapped[float] = mapped_column(Float, default=0)
    high: Mapped[float] = mapped_column(Float, default=0)
    low: Mapped[float] = mapped_column(Float, default=0)
    volume: Mapped[float] = mapped_column(Float, default=0)
    turnover: Mapped[float] = mapped_column(Float, default=0)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    sync_id: Mapped[str] = mapped_column(String, index=True)


class NewsItem(Base):
    __tablename__ = "news_items"

    news_id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String, default="futu", index=True)
    market: Mapped[str] = mapped_column(String, default="", index=True)
    news_type: Mapped[str] = mapped_column(String, default="news", index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    news_sub_type: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="")
    publish_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    related_securities: Mapped[list[dict]] = mapped_column(JSON, default=list)
    url: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sync_id: Mapped[str] = mapped_column(String, index=True, default="")


class DecisionCard(Base):
    __tablename__ = "decision_cards"

    card_id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, index=True)
    position_layer: Mapped[str] = mapped_column(String, default="")
    recommendation: Mapped[str] = mapped_column(String, default="观察")
    confidence: Mapped[str] = mapped_column(String, default="中")
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    key_prices: Mapped[dict] = mapped_column(JSON, default=dict)
    data_time: Mapped[datetime] = mapped_column(DateTime)
    action_required: Mapped[bool] = mapped_column(Boolean, default=False)
    data_version: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="正常")
    priority: Mapped[str] = mapped_column(String, default="P3")
    generation_source: Mapped[str] = mapped_column(String, default="rule")
    model: Mapped[str] = mapped_column(String, default="")
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    input_version: Mapped[str] = mapped_column(String, default="")
    analysis_framework: Mapped[dict] = mapped_column(JSON, default=dict)
    missing_data: Mapped[list[str]] = mapped_column(JSON, default=list)
    invalid_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    read_status: Mapped[str] = mapped_column(String, default="未读")
    ignored: Mapped[bool] = mapped_column(Boolean, default=False)


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, index=True)
    alert_type: Mapped[str] = mapped_column(String, default="")
    trigger_condition: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String, default="P3")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    read_status: Mapped[str] = mapped_column(String, default="未读")
    related_card_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ignored: Mapped[bool] = mapped_column(Boolean, default=False)


class SyncTask(Base):
    __tablename__ = "sync_tasks"

    sync_id: Mapped[str] = mapped_column(String, primary_key=True)
    sync_type: Mapped[str] = mapped_column(String, default="手动刷新")
    status: Mapped[str] = mapped_column(String, default="待执行")
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String, default="futu")
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str] = mapped_column(String, index=True, default="")


class ProfileVersion(Base):
    __tablename__ = "profile_versions"

    profile_id: Mapped[str] = mapped_column(String, primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    confidence: Mapped[str] = mapped_column(String, default="低")
    core_position_ratio: Mapped[float] = mapped_column(Float, default=0)
    mid_position_ratio: Mapped[float] = mapped_column(Float, default=0)
    trade_position_ratio: Mapped[float] = mapped_column(Float, default=0)
    option_position_ratio: Mapped[float] = mapped_column(Float, default=0)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    change_reason: Mapped[str] = mapped_column(Text, default="")


class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"

    scene: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, default="deepseek")
    model: Mapped[str] = mapped_column(String, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class AIRuntimeConfig(Base):
    __tablename__ = "ai_runtime_configs"

    config_id: Mapped[str] = mapped_column(String, primary_key=True, default="default")
    provider: Mapped[str] = mapped_column(String, default="deepseek", index=True)
    display_name: Mapped[str] = mapped_column(String, default="")
    base_url: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String, default="")
    api_key: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_test_status: Mapped[str] = mapped_column(String, default="")
    last_test_message: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class InvestorPreference(Base):
    __tablename__ = "investor_preferences"

    preference_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="all")
    kyc_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_tolerance: Mapped[str] = mapped_column(String, default="")
    investment_horizon: Mapped[str] = mapped_column(String, default="")
    liquidity_needs: Mapped[str] = mapped_column(String, default="")
    target_return: Mapped[str] = mapped_column(String, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class AIWorkflowRun(Base):
    __tablename__ = "ai_workflow_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String, index=True)
    account_id: Mapped[str] = mapped_column(String, index=True, default="all")
    question: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    steps: Mapped[list[dict]] = mapped_column(JSON, default=list)
    input_context: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    artifacts: Mapped[list[dict]] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String, default="local")
    model: Mapped[str] = mapped_column(String, default="local_workflow")
    data_version: Mapped[str] = mapped_column(String, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class UserAction(Base):
    __tablename__ = "user_actions"

    action_id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, index=True)
    action_type: Mapped[str] = mapped_column(String, default="查看建议")
    related_card_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class ReviewReport(Base):
    __tablename__ = "review_reports"

    review_id: Mapped[str] = mapped_column(String, primary_key=True)
    review_date: Mapped[str] = mapped_column(String, index=True)
    portfolio_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    advice_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    user_action_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    next_watchlist: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class TradeReview(Base):
    __tablename__ = "trade_reviews"
    __table_args__ = (UniqueConstraint("account_id", "deal_id", name="uq_trade_review_deal"),)

    review_id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, index=True)
    deal_id: Mapped[str] = mapped_column(String, index=True)
    order_id: Mapped[str] = mapped_column(String, default="")
    code: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(String, default="")
    price: Mapped[float] = mapped_column(Float, default=0)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    deal_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    one_day_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    five_day_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latest_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    one_day_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    five_day_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latest_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    result_label: Mapped[str] = mapped_column(String, default="等待验证")
    discipline_label: Mapped[str] = mapped_column(String, default="待补交易理由")
    confidence: Mapped[str] = mapped_column(String, default="低")
    fact_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_commentary: Mapped[str] = mapped_column(Text, default="")
    user_note: Mapped[str] = mapped_column(Text, default="")
    intent_tags: Mapped[dict] = mapped_column(JSON, default=dict)
    intent_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_by: Mapped[str] = mapped_column(String, default="rule_local_ai")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class DataSourceState(Base):
    __tablename__ = "data_source_states"

    source_name: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(String, default="all", index=True)
    provider: Mapped[str] = mapped_column(String, default="", index=True)
    data_type: Mapped[str] = mapped_column(String, default="", index=True)
    market: Mapped[str] = mapped_column(String, default="", index=True)
    status: Mapped[str] = mapped_column(String, default="unknown")
    last_success_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    freshness_seconds: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    analysis_id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String, default="local")
    model: Mapped[str] = mapped_column(String, default="local_reasoning")
    input_context: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="success")
    error_message: Mapped[str] = mapped_column(Text, default="")
    data_version: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class PositionLayerOverride(Base):
    __tablename__ = "position_layer_overrides"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    position_layer: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime)
