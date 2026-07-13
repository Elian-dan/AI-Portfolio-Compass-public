from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        alert_columns = {row[1] for row in conn.execute(text("pragma table_info(alerts)")).fetchall()}
        if alert_columns and "ignored" not in alert_columns:
            conn.execute(text("alter table alerts add column ignored boolean default 0"))
        position_columns = {row[1] for row in conn.execute(text("pragma table_info(position_snapshots)")).fetchall()}
        if position_columns:
            if "raw_currency" not in position_columns:
                conn.execute(text("alter table position_snapshots add column raw_currency varchar default ''"))
            if "normalized_currency" not in position_columns:
                conn.execute(text("alter table position_snapshots add column normalized_currency varchar default ''"))
            if "exchange_rate_to_base" not in position_columns:
                conn.execute(text("alter table position_snapshots add column exchange_rate_to_base float"))
            if "missing_market_code" not in position_columns:
                conn.execute(text("alter table position_snapshots add column missing_market_code boolean default 0"))
        account_columns = {row[1] for row in conn.execute(text("pragma table_info(accounts)")).fetchall()}
        if account_columns:
            account_additions = {
                "source_name": "varchar default 'futu'",
                "broker_provider": "varchar default ''",
                "display_name": "varchar default ''",
                "institution": "varchar default ''",
                "import_mode": "varchar default 'api'",
                "position_import_modes": "varchar default ''",
                "review_import_modes": "varchar default ''",
                "market_data_provider": "varchar default ''",
                "news_data_provider": "varchar default ''",
                "enabled": "boolean default 1",
                "last_import_hash": "varchar default ''",
            }
            for column, definition in account_additions.items():
                if column not in account_columns:
                    conn.execute(text(f"alter table accounts add column {column} {definition}"))
        card_columns = {row[1] for row in conn.execute(text("pragma table_info(decision_cards)")).fetchall()}
        if card_columns:
            card_additions = {
                "generation_source": "varchar default 'rule'",
                "model": "varchar default ''",
                "generated_at": "datetime",
                "input_version": "varchar default ''",
                "analysis_framework": "json default '{}'",
                "missing_data": "json default '[]'",
                "invalid_conditions": "json default '[]'",
            }
            for column, definition in card_additions.items():
                if column not in card_columns:
                    conn.execute(text(f"alter table decision_cards add column {column} {definition}"))
        trade_review_columns = {row[1] for row in conn.execute(text("pragma table_info(trade_reviews)")).fetchall()}
        if trade_review_columns:
            trade_review_additions = {
                "intent_tags": "json default '{}'",
                "intent_plan": "json default '{}'",
            }
            for column, definition in trade_review_additions.items():
                if column not in trade_review_columns:
                    conn.execute(text(f"alter table trade_reviews add column {column} {definition}"))
        quote_columns = {row[1] for row in conn.execute(text("pragma table_info(quote_summaries)")).fetchall()}
        if quote_columns:
            quote_additions = {
                "provider": "varchar default 'futu'",
                "market": "varchar default ''",
                "exchange": "varchar default ''",
                "is_delayed": "boolean default 0",
                "license_note": "text default ''",
            }
            for column, definition in quote_additions.items():
                if column not in quote_columns:
                    conn.execute(text(f"alter table quote_summaries add column {column} {definition}"))
        news_columns = {row[1] for row in conn.execute(text("pragma table_info(news_items)")).fetchall()}
        if news_columns:
            news_additions = {
                "provider": "varchar default 'futu'",
                "market": "varchar default ''",
                "news_type": "varchar default 'news'",
            }
            for column, definition in news_additions.items():
                if column not in news_columns:
                    conn.execute(text(f"alter table news_items add column {column} {definition}"))
        state_columns = {row[1] for row in conn.execute(text("pragma table_info(data_source_states)")).fetchall()}
        if state_columns:
            state_additions = {
                "account_id": "varchar default 'all'",
                "provider": "varchar default ''",
                "data_type": "varchar default ''",
                "market": "varchar default ''",
            }
            for column, definition in state_additions.items():
                if column not in state_columns:
                    conn.execute(text(f"alter table data_source_states add column {column} {definition}"))
        Base.metadata.create_all(bind=conn)
