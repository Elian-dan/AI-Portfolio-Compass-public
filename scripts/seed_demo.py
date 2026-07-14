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
                inserted_count=82,
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
                input_context={"demo": True, "account_count": 3},
                output={
                    "summary": "组合覆盖 A 股、港股与美股，盈亏持仓并存；优先复核深度亏损仓与科技成长暴露。",
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
        ("demo_cn", "A股演示账户", "演示券商 · 中国", "CNY", ["CN"], 1_050_000, 153_553, 896_447),
        ("demo_hk", "港股演示账户", "演示券商 · 香港", "HKD", ["HK"], 300_000, 52_020, 247_980),
        ("demo_us", "美股演示账户", "演示券商 · 美国", "USD", ["US"], 112_000, 11_904, 100_096),
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
        ("demo_cn", "SH.600519", "贵州茅台", "CN", "stock", 100, 1_100.00, 1_210.99, 121_099, "CNY", 121_099, "CNY", 1.0, 0.1009, "核心长期仓", "消费核心仓，演示盈利持仓与长期逻辑跟踪"),
        ("demo_cn", "SZ.300750", "宁德时代", "CN", "stock", 800, 410.00, 359.06, 287_248, "CNY", 287_248, "CNY", 1.0, -0.1242, "遗留观察仓", "成本较高且仍在亏损，演示持有理由复核"),
        ("demo_cn", "SH.601318", "中国平安", "CN", "stock", 1_500, 48.00, 52.40, 78_600, "CNY", 78_600, "CNY", 1.0, 0.0917, "中期配置仓", "金融与红利因子配置，观察估值修复持续性"),
        ("demo_cn", "SZ.000858", "五粮液", "CN", "stock", 600, 145.00, 132.50, 79_500, "CNY", 79_500, "CNY", 1.0, -0.0862, "核心长期仓", "消费行业分散配置，跟踪渠道与库存变化"),
        ("demo_cn", "FUND.110022", "易方达消费行业股票", "CN", "fund", 30_000, 2.55, 3.00, 90_000, "CNY", 90_000, "CNY", 1.0, 0.1765, "核心长期仓", "A股消费基金，作为行业分散工具长期持有"),
        ("demo_cn", "FUND.161725", "招商中证白酒指数", "CN", "fund", 35_000, 1.72, 2.00, 70_000, "CNY", 70_000, "CNY", 1.0, 0.1628, "中期配置仓", "白酒指数基金，演示行业主题暴露"),
        ("demo_cn", "FUND.005827", "易方达蓝筹精选混合", "CN", "fund", 25_000, 2.08, 2.40, 60_000, "CNY", 60_000, "CNY", 1.0, 0.1538, "核心长期仓", "主动权益基金，观察风格漂移与集中度"),
        ("demo_cn", "FUND.000311", "景顺长城沪深300指数增强", "CN", "fund", 30_000, 1.25, 1.50, 45_000, "CNY", 45_000, "CNY", 1.0, 0.2000, "核心长期仓", "宽基增强基金，作为A股底仓"),
        ("demo_cn", "FUND.003095", "中欧医疗健康混合", "CN", "fund", 25_000, 1.60, 1.40, 35_000, "CNY", 35_000, "CNY", 1.0, -0.1250, "遗留观察仓", "医药主题仓位承压，等待基本面验证"),
        ("demo_cn", "FUND.001632", "天弘中证食品饮料指数", "CN", "fund", 20_000, 1.25, 1.50, 30_000, "CNY", 30_000, "CNY", 1.0, 0.2000, "短期交易仓", "行业轮动试验仓，控制单一主题权重"),
        ("demo_hk", "HK.00700", "腾讯控股", "HK", "stock", 300, 390.00, 457.60, 137_280, "HKD", 137_280, "HKD", 1.0, 0.1733, "核心长期仓", "平台与内容业务核心暴露，演示港股盈利持仓"),
        ("demo_hk", "HK.09988", "阿里巴巴-W", "HK", "stock", 1_000, 132.00, 110.70, 110_700, "HKD", 110_700, "HKD", 1.0, -0.1614, "中期配置仓", "电商与云业务处于验证期，演示港股亏损持仓"),
        ("demo_us", "US.MSFT", "Microsoft", "US", "stock", 80, 420.00, 387.13, 30_970.40, "USD", 30_970.40, "USD", 1.0, -0.0783, "核心长期仓", "云与软件核心配置，演示美股浮亏持仓"),
        ("demo_us", "US.NVDA", "NVIDIA", "US", "stock", 140, 175.00, 207.18, 29_005.20, "USD", 29_005.20, "USD", 1.0, 0.1839, "短期交易仓", "高波动成长仓，演示美股盈利与交易纪律"),
        ("demo_us", "US.QQQ", "Invesco QQQ", "US", "fund", 45, 420.00, 444.00, 19_980.00, "USD", 19_980.00, "USD", 1.0, 0.0571, "核心长期仓", "纳斯达克100 ETF，作为美股科技底仓"),
        ("demo_us", "US.AAPL", "Apple", "US", "stock", 35, 188.00, 204.00, 7_140.00, "USD", 7_140.00, "USD", 1.0, 0.0851, "核心长期仓", "消费电子与服务业务长期配置"),
        ("demo_us", "US.AMZN", "Amazon", "US", "stock", 40, 162.00, 150.00, 6_000.00, "USD", 6_000.00, "USD", 1.0, -0.0741, "中期配置仓", "云业务与零售利润率进入验证期"),
        ("demo_us", "US.GOOGL", "Alphabet", "US", "stock", 25, 185.00, 200.00, 5_000.00, "USD", 5_000.00, "USD", 1.0, 0.0811, "核心长期仓", "广告与AI基础设施双重暴露"),
        ("demo_us", "US.META", "Meta Platforms", "US", "stock", 12, 420.00, 416.67, 5_000.04, "USD", 5_000.04, "USD", 1.0, -0.0079, "短期交易仓", "高波动成长仓，观察资本开支纪律"),
        ("demo_us", "US.TSLA", "Tesla", "US", "stock", 20, 230.00, 200.00, 4_000.00, "USD", 4_000.00, "USD", 1.0, -0.1304, "遗留观察仓", "波动较大，重新验证增长与估值匹配度"),
        ("demo_us", "US.JPM", "JPMorgan Chase", "US", "stock", 20, 190.00, 150.00, 3_000.00, "USD", 3_000.00, "USD", 1.0, -0.2105, "中期配置仓", "金融股分散配置，观察信用周期"),
    ]
    totals = {"demo_cn": 1_050_000, "demo_hk": 300_000, "demo_us": 112_000}
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

    # Prices and volumes are a frozen Futu OpenAPI snapshot captured for the
    # demo dataset. Cost prices remain fictional so the workspace intentionally
    # covers both profitable and losing positions.
    quotes = [
        ("SH.600519", "CN", "SSE", 1_210.99, 0.00499, 4_198_257),
        ("SZ.300750", "CN", "SZSE", 359.06, 0.02953, 46_290_681),
        ("SH.601318", "CN", "SSE", 52.40, 0.0081, 18_420_000),
        ("SZ.000858", "CN", "SZSE", 132.50, -0.0032, 12_880_000),
        ("FUND.110022", "CN", "FUND", 3.00, 0.0062, 8_200_000),
        ("FUND.161725", "CN", "FUND", 2.00, -0.0041, 6_700_000),
        ("FUND.005827", "CN", "FUND", 2.40, 0.0035, 5_900_000),
        ("FUND.000311", "CN", "FUND", 1.50, 0.0022, 4_100_000),
        ("FUND.003095", "CN", "FUND", 1.40, -0.0075, 3_800_000),
        ("FUND.001632", "CN", "FUND", 1.50, 0.0058, 3_200_000),
        ("HK.00700", "HK", "HKEX", 457.60, -0.00565, 24_291_842),
        ("HK.09988", "HK", "HKEX", 110.70, 0.00454, 100_489_536),
        ("US.MSFT", "US", "NASDAQ", 387.13, 0.00527, 3_170_937),
        ("US.NVDA", "US", "NASDAQ", 207.18, -0.01792, 17_144_823),
        ("US.QQQ", "US", "NASDAQ", 444.00, 0.0061, 28_120_000),
        ("US.AAPL", "US", "NASDAQ", 204.00, 0.0042, 31_600_000),
        ("US.AMZN", "US", "NASDAQ", 150.00, -0.0031, 25_400_000),
        ("US.GOOGL", "US", "NASDAQ", 200.00, 0.0078, 19_200_000),
        ("US.META", "US", "NASDAQ", 416.67, 0.0025, 8_600_000),
        ("US.TSLA", "US", "NASDAQ", 200.00, -0.0112, 42_800_000),
        ("US.JPM", "US", "NYSE", 150.00, 0.0018, 11_600_000),
    ]
    for code, market, exchange, price, change, volume in quotes:
        db.add(
            QuoteSummary(
                code=code,
                provider="futu_demo_snapshot",
                market=market,
                exchange=exchange,
                is_delayed=True,
                license_note="Futu OpenAPI 演示快照；仅用于功能展示，不代表实时行情",
                current_price=price,
                change_ratio=change,
                volume=volume,
                ma_summary={"trend": "demo_snapshot"},
                support_price=price * 0.92,
                resistance_price=price * 1.08,
                quote_time=now,
                sync_id=sync_id,
            )
        )

    cards = [
        ("HK.09988", "中期配置仓", "复核持有理由", "高", "P1", True, ["浮亏超过 15%", "业务验证尚未完成"], ["不要仅因浮亏机械补仓"]),
        ("SZ.300750", "遗留观察仓", "控制仓位", "高", "P1", True, ["成本区距离现价较远", "需要重新验证持仓逻辑"], ["关注行业价格竞争"]),
        ("US.NVDA", "短期交易仓", "按计划持有", "中", "P2", False, ["交易仓处于盈利状态", "波动仍然较高"], ["避免盈利后放宽失效条件"]),
        ("HK.00700", "核心长期仓", "继续观察", "中", "P3", False, ["长期逻辑稳定", "当前持仓处于盈利区间"], ["关注主题合计权重"]),
        ("US.MSFT", "核心长期仓", "继续观察", "中", "P2", False, ["长期逻辑尚未失效", "当前浮亏处于可复核区间"], ["关注云业务投入与利润率"]),
        ("SH.600519", "核心长期仓", "保持配置", "中", "P3", False, ["消费核心仓处于盈利区间", "组合权重仍在计划范围"], ["关注需求与渠道库存变化"]),
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
                generation_source="ai",
                model="deterministic-demo",
                generated_at=now,
                input_version=sync_id,
                analysis_framework={"layer": layer, "focus": reasons},
                missing_data=[],
                invalid_conditions=[],
                created_at=now,
            )
        )

    demo_news = [
        ("SH.600519", "演示资讯：消费需求与渠道库存成为白酒板块跟踪重点"),
        ("SZ.300750", "演示资讯：新能源产业链价格与海外业务进展受到关注"),
        ("HK.00700", "演示资讯：游戏与广告业务表现进入新的观察窗口"),
        ("HK.09988", "演示资讯：电商竞争与云业务进展成为市场关注点"),
        ("US.MSFT", "演示资讯：云业务投入与利润率变化受到投资者关注"),
        ("US.NVDA", "演示资讯：高性能计算需求与供应节奏仍是核心变量"),
    ]
    for index, (code, title) in enumerate(demo_news, start=1):
        db.add(WatchlistItem(group_name="演示关注", code=code, name=code, source="fictional_demo", updated_at=now))
        db.add(
            NewsItem(
                news_id=f"demo_news_{index}",
                code=code,
                provider="fictional_demo",
                market=code.split(".", 1)[0],
                title=title,
                source="演示资讯（脱敏改写）",
                publish_time=now - timedelta(minutes=index * 7),
                related_securities=[{"code": code}],
                url="",
                fetched_at=now,
                sync_id=sync_id,
            )
        )


