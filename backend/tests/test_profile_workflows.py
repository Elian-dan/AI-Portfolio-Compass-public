from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AccountSnapshot, PositionSnapshot
from app.services.sync import latest_account_snapshots, latest_positions
from app.services.profile_workflows import audit_calculation_pack_locally, build_artifacts, build_calculation_audit_pack, build_workflow_context


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _account(account_id: str, total_assets: float, cash: float, market_value: float, currency: str) -> AccountSnapshot:
    return AccountSnapshot(
        account_id=account_id,
        total_assets=total_assets,
        cash=cash,
        market_value=market_value,
        raw_currency_values={"currency": currency},
        snapshot_time=datetime.now(timezone.utc),
        sync_id="sync",
    )


def _position(
    account_id: str,
    code: str,
    value: float,
    currency: str,
    account_weight: float,
    pl_ratio: float = 0,
    asset_type: str = "stock",
) -> PositionSnapshot:
    return PositionSnapshot(
        account_id=account_id,
        code=code,
        name=code,
        market=code.split(".")[0],
        asset_type=asset_type,
        quantity=1,
        average_cost=100,
        current_price=100,
        raw_market_value=value,
        raw_currency=currency,
        normalized_market_value=value,
        normalized_currency=currency,
        exchange_rate_to_base=1,
        position_weight=account_weight,
        profit_loss_ratio=pl_ratio,
        position_layer="中期配置仓",
        layer_source="test",
        layer_confidence="高",
        layer_reason="test",
        snapshot_time=datetime.now(timezone.utc),
        sync_id="sync",
    )


def test_workflow_recomputes_cross_account_weights_before_merging():
    db = _session()
    db.add_all(
        [
            _account("hk", total_assets=10000, cash=1000, market_value=9000, currency="HKD"),
            _account("usd", total_assets=100, cash=20, market_value=80, currency="USD"),
            _position("hk", "US.QQQ", value=8000, currency="HKD", account_weight=0.8),
            _position("hk", "US.NVDA", value=1000, currency="HKD", account_weight=0.1),
            _position("usd", "US.NVDA", value=80, currency="USD", account_weight=0.8),
        ]
    )
    db.commit()

    context = build_workflow_context(db, "all")
    exposures = {item["code"]: item for item in context["position_exposures"]}

    assert context["portfolio"]["base_currency"] == "CNY"
    assert exposures["US.QQQ"]["weight"] > exposures["US.NVDA"]["weight"]
    assert round(exposures["US.NVDA"]["weight"], 4) == round((1000 * 0.92 + 80 * 7.2) / (10000 * 0.92 + 100 * 7.2), 4)
    assert exposures["US.NVDA"]["weight"] < 0.2
    assert context["portfolio"]["max_position_weight"] == exposures["US.QQQ"]["weight"]


def test_workflow_artifacts_use_real_labels_cash_and_return_contribution():
    context = {
        "portfolio": {"cash_ratio": 0.1, "base_currency": "CNY"},
        "positions": [],
        "position_exposures": [
            {"code": "US.QQQ", "name": "QQQ", "asset_type": "stock", "source_currency": "USD", "weight": 0.5, "profit_loss_ratio": 0.02},
            {"code": "FUND.BOND", "name": "债券基金", "asset_type": "fund", "source_currency": "CNY", "weight": 0.4, "profit_loss_ratio": -0.01},
        ],
    }

    artifacts = {item["artifact_id"]: item for item in build_artifacts("portfolio_diagnosis", context)}

    asset_labels = {item["label"] for item in artifacts["asset_allocation"]["data"]}
    currency_labels = {item["label"] for item in artifacts["currency_allocation"]["data"]}
    contribution = {item["label"]: item["value"] for item in artifacts["holding_return_rank"]["data"]}

    assert asset_labels == {"股票", "基金/ETF", "现金"}
    assert currency_labels == {"USD", "CNY"}
    assert sum(item["value"] for item in artifacts["asset_allocation"]["data"]) == 1
    assert contribution["US.QQQ"] == 0.01
    assert contribution["FUND.BOND"] == -0.004


def test_calculation_audit_pack_uses_merged_total_asset_weights_and_formulas():
    context = {
        "data_version": "test",
        "generated_at": "now",
        "portfolio": {"cash_ratio": 0.1, "base_currency": "CNY", "total_assets": 1000, "market_value": 900, "cash": 100, "weight_basis": "CNY total_assets"},
        "positions": [
            {"account_id": "a", "code": "US.NVDA", "market_value": 100, "weight": 0.1, "account_weight": 0.8, "profit_loss_ratio": 0.2, "asset_type": "stock", "source_currency": "USD"},
            {"account_id": "b", "code": "US.NVDA", "market_value": 50, "weight": 0.05, "account_weight": 0.9, "profit_loss_ratio": 0.1, "asset_type": "stock", "source_currency": "USD"},
            {"account_id": "a", "code": "US.QQQ", "market_value": 750, "weight": 0.75, "account_weight": 0.7, "profit_loss_ratio": 0.01, "asset_type": "fund", "source_currency": "USD"},
        ],
        "position_exposures": [
            {"code": "US.QQQ", "market_value": 750, "weight": 0.75, "account_weight": 0.7, "profit_loss_ratio": 0.01, "asset_type": "fund", "source_currency": "USD", "account_positions": [{"account_id": "a"}]},
            {"code": "US.NVDA", "market_value": 150, "weight": 0.15, "account_weight": 0.8, "profit_loss_ratio": 0.1666667, "asset_type": "stock", "source_currency": "USD", "account_positions": [{"account_id": "a"}, {"account_id": "b"}]},
        ],
        "news": [],
    }
    artifacts = build_artifacts("portfolio_diagnosis", context)

    pack = build_calculation_audit_pack(context, artifacts)
    audit = audit_calculation_pack_locally(pack)
    contribution = {item["label"]: item["value"] for item in pack["return_contribution_rank"]}

    assert pack["largest_exposure"]["code"] == "US.QQQ"
    assert pack["top5_weights"][1]["code"] == "US.NVDA"
    assert pack["top5_weights"][1]["weight"] == 0.15
    assert pack["top5_weights"][1]["weight"] != 1.7
    assert round(contribution["US.NVDA"], 6) == round(0.15 * 0.1666667, 6)
    assert audit["status"] == "ok"


def test_latest_queries_ignore_legacy_sample_template_data():
    db = _session()
    sample_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
    real_time = datetime(2026, 7, 4, tzinfo=timezone.utc)
    db.add_all(
        [
            AccountSnapshot(
                account_id="alipay_fund",
                total_assets=133682.57,
                cash=0,
                market_value=133682.57,
                raw_currency_values={"currency": "CNY", "parser": "sample_template"},
                snapshot_time=sample_time,
                sync_id="import_alipay_sample",
            ),
            _position("alipay_fund", "FUND.002611", value=14571.16, currency="CNY", account_weight=0.1),
            _account("real_account", total_assets=1000, cash=100, market_value=900, currency="CNY"),
            _position("real_account", "US.NVDA", value=900, currency="CNY", account_weight=0.9),
        ]
    )
    for item in db.query(PositionSnapshot).filter(PositionSnapshot.account_id == "alipay_fund"):
        item.sync_id = "import_alipay_sample"
        item.snapshot_time = sample_time
    for item in db.query(PositionSnapshot).filter(PositionSnapshot.account_id == "real_account"):
        item.snapshot_time = real_time
    db.commit()

    accounts = latest_account_snapshots(db)
    positions = latest_positions(db)

    assert {item.account_id for item in accounts} == {"real_account"}
    assert {item.account_id for item in positions} == {"real_account"}
