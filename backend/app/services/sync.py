from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.adapters.futu_adapter import FutuReadOnlyAdapter
from app.models import (
    AIAnalysis,
    AIWorkflowRun,
    Account,
    AccountSnapshot,
    Alert,
    DataSourceState,
    Deal,
    DecisionCard,
    NewsItem,
    PositionLayerOverride,
    PositionSnapshot,
    ProfileVersion,
    QuoteSummary,
    ReviewReport,
    SyncTask,
    TradeReview,
    UserAction,
    WatchlistItem,
)
from app.services.classifier import POSITION_LAYERS, PositionFacts, classify_position
from app.services.freshness import alert_cooldown_seconds, evaluate_freshness, page_freshness_summary
from app.services.providers import normalize_market
from app.services.trade_review import refresh_trade_reviews


MANUAL_SYNC_DEBOUNCE_SECONDS = 10
USER_ACCOUNT_CONFIG_FIELDS = {
    "import_mode",
    "position_import_modes",
    "review_import_modes",
    "market_data_provider",
    "news_data_provider",
}


def run_manual_sync(db: Session) -> SyncTask:
    existing = _recent_manual_sync(db)
    if existing:
        return existing

    sync_id = f"sync_{uuid4().hex}"
    task = SyncTask(
        sync_id=sync_id,
        sync_type="手动刷新",
        status="执行中",
        start_time=datetime.now(timezone.utc),
        source="futu",
        idempotency_key=f"manual:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
    )
    db.add(task)
    db.commit()

    try:
        adapter = FutuReadOnlyAdapter()
        snapshot = adapter.fetch_snapshot()
        inserted, updated = persist_snapshot(db, sync_id, snapshot)
        mark_source_state(db, "futu", "available", "", 0)
        task.status = "成功"
        task.inserted_count = inserted
        task.updated_count = updated
    except Exception as exc:
        task.status = "失败"
        task.error_message = str(exc)[:1000]
        mark_source_state(db, "futu", "unavailable", task.error_message, 0)
    finally:
        task.end_time = datetime.now(timezone.utc)
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def pull_account_market_data(db: Session, account: Account, data_type: str) -> dict:
    normalized_type = str(data_type or "").strip().lower()
    if normalized_type not in {"quote", "news"}:
        raise ValueError("Unsupported data type")
    positions = [item for item in latest_positions(db, account.account_id) if item.code and not item.missing_market_code]
    if not positions:
        return {"status": "empty", "message": "当前账户暂无可拉取的持仓标的", "inserted_count": 0, "updated_count": 0}

    sync_id = f"{normalized_type}_pull_{uuid4().hex}"
    adapter = FutuReadOnlyAdapter()
    if normalized_type == "quote":
        rows = adapter.fetch_quote_summaries([item.code for item in positions])
        inserted = _persist_quote_rows(db, sync_id, rows)
        _mark_account_pull_states(db, account, positions, "quote", rows, "")
        db.commit()
        return {"status": "success", "message": f"已拉取 {inserted} 条行情数据", "inserted_count": inserted, "updated_count": 0}

    position_payloads = [
        {
            "account_id": item.account_id,
            "code": item.code,
            "name": item.name,
            "market": item.market,
        }
        for item in positions
    ]
    rows, error = adapter.fetch_news_items(position_payloads)
    inserted, updated = _persist_news_rows(db, sync_id, rows)
    _mark_account_pull_states(db, account, positions, "news", rows, error)
    db.commit()
    status = "success" if rows else "empty"
    message = f"已拉取 {inserted + updated} 条新闻数据" if rows else error or "本次未返回新闻数据"
    return {"status": status, "message": message, "inserted_count": inserted, "updated_count": updated}


def _persist_quote_rows(db: Session, sync_id: str, rows: list[dict]) -> int:
    inserted = 0
    for payload in rows:
        db.add(QuoteSummary(sync_id=sync_id, **payload))
        inserted += 1
    return inserted


