#!/usr/bin/env python3
"""Create a fictional portfolio in an isolated demo database.

The script intentionally refuses to run unless DATABASE_URL points to a SQLite
file whose name contains ``demo``. It is meant for screenshots and local demos,
never for a user's normal portfolio database.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.models import (  # noqa: E402
    AIWorkflowRun,
    Account,
    AccountSnapshot,
    Deal,
    DecisionCard,
    ExchangeRate,
    InvestorPreference,
    NewsItem,
    PositionSnapshot,
    ProfileVersion,
    QuoteSummary,
    ReviewReport,
    SyncTask,
    TradeReview,
    WatchlistItem,
)
from app.services.profile_workflows import (  # noqa: E402
    build_artifacts,
    build_home_summary_cards,
    build_workflow_context,
)


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("sqlite:///") or "demo" not in database_url.lower():
        print("Refusing to seed: DATABASE_URL must be a SQLite path containing 'demo'.")
        return 2

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    sync_id = "demo_sync_001"
    with Session(engine) as db:
        _seed_accounts(db, now, sync_id)
        _seed_positions(db, now, sync_id)
        _seed_market_context(db, now, sync_id)
        _seed_reviews(db, now)
        _seed_profile(db, now)
        db.add(
            SyncTask(
                sync_id=sync_id,
                sync_type="演示数据初始化",
                status="成功",
                start_time=now - timedelta(seconds=3),
                end_time=now,
                source="fictional_demo",
                inserted_count=31,
                updated_count=0,
                idempotency_key=sync_id,
            )
        )
        db.commit()

        context = build_workflow_context(db, "all")
        artifacts = build_artifacts("portfolio_diagnosis", context)
        cards = build_home_summary_cards("portfolio_diagnosis", context, artifacts)
        db.add(
            AIWorkflowRun(
                run_id="demo_portfolio_diagnosis",
                workflow_type="portfolio_diagnosis",
                account_id="all",
                question="基于虚拟多账户持仓进行组合体检",
                status="completed",
                steps=[
                    {"step": "读取虚拟快照", "status": "completed"},
                    {"step": "统一币种与合并暴露", "status": "completed"},
                    {"step": "生成组合诊断", "status": "completed"},
                ],
                input_context={"demo": True, "account_count": 2},
                output={
                    "summary": "组合跨 A 股、港股与美股配置，现金缓冲充足；科技成长暴露需要定期复核。",
                    "markdown": _demo_report(),
                    "home_summary_cards": cards,
                },
                artifacts=artifacts,
                provider="local-demo",
                model="deterministic-demo",
                data_version=sync_id,
                created_at=now + timedelta(seconds=1),
                updated_at=now + timedelta(seconds=1),
            )
        )
        db.commit()

    print(f"Fictional demo portfolio created at {database_url.removeprefix('sqlite:///')}")
    return 0


def _seed_accounts(db: Session, now: datetime, sync_id: str) -> None:
    rows = [
        ("demo_cn", "本地配置账户", "演示券商 A", "CNY", ["CN"], 620_000, 80_000, 540_000),
        ("demo_global", "全球资产账户", "演示券商 B", "USD", ["US", "HK"], 72_000, 9_000, 63_000),
    ]
    for account_id, name, institution, currency, markets, total, cash, market_value in rows:
        db.add(
            Account(
                account_id=account_id,
                source_name="fictional_demo",
                broker_provider="manual",
                display_name=name,
                institution=institution,
                import_mode="manual",
                position_import_modes="manual",
                review_import_modes="manual",
                account_type="demo",
                trade_env="SIMULATE",
                markets=markets,
                base_currency=currency,
                total_assets=total,
                cash=cash,
                market_value=market_value,
                last_sync_time=now,
            )
        )
        db.add(
            AccountSnapshot(
                account_id=account_id,
                total_assets=total,
                cash=cash,
                market_value=market_value,
                raw_currency_values={"currency": currency, "dataset": "fictional_demo"},
                snapshot_time=now,
                sync_id=sync_id,
            )
        )


def _seed_positions(db: Session, now: datetime, sync_id: str) -> None:
    positions = [
        ("demo_cn", "FUND.510300", "沪深300ETF", "CN", "fund", 5_000, 38.40, 42.00, 210_000, "CNY", 210_000, "CNY", 1.0, 0.0938, "核心长期仓", "宽基底仓，承担组合稳定器角色"),
        ("demo_cn", "CN.600519", "消费龙头A", "CN", "stock", 100, 1_320, 1_450, 145_000, "CNY", 145_000, "CNY", 1.0, 0.0985, "中期配置仓", "虚拟消费龙头，用于展示行业分散"),
        ("demo_cn", "FUND.511010", "国债ETF", "CN", "fund", 900, 102.00, 105.56, 95_000, "CNY", 95_000, "CNY", 1.0, 0.0349, "核心长期仓", "低波动资产，提供流动性缓冲"),
        ("demo_cn", "CN.300750", "新能源龙头A", "CN", "stock", 500, 215.00, 180.00, 90_000, "CNY", 90_000, "CNY", 1.0, -0.1628, "遗留观察仓", "回撤较深，等待重新验证持有理由"),
        ("demo_global", "US.MSFT", "Microsoft", "US", "stock", 50, 420.00, 500.00, 25_000, "USD", 25_000, "USD", 1.0, 0.1905, "核心长期仓", "全球软件与云计算核心暴露"),
        ("demo_global", "US.VTI", "Vanguard Total Stock Market ETF", "US", "fund", 60, 270.00, 300.00, 18_000, "USD", 18_000, "USD", 1.0, 0.1111, "核心长期仓", "美股宽基配置，降低单票依赖"),
        ("demo_global", "HK.00700", "Tencent", "HK", "stock", 250, 330.00, 375.00, 93_750, "HKD", 12_000, "USD", 0.128, 0.1364, "中期配置仓", "互联网平台配置，关注估值与监管变化"),
        ("demo_global", "US.NVDA", "NVIDIA", "US", "stock", 50, 180.00, 160.00, 8_000, "USD", 8_000, "USD", 1.0, -0.1111, "短期交易仓", "波动较高，按交易计划控制仓位"),
    ]
    totals = {"demo_cn": 620_000, "demo_global": 72_000}
    for row in positions:
        (
            account_id,
            code,
            name,
            market,
            asset_type,
            quantity,
            average_cost,
            current_price,
            raw_value,
            raw_currency,
            normalized_value,
            normalized_currency,
            fx_rate,
            profit_loss_ratio,
            layer,
            reason,
        ) = row
        db.add(
            PositionSnapshot(
                account_id=account_id,
                code=code,
                name=name,
                market=market,
                asset_type=asset_type,
                quantity=quantity,
                average_cost=average_cost,
                current_price=current_price,
                raw_market_value=raw_value,
                raw_currency=raw_currency,
                normalized_market_value=normalized_value,
                normalized_currency=normalized_currency,
                exchange_rate_to_base=fx_rate,
                position_weight=normalized_value / totals[account_id],
                profit_loss_ratio=profit_loss_ratio,
                first_buy_time=now - timedelta(days=420 if layer == "核心长期仓" else 150),
                last_trade_time=now - timedelta(days=14),
                position_layer=layer,
                layer_source="fictional_demo",
                layer_confidence="高",
                layer_reason=reason,
                snapshot_time=now,
                sync_id=sync_id,
            )
        )


def _seed_market_context(db: Session, now: datetime, sync_id: str) -> None:
    for quote, rate in (("USD", 1 / 7.2), ("HKD", 1 / 0.92)):
        db.add(
            ExchangeRate(
                base_currency="CNY",
                quote_currency=quote,
                rate=rate,
                source="frankfurter",
                rate_time=now,
                fetched_at=now,
                expires_at=now + timedelta(hours=12),
                is_stale=False,
                raw_payload={"dataset": "fictional_demo"},
            )
        )

    quotes = [
        ("FUND.510300", "CN", 42.00, 0.004),
        ("CN.600519", "CN", 1_450.00, -0.006),
        ("FUND.511010", "CN", 105.56, 0.001),
        ("CN.300750", "CN", 180.00, -0.012),
        ("US.MSFT", "US", 500.00, 0.008),
        ("US.VTI", "US", 300.00, 0.003),
        ("HK.00700", "HK", 375.00, 0.011),
        ("US.NVDA", "US", 160.00, -0.018),
    ]
    for code, market, price, change in quotes:
        db.add(
            QuoteSummary(
                code=code,
                provider="fictional_demo",
                market=market,
                exchange="DEMO",
                current_price=price,
                change_ratio=change,
                volume=1_000_000,
                ma_summary={"trend": "demo"},
                support_price=price * 0.92,
                resistance_price=price * 1.08,
                quote_time=now,
                sync_id=sync_id,
            )
        )

    cards = [
        ("CN.300750", "遗留观察仓", "复核持有理由", "高", "P1", True, ["回撤超过 15%", "持仓逻辑需要重新验证"], ["不要仅因浮亏继续持有"]),
        ("US.NVDA", "短期交易仓", "控制仓位", "中", "P1", True, ["短线波动扩大", "交易仓需遵守失效条件"], ["避免追涨杀跌"]),
        ("US.MSFT", "核心长期仓", "继续观察", "中", "P2", False, ["长期逻辑稳定", "单票暴露处于可控区间"], ["关注科技主题合计权重"]),
        ("FUND.510300", "核心长期仓", "保持配置", "中", "P3", False, ["宽基底仓分散单票风险"], ["定期检查组合整体偏离"]),
    ]
    for index, (code, layer, recommendation, confidence, priority, action, reasons, risks) in enumerate(cards, start=1):
        db.add(
            DecisionCard(
                card_id=f"demo_card_{index}",
                code=code,
                position_layer=layer,
                recommendation=recommendation,
                confidence=confidence,
                reasons=reasons,
                risks=risks,
                key_prices={},
                data_time=now,
                action_required=action,
                data_version=sync_id,
                status="正常",
                priority=priority,
                generation_source="fictional_demo",
                model="local_rules",
                generated_at=now,
                input_version=sync_id,
                analysis_framework={"layer": layer, "focus": reasons},
                missing_data=[],
                invalid_conditions=[],
                created_at=now,
            )
        )

    for index, code in enumerate(("US.MSFT", "US.VTI", "HK.00700"), start=1):
        db.add(WatchlistItem(group_name="演示关注", code=code, name=code, source="fictional_demo", updated_at=now))
        db.add(
            NewsItem(
                news_id=f"demo_news_{index}",
                code=code,
                provider="fictional_demo",
                market=code.split(".", 1)[0],
                title=f"{code} 虚拟资讯：用于展示本地新闻摘要布局",
                source="Demo Newsroom",
                publish_time=now - timedelta(minutes=index * 7),
                related_securities=[{"code": code}],
                url="",
                fetched_at=now,
                sync_id=sync_id,
            )
        )


def _seed_reviews(db: Session, now: datetime) -> None:
    trades = [
        ("demo_global", "demo_deal_1", "US.NVDA", "BUY", 172.00, 25, now - timedelta(days=18), "短线突破后小仓试错", ["突破", "执行纪律好"]),
        ("demo_cn", "demo_deal_2", "CN.300750", "BUY", 205.00, 200, now - timedelta(days=45), "行业景气修复预期，计划分批验证", ["低吸", "执行犹豫"]),
        ("demo_global", "demo_deal_3", "US.MSFT", "BUY", 455.00, 20, now - timedelta(minutes=5), "核心仓按月度计划补充", ["趋势跟随", "执行纪律好"]),
    ]
    latest_prices = {"US.NVDA": 160.00, "CN.300750": 180.00, "US.MSFT": 500.00}
    for index, (account_id, deal_id, code, side, price, quantity, deal_time, note, tags) in enumerate(trades, start=1):
        db.add(
            Deal(
                deal_id=deal_id,
                order_id=f"demo_order_{index}",
                code=code,
                side=side,
                price=price,
                quantity=quantity,
                deal_time=deal_time,
                market=code.split(".", 1)[0],
                account_id=account_id,
                raw_payload={"dataset": "fictional_demo"},
            )
        )
        latest = latest_prices[code]
        latest_return = (latest - price) / price
        db.add(
            TradeReview(
                review_id=f"demo_trade_review_{index}",
                account_id=account_id,
                deal_id=deal_id,
                order_id=f"demo_order_{index}",
                code=code,
                side=side,
                price=price,
                quantity=quantity,
                deal_time=deal_time,
                one_day_price=price * 1.01,
                five_day_price=price * (0.95 if latest_return < 0 else 1.04),
                latest_price=latest,
                one_day_return=0.01,
                five_day_return=-0.05 if latest_return < 0 else 0.04,
                latest_return=latest_return,
                result_label="买后承压" if latest_return < 0 else "计划内买入",
                discipline_label="计划内执行" if "执行纪律好" in tags else "需要复核",
                confidence="高",
                fact_summary={"dataset": "fictional_demo"},
                ai_commentary="虚拟复盘内容：对照原始计划检查执行，不以单次盈亏替代纪律判断。",
                user_note=note,
                intent_tags={"trend": tags[:1], "market": ["市场中性"], "fundamental": [], "emotion": tags[1:]},
                intent_plan={"holding_period": "1-6 个月", "stop_loss_type": "逻辑失效", "take_profit_type": "分批", "stop_loss_price": "", "take_profit_price": ""},
                generated_by="fictional_demo",
                created_at=now,
                updated_at=now,
            )
        )

    db.add(
        ReviewReport(
            review_id="demo_review_report",
            review_date=now.date().isoformat(),
            portfolio_summary={"position_count": 8, "base_currency": "CNY", "max_position_weight": 0.185},
            advice_summary={"card_count": 4, "p0_p1_count": 2},
            user_action_summary={"recorded_actions": 3},
            result_summary={"status": "已生成虚拟复盘"},
            next_watchlist=["CN.300750", "US.NVDA", "US.MSFT"],
            created_at=now,
        )
    )


def _seed_profile(db: Session, now: datetime) -> None:
    db.add(
        ProfileVersion(
            profile_id="demo_profile",
            generated_at=now,
            confidence="高",
            core_position_ratio=0.58,
            mid_position_ratio=0.25,
            trade_position_ratio=0.07,
            option_position_ratio=0,
            tags=["多市场配置", "核心卫星", "重视复盘"],
            change_reason="基于虚拟持仓与成交记录生成",
        )
    )
    db.add(
        InvestorPreference(
            preference_id="demo_preference",
            account_id="all",
            kyc_profile={"dataset": "fictional_demo"},
            risk_tolerance="中等",
            investment_horizon="3-5 年",
            liquidity_needs="保留 10% 以上现金缓冲",
            target_return="长期跑赢通胀与宽基",
            notes="仅用于公开演示截图",
            updated_at=now,
        )
    )


def _demo_report() -> str:
    return """# 虚拟组合诊断报告

## 一、组合总览

组合由两个虚拟账户构成，覆盖人民币、美元和港币资产。现金缓冲充足，宽基与债券资产提供基础稳定性。

## 二、优先复核

- 新能源遗留观察仓回撤较深，应重新验证持有理由。
- 科技成长主题合计暴露需要定期检查，避免相关性被低估。
- 短期交易仓按预设失效条件管理，不以单日波动替代计划。

> 本报告中的账户、金额、持仓与交易均为虚构数据，不构成投资建议。
"""


if __name__ == "__main__":
    raise SystemExit(main())