def _seed_reviews(db: Session, now: datetime) -> None:
    trades = [
        ("demo_cn", "demo_deal_1", "SH.600519", "BUY", 1_100.00, 100, now - timedelta(days=120), "消费核心仓按计划分批建立", ["价值配置", "执行纪律好"]),
        ("demo_cn", "demo_deal_2", "SZ.300750", "BUY", 410.00, 800, now - timedelta(days=75), "新能源景气修复预期，等待后续验证", ["左侧布局", "执行犹豫"]),
        ("demo_cn", "demo_deal_7", "SH.601318", "BUY", 48.00, 1_500, now - timedelta(days=108), "红利与金融修复，作为中期分散配置", ["估值修复", "执行纪律好"]),
        ("demo_cn", "demo_deal_8", "SZ.000858", "BUY", 145.00, 600, now - timedelta(days=88), "消费龙头分散配置，等待需求回暖", ["价值配置", "执行犹豫"]),
        ("demo_cn", "demo_deal_9", "FUND.110022", "BUY", 2.55, 30_000, now - timedelta(days=210), "用消费行业基金替代单一个股暴露", ["基金定投", "执行纪律好"]),
        ("demo_cn", "demo_deal_10", "FUND.161725", "BUY", 1.72, 35_000, now - timedelta(days=168), "白酒指数回撤后分批建立仓位", ["行业配置", "执行纪律好"]),
        ("demo_cn", "demo_deal_11", "FUND.005827", "BUY", 2.08, 25_000, now - timedelta(days=145), "主动权益基金作为A股底仓补充", ["长期配置", "执行纪律好"]),
        ("demo_cn", "demo_deal_12", "FUND.000311", "BUY", 1.25, 30_000, now - timedelta(days=132), "沪深300增强基金定投", ["宽基配置", "执行纪律好"]),
        ("demo_cn", "demo_deal_13", "FUND.003095", "BUY", 1.60, 25_000, now - timedelta(days=98), "医疗行业回撤后左侧试仓", ["左侧布局", "执行犹豫"]),
        ("demo_cn", "demo_deal_14", "FUND.001632", "BUY", 1.25, 20_000, now - timedelta(days=42), "食品饮料行业轮动试验仓", ["行业轮动", "执行纪律好"]),
        ("demo_hk", "demo_deal_3", "HK.00700", "BUY", 390.00, 300, now - timedelta(days=96), "平台业务修复，作为港股核心仓配置", ["趋势跟随", "执行纪律好"]),
        ("demo_hk", "demo_deal_4", "HK.09988", "BUY", 132.00, 1_000, now - timedelta(days=64), "估值修复预期，计划分阶段验证", ["估值修复", "执行犹豫"]),
        ("demo_us", "demo_deal_5", "US.MSFT", "BUY", 420.00, 80, now - timedelta(days=52), "云业务长期配置，按季度复核", ["长期配置", "执行纪律好"]),
        ("demo_us", "demo_deal_6", "US.NVDA", "BUY", 175.00, 140, now - timedelta(minutes=5), "高性能计算趋势仓，小仓位试错", ["突破", "执行纪律好"]),
        ("demo_us", "demo_deal_15", "US.QQQ", "BUY", 420.00, 45, now - timedelta(days=130), "纳斯达克100作为美股核心底仓", ["宽基配置", "执行纪律好"]),
        ("demo_us", "demo_deal_16", "US.AAPL", "BUY", 188.00, 35, now - timedelta(days=101), "硬件与服务生态长期配置", ["长期配置", "执行纪律好"]),
        ("demo_us", "demo_deal_17", "US.AMZN", "BUY", 162.00, 40, now - timedelta(days=82), "云业务与零售利润率改善预期", ["成长配置", "执行犹豫"]),
        ("demo_us", "demo_deal_18", "US.GOOGL", "BUY", 185.00, 25, now - timedelta(days=76), "广告业务稳健，AI投入进入验证期", ["长期配置", "执行纪律好"]),
        ("demo_us", "demo_deal_19", "US.META", "BUY", 420.00, 12, now - timedelta(days=60), "高质量成长仓，小仓位参与", ["突破", "执行纪律好"]),
        ("demo_us", "demo_deal_20", "US.TSLA", "BUY", 230.00, 20, now - timedelta(days=48), "高波动主题仓，设置明确失效条件", ["主题交易", "执行犹豫"]),
        ("demo_us", "demo_deal_21", "US.JPM", "BUY", 190.00, 20, now - timedelta(days=35), "金融股分散科技集中度", ["分散配置", "执行纪律好"]),
        ("demo_cn", "demo_deal_22", "FUND.110022", "BUY", 2.92, 5_000, now - timedelta(days=18), "消费基金回撤后补充一笔", ["分批买入", "执行纪律好"]),
        ("demo_us", "demo_deal_23", "US.QQQ", "BUY", 438.00, 10, now - timedelta(days=12), "QQQ回调后的定期加仓", ["定期加仓", "执行纪律好"]),
        ("demo_us", "demo_deal_24", "US.NVDA", "SELL", 212.00, 20, now - timedelta(days=3), "盈利后按计划落袋一部分", ["分批止盈", "执行纪律好"]),
    ]
    latest_prices = {
        "SH.600519": 1_210.99,
        "SZ.300750": 359.06,
        "SH.601318": 52.40,
        "SZ.000858": 132.50,
        "FUND.110022": 3.00,
        "FUND.161725": 2.00,
        "FUND.005827": 2.40,
        "FUND.000311": 1.50,
        "FUND.003095": 1.40,
        "FUND.001632": 1.50,
        "HK.00700": 457.60,
        "HK.09988": 110.70,
        "US.MSFT": 387.13,
        "US.NVDA": 207.18,
        "US.QQQ": 444.00,
        "US.AAPL": 204.00,
        "US.AMZN": 150.00,
        "US.GOOGL": 200.00,
        "US.META": 416.67,
        "US.TSLA": 200.00,
        "US.JPM": 150.00,
    }
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
            portfolio_summary={"position_count": 21, "base_currency": "CNY", "max_position_weight": 0.24},
            advice_summary={"card_count": 6, "p0_p1_count": 3},
            user_action_summary={"recorded_actions": 24},
            result_summary={"status": "已生成虚拟复盘"},
            next_watchlist=["SZ.300750", "HK.09988", "US.MSFT"],
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

组合由三个相互独立的虚拟账户构成，覆盖 A 股、港股、美股以及人民币、港币、美元三种币种。持仓同时包含盈利与亏损场景，便于完整演示组合分析流程。

## 二、优先复核

- 宁德时代与阿里巴巴处于亏损区间，应重新验证持有理由。
- 腾讯与英伟达已有浮盈，仍需按原计划管理仓位而非放宽纪律。
- 科技成长主题合计暴露需要定期检查，避免相关性被低估。

> 本报告中的账户、金额、持仓与交易均为虚构数据，不构成投资建议。
"""


if __name__ == "__main__":
    raise SystemExit(main())