def _persist_news_rows(db: Session, sync_id: str, rows: list[dict]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for payload in rows:
        existing = db.get(NewsItem, payload["news_id"])
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.sync_id = sync_id
            updated += 1
        else:
            db.add(NewsItem(sync_id=sync_id, **payload))
            inserted += 1
    return inserted, updated


def _mark_account_pull_states(db: Session, account: Account, positions: list[PositionSnapshot], data_type: str, rows: list[dict], error: str) -> None:
    now = datetime.now(timezone.utc)
    rows_by_market: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        market = normalize_market(str(row.get("market") or str(row.get("code", "")).split(".")[0]))
        rows_by_market[market].append(row)
    provider_fallback = account.market_data_provider if data_type == "quote" else account.news_data_provider
    provider_fallback = str(provider_fallback or account.broker_provider or data_type).strip().lower()
    for market in sorted({normalize_market(item.market or str(item.code).split(".", 1)[0]) for item in positions if item.code}):
        market_rows = rows_by_market.get(market, [])
        time_key = "quote_time" if data_type == "quote" else "fetched_at"
        data_time = max((item.get(time_key) for item in market_rows), default=None)
        provider = next((str(item.get("provider") or "") for item in market_rows if item.get("provider")), provider_fallback)
        _mark_data_type_state(db, account.account_id, provider or data_type, data_type, market, data_time, error)
    mark_source_state(
        db,
        data_type,
        "available" if rows else "missing",
        "" if rows else error or "本次拉取未返回数据",
        0,
        data_type=data_type,
        last_success_time=now if rows else None,
    )


def persist_snapshot(db: Session, sync_id: str, snapshot) -> tuple[int, int]:
    inserted = 0
    updated = 0
    now = datetime.now(timezone.utc)

    for payload in snapshot.accounts:
        account = db.get(Account, payload["account_id"])
        is_existing_account = bool(account)
        if account:
            updated += 1
        else:
            account = Account(account_id=payload["account_id"])
            inserted += 1
        for key, value in payload.items():
            if is_existing_account and key in USER_ACCOUNT_CONFIG_FIELDS:
                continue
            setattr(account, key, value)
        account.last_sync_time = now
        db.add(account)

    for payload in snapshot.account_snapshots:
        db.add(AccountSnapshot(sync_id=sync_id, **payload))
        inserted += 1

    deal_stats = _deal_stats(snapshot.deals)
    override_by_code = {item.code: item for item in db.scalars(select(PositionLayerOverride)).all()}

    for payload in snapshot.positions:
        stats = deal_stats[payload["code"]]
        override = override_by_code.get(payload["code"])
        facts = PositionFacts(
            code=payload["code"],
            asset_type=payload["asset_type"],
            position_weight=payload["position_weight"],
            first_buy_time=stats["first_buy_time"],
            buy_count=stats["buy_count"],
            sell_count=stats["sell_count"],
            has_round_trip=stats["buy_count"] > 0 and stats["sell_count"] > 0,
            profit_loss_ratio=payload["profit_loss_ratio"],
            is_leveraged_etf=payload["asset_type"] == "leveraged_etf",
            manual_layer=override.position_layer if override else None,
            data_days=stats["data_days"],
            now=now,
        )
        layer = classify_position(facts)
        payload.update(
            {
                "first_buy_time": stats["first_buy_time"],
                "last_trade_time": stats["last_trade_time"],
                "position_layer": layer.layer,
                "layer_source": layer.source,
                "layer_confidence": layer.confidence,
                "layer_reason": layer.reason,
                "sync_id": sync_id,
            }
        )
        db.add(PositionSnapshot(**payload))
        inserted += 1

    for payload in snapshot.deals:
        existing = db.scalar(
            select(Deal).where(Deal.account_id == payload["account_id"], Deal.deal_id == payload["deal_id"])
        )
        if existing:
            updated += 1
            continue
        db.add(Deal(**payload))
        inserted += 1

    for payload in snapshot.watchlist:
        existing = db.scalar(
            select(WatchlistItem).where(
                WatchlistItem.group_name == payload["group_name"], WatchlistItem.code == payload["code"]
            )
        )
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(WatchlistItem(**payload))
            inserted += 1

    for payload in snapshot.quotes:
        db.add(QuoteSummary(sync_id=sync_id, **payload))
        inserted += 1

    for payload in getattr(snapshot, "news", []):
        existing = db.get(NewsItem, payload["news_id"])
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.sync_id = sync_id
            updated += 1
        else:
            db.add(NewsItem(sync_id=sync_id, **payload))
            inserted += 1

    _mark_freshness_states(db, snapshot)
    _create_profile(db)
    _create_review(db)
    refresh_trade_reviews(db)
    db.commit()
    return inserted, updated


def latest_sync(db: Session) -> SyncTask | None:
    return db.scalar(select(SyncTask).order_by(SyncTask.start_time.desc()).limit(1))


def latest_positions(db: Session, account_id: Optional[str] = None) -> list[PositionSnapshot]:
    filters = []
    if account_id and account_id != "all":
        filters.append(PositionSnapshot.account_id == account_id)
    invalid_sync_ids = sample_template_sync_ids(db)
    if invalid_sync_ids:
        filters.append(PositionSnapshot.sync_id.notin_(invalid_sync_ids))
    subq = (
        select(
            PositionSnapshot.account_id,
            PositionSnapshot.code,
            func.max(PositionSnapshot.snapshot_time).label("latest"),
        )
        .where(*filters)
        .group_by(PositionSnapshot.account_id, PositionSnapshot.code)
        .subquery()
    )
    positions = list(
        db.scalars(
            select(PositionSnapshot)
            .join(
                subq,
                (PositionSnapshot.account_id == subq.c.account_id)
                & (PositionSnapshot.code == subq.c.code)
                & (PositionSnapshot.snapshot_time == subq.c.latest),
            )
            .order_by(PositionSnapshot.position_weight.desc())
        ).all()
    )
    _apply_layer_overrides(db, positions)
    return positions


def _apply_layer_overrides(db: Session, positions: list[PositionSnapshot]) -> None:
    codes = {item.code for item in positions}
    if not codes:
        return
    overrides = {
        item.code: item
        for item in db.scalars(select(PositionLayerOverride).where(PositionLayerOverride.code.in_(codes))).all()
        if item.position_layer in POSITION_LAYERS
    }
    for item in positions:
        override = overrides.get(item.code)
        if not override:
            continue
        item.position_layer = override.position_layer
        item.layer_source = "user"
        item.layer_confidence = "高"
        item.layer_reason = override.reason or "用户手动修正优先"


def latest_account_snapshots(db: Session, account_id: Optional[str] = None) -> list[AccountSnapshot]:
    filters = []
    if account_id and account_id != "all":
        filters.append(AccountSnapshot.account_id == account_id)
    invalid_sync_ids = sample_template_sync_ids(db)
    if invalid_sync_ids:
        filters.append(AccountSnapshot.sync_id.notin_(invalid_sync_ids))
    subq = (
        select(AccountSnapshot.account_id, func.max(AccountSnapshot.snapshot_time).label("latest"))
        .where(*filters)
        .group_by(AccountSnapshot.account_id)
        .subquery()
    )
    return list(
        db.scalars(
            select(AccountSnapshot).join(
                subq,
                (AccountSnapshot.account_id == subq.c.account_id)
                & (AccountSnapshot.snapshot_time == subq.c.latest),
            )
        ).all()
    )


def sample_template_sync_ids(db: Session) -> set[str]:
    rows = db.execute(select(AccountSnapshot.sync_id, AccountSnapshot.raw_currency_values)).all()
    return {
        str(sync_id)
        for sync_id, values in rows
        if isinstance(values, dict) and values.get("parser") == "sample_template"
    }


def latest_cards(db: Session, limit: int = 20, latest_per_code: bool = True) -> list[DecisionCard]:
    fetch_limit = max(limit * 5, 200) if latest_per_code else limit
    cards = list(
        db.scalars(
            select(DecisionCard)
            .where(DecisionCard.ignored.is_(False))
            .order_by(DecisionCard.created_at.desc())
            .limit(fetch_limit)
        ).all()
    )
    if latest_per_code:
        seen = set()
        deduped = []
        for card in cards:
            if card.code in seen:
                continue
            seen.add(card.code)
            deduped.append(card)
        cards = deduped
    return cards[:limit]


def latest_alerts(db: Session, limit: int = 50) -> list[Alert]:
    return list(
        db.scalars(
            select(Alert)
            .where(Alert.ignored.is_(False))
            .order_by(Alert.priority.asc(), Alert.created_at.desc())
            .limit(limit)
        ).all()
    )


def latest_profile(db: Session) -> ProfileVersion | None:
    return db.scalar(select(ProfileVersion).order_by(ProfileVersion.generated_at.desc()).limit(1))


def latest_review(db: Session) -> ReviewReport | None:
    return db.scalar(select(ReviewReport).order_by(ReviewReport.created_at.desc()).limit(1))


def latest_source_states(db: Session) -> list[DataSourceState]:
    return list(
        db.scalars(
            select(DataSourceState).order_by(
                DataSourceState.account_id.asc(),
                DataSourceState.provider.asc(),
                DataSourceState.data_type.asc(),
                DataSourceState.market.asc(),
                DataSourceState.source_name.asc(),
            )
        ).all()
    )


def freshness_summary(db: Session) -> list[dict]:
    positions = latest_positions(db)
    latest_deal_time = db.scalar(select(func.max(Deal.deal_time)))
    latest_watchlist_time = db.scalar(select(func.max(WatchlistItem.updated_at)))
    latest_quote_time = db.scalar(select(func.max(QuoteSummary.quote_time)))
    latest_news_time = db.scalar(select(func.max(NewsItem.fetched_at)))
    profile = latest_profile(db)
    latest_card_time = db.scalar(select(func.max(DecisionCard.data_time)))
    return page_freshness_summary(
        {
            "quote": latest_quote_time,
            "position": max((item.snapshot_time for item in positions), default=None),
            "deal": latest_deal_time,
            "watchlist": latest_watchlist_time,
            "news": latest_news_time,
            "profile": profile.generated_at if profile else None,
            "decision_card": latest_card_time,
        }
    )


def opportunities(db: Session) -> list[dict]:
    watchlist_codes = {item.code for item in db.scalars(select(WatchlistItem)).all()}
    position_codes = {item.code for item in latest_positions(db)}
    quotes = db.scalars(select(QuoteSummary).order_by(QuoteSummary.quote_time.desc()).limit(200)).all()
    items = []
    seen = set()
    for quote in quotes:
        if quote.code in seen or quote.code in position_codes:
            continue
        seen.add(quote.code)
        items.append(
            {
                "code": quote.code,
                "source": "富途自选" if quote.code in watchlist_codes else "行情扫描",
                "current_price": quote.current_price,
                "change_ratio": quote.change_ratio,
                "status": "观察",
                "reason": "自选或核心关注标的，等待明确买点",
                "quote_time": quote.quote_time,
            }
        )
    return items[:30]


def latest_news(db: Session, limit: int = 100, codes: list[str] | None = None) -> list[NewsItem]:
    stmt = select(NewsItem)
    if codes:
        stmt = stmt.where(NewsItem.code.in_(codes))
    return list(
        db.scalars(
            stmt.order_by(NewsItem.publish_time.desc().nullslast(), NewsItem.fetched_at.desc()).limit(limit)
        ).all()
    )


def recent_news_for_code(db: Session, code: str, days: int = 3, limit: int = 12) -> list[NewsItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return list(
        db.scalars(
            select(NewsItem)
            .where(NewsItem.code == code)
            .where((NewsItem.publish_time.is_(None)) | (NewsItem.publish_time >= cutoff))
            .order_by(NewsItem.publish_time.desc().nullslast(), NewsItem.fetched_at.desc())
            .limit(limit)
        ).all()
    )


def delete_local_data(db: Session) -> None:
    for model in (
        Alert,
        AIAnalysis,
        AIWorkflowRun,
        DecisionCard,
        NewsItem,
        QuoteSummary,
        WatchlistItem,
        Deal,
        TradeReview,
        PositionSnapshot,
        AccountSnapshot,
        ProfileVersion,
        ReviewReport,
        UserAction,
        DataSourceState,
        Account,
        SyncTask,
    ):
        db.execute(delete(model))
    db.commit()


def mark_source_state(
    db: Session,
    source_name: str,
    status: str,
    error: str,
    freshness_seconds: int,
    *,
    account_id: str = "all",
    provider: str = "",
    data_type: str = "",
    market: str = "",
    last_success_time: datetime | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    state = db.get(DataSourceState, source_name) or DataSourceState(source_name=source_name)
    state.account_id = account_id
    state.provider = provider
    state.data_type = data_type
    state.market = market
    state.status = status
    state.last_error = error
    state.freshness_seconds = freshness_seconds
    state.updated_at = now
    if status == "available":
        state.last_success_time = last_success_time or now
    db.add(state)


def should_create_alert(db: Session, code: str, alert_type: str, trigger_condition: str, now: datetime) -> bool:
    cooldown_start = now - timedelta(seconds=alert_cooldown_seconds(alert_type))
    existing = db.scalar(
        select(Alert).where(
            Alert.code == code,
            Alert.alert_type == alert_type,
            Alert.trigger_condition == trigger_condition,
            Alert.created_at >= cooldown_start,
)
    )
    return existing is None


def _recent_manual_sync(db: Session) -> SyncTask | None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=MANUAL_SYNC_DEBOUNCE_SECONDS)
    return db.scalar(
        select(SyncTask)
        .where(SyncTask.sync_type == "手动刷新", SyncTask.start_time >= cutoff)
        .order_by(SyncTask.start_time.desc())
        .limit(1)
    )


def _deal_stats(deals: list[dict]) -> dict[str, dict]:
    stats = defaultdict(lambda: {"buy_count": 0, "sell_count": 0, "first_buy_time": None, "last_trade_time": None, "data_days": 365})
    all_times = [deal["deal_time"] for deal in deals if deal.get("deal_time")]
    if all_times:
        data_days = max((max(all_times) - min(all_times)).days, 1)
    else:
        data_days = 0

    for deal in deals:
        code = deal["code"]
        item = stats[code]
        item["data_days"] = data_days
        side = str(deal.get("side", "")).upper()
        if "BUY" in side:
            item["buy_count"] += 1
            dt = deal.get("deal_time")
            if dt and (item["first_buy_time"] is None or dt < item["first_buy_time"]):
                item["first_buy_time"] = dt
        if "SELL" in side:
            item["sell_count"] += 1
        dt = deal.get("deal_time")
        if dt and (item["last_trade_time"] is None or dt > item["last_trade_time"]):
            item["last_trade_time"] = dt
    return stats


def _mark_freshness_states(db: Session, snapshot) -> None:
    now = datetime.now(timezone.utc)
    latest_times = {
        "account": max((item.get("snapshot_time") for item in snapshot.account_snapshots), default=None),
        "position": max((item.get("snapshot_time") for item in snapshot.positions), default=None),
        "deal": max((item.get("deal_time") for item in snapshot.deals if item.get("deal_time")), default=None),
        "watchlist": max((item.get("updated_at") for item in snapshot.watchlist), default=None),
        "quote": max((item.get("quote_time") for item in snapshot.quotes), default=None),
        "news": max((item.get("fetched_at") for item in getattr(snapshot, "news", [])), default=None),
    }
    for source_name, data_time in latest_times.items():
        if not data_time:
            error = getattr(snapshot, "news_error", "") if source_name == "news" else ""
            mark_source_state(db, source_name, "missing", error or "本次同步未返回该数据源", 0)
            continue
        rule_type = "position" if source_name == "account" else source_name
        freshness = evaluate_freshness(rule_type, data_time)
        age_seconds = int(freshness["age_seconds"] or 0)
        status = "available" if freshness["status"] == "fresh" else "stale"
        mark_source_state(
            db,
            source_name,
            status,
            "" if status == "available" else freshness["message"],
            age_seconds,
            data_type=source_name,
            last_success_time=data_time,
        )
    _mark_provider_freshness_states(db, snapshot, now)


def _mark_provider_freshness_states(db: Session, snapshot, now: datetime) -> None:
    positions_by_account: dict[str, list[dict]] = defaultdict(list)
    for position in snapshot.positions:
        positions_by_account[str(position.get("account_id") or "all")].append(position)

    quotes_by_market: dict[str, list[dict]] = defaultdict(list)
    for quote in snapshot.quotes:
        market = normalize_market(str(quote.get("market") or str(quote.get("code", "")).split(".")[0]))
        quotes_by_market[market].append(quote)

    news_by_market: dict[str, list[dict]] = defaultdict(list)
    for item in getattr(snapshot, "news", []):
        market = normalize_market(str(item.get("market") or str(item.get("code", "")).split(".")[0]))
        news_by_market[market].append(item)

    account_sources = {str(account.get("account_id")): str(account.get("broker_provider") or "") for account in snapshot.accounts}
    for account_id, positions in positions_by_account.items():
        account_source = account_sources.get(account_id, "futu")
        for market in sorted({normalize_market(str(item.get("market") or str(item.get("code", "")).split(".")[0])) for item in positions}):
            market_quotes = quotes_by_market.get(market, [])
            quote_time = max((item.get("quote_time") for item in market_quotes), default=None)
            quote_provider = next((str(item.get("provider") or account_source) for item in market_quotes), account_source)
            _mark_data_type_state(db, account_id, quote_provider, "quote", market, quote_time, "")

            market_news = news_by_market.get(market, [])
            news_time = max((item.get("fetched_at") for item in market_news), default=None)
            news_provider = next((str(item.get("provider") or "") for item in market_news), "")
            news_error = getattr(snapshot, "news_error", "") if not news_time else ""
            _mark_data_type_state(db, account_id, news_provider or "news", "news", market, news_time, news_error)


def _mark_data_type_state(
    db: Session,
    account_id: str,
    provider: str,
    data_type: str,
    market: str,
    data_time: datetime | None,
    error: str,
) -> None:
    source_name = _provider_state_key(account_id, provider, data_type, market)
    if not data_time:
        mark_source_state(
            db,
            source_name,
            "missing",
            error or "本次同步未返回该数据源",
            0,
            account_id=account_id,
            provider=provider,
            data_type=data_type,
            market=market,
        )
        return
    freshness = evaluate_freshness("quote" if data_type == "quote" else "news", data_time)
    status = "available" if freshness["status"] == "fresh" else "stale"
    mark_source_state(
        db,
        source_name,
        status,
        "" if status == "available" else freshness["message"],
        int(freshness["age_seconds"] or 0),
        account_id=account_id,
        provider=provider,
        data_type=data_type,
        market=market,
        last_success_time=data_time,
    )


def _provider_state_key(account_id: str, provider: str, data_type: str, market: str) -> str:
    return f"{account_id}:{provider}:{data_type}:{market}"


def _create_profile(db: Session) -> None:
    positions = latest_positions(db)
    account_snapshots = latest_account_snapshots(db)
    base_currency = _portfolio_base_currency(account_snapshots, positions)
    total = _account_market_value_base(account_snapshots, base_currency) or sum(_position_market_value_base(item, base_currency) for item in positions) or 1
    by_layer = defaultdict(float)
    for item in positions:
        by_layer[item.position_layer] += _position_market_value_base(item, base_currency)
    profile = ProfileVersion(
        profile_id=f"profile_{uuid4().hex}",
        generated_at=datetime.now(timezone.utc),
        confidence="低" if not positions else min((item.layer_confidence for item in positions), default="低"),
        core_position_ratio=by_layer["核心长期仓"] / total,
        mid_position_ratio=by_layer["中期配置仓"] / total,
        trade_position_ratio=by_layer["短期交易仓"] / total,
        option_position_ratio=by_layer["期权仓"] / total,
        tags=_profile_tags(positions),
        change_reason="同步后按最新持仓和成交记录生成",
    )
    db.add(profile)


def _create_review(db: Session) -> None:
    positions = latest_positions(db)
    account_snapshots = latest_account_snapshots(db)
    base_currency = _portfolio_base_currency(account_snapshots, positions)
    total_position_value = _account_market_value_base(account_snapshots, base_currency) or sum(
        _position_market_value_base(item, base_currency) for item in positions
    )
    total_assets = _account_total_assets_base(account_snapshots, base_currency) or total_position_value
    max_position_weight = _max_merged_position_weight(positions, total_assets, base_currency)
    cards = latest_cards(db, limit=100)
    alerts = latest_alerts(db, limit=100)
    now = datetime.now(timezone.utc)
    review = ReviewReport(
        review_id=f"review_{uuid4().hex}",
        review_date=now.date().isoformat(),
        portfolio_summary={
            "position_count": len(positions),
            "total_position_value": total_position_value,
            "base_currency": base_currency,
            "max_position_weight": max_position_weight,
            "largest_loss": min((item.profit_loss_ratio for item in positions), default=0),
        },
        advice_summary={
            "card_count": len(cards),
            "p0_p1_count": len([item for item in cards if item.priority in {"P0", "P1"}]),
            "recommendations": _count_by([item.recommendation for item in cards]),
        },
        user_action_summary={
            "recorded_actions": db.scalar(select(func.count()).select_from(UserAction)) or 0,
        },
        result_summary={
            "status": "待后续行情验证",
            "alerts": len(alerts),
        },
        next_watchlist=[item.code for item in positions[:10]],
        created_at=now,
    )
    db.add(review)


def _profile_tags(positions: list[PositionSnapshot]) -> list[str]:
    tags = set()
    for item in positions:
        if item.position_layer == "核心长期仓":
            tags.add("长期配置")
        if item.market == "US":
            tags.add("美股科技成长")
        if item.market == "HK":
            tags.add("港股热门股")
        if item.asset_type == "option":
            tags.add("期权增强或短线交易")
    return sorted(tags)


def _count_by(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _priority_rank(priority: str) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(priority, 4)


def _base_currency(positions: list[PositionSnapshot]) -> str:
    for item in positions:
        if item.normalized_currency:
            return item.normalized_currency
    return "HKD"


def _account_market_value(db: Session) -> float:
    return sum(item.market_value for item in latest_account_snapshots(db))


def _account_base_currency(account_snapshots: list[AccountSnapshot]) -> str:
    for snapshot in account_snapshots:
        currency = (snapshot.raw_currency_values or {}).get("currency")
        if currency:
            return str(currency)
    return ""


def _portfolio_base_currency(account_snapshots: list[AccountSnapshot], positions: list[PositionSnapshot]) -> str:
    if len(account_snapshots) > 1:
        return "CNY"
    return _account_base_currency(account_snapshots) or _base_currency(positions)


def _account_market_value_base(account_snapshots: list[AccountSnapshot], base_currency: str) -> float:
    return sum(_money_to_base(item.market_value, _snapshot_currency(item), base_currency) for item in account_snapshots)


def _account_total_assets_base(account_snapshots: list[AccountSnapshot], base_currency: str) -> float:
    return sum(_money_to_base(item.total_assets, _snapshot_currency(item), base_currency) for item in account_snapshots)


def _max_merged_position_weight(positions: list[PositionSnapshot], total_assets: float, base_currency: str) -> float:
    if total_assets <= 0:
        return 0
    by_code: dict[str, float] = defaultdict(float)
    for item in positions:
        by_code[item.code] += _position_market_value_base(item, base_currency)
    return max((value / total_assets for value in by_code.values()), default=0)


def _position_market_value_base(position: PositionSnapshot, base_currency: str) -> float:
    return _money_to_base(position.normalized_market_value, position.normalized_currency or position.raw_currency, base_currency)


def _money_to_base(value: float, currency: str, base_currency: str) -> float:
    currency = (currency or base_currency or "CNY").upper()
    base_currency = (base_currency or currency).upper()
    if currency == base_currency:
        return float(value or 0)
    return float(value or 0) * _currency_rate_to_cny(currency) / _currency_rate_to_cny(base_currency)


def _snapshot_currency(snapshot: AccountSnapshot) -> str:
    return str((snapshot.raw_currency_values or {}).get("currency") or "")


def _currency_rate_to_cny(currency: str) -> float:
    rates = {"CNY": 1.0, "CNH": 1.0, "USD": 7.2, "HKD": 0.92}
    return rates.get(currency.upper(), 1.0)
