from datetime import datetime, timezone

from app.services.imports import ImportSnapshot, _supplement_markets


def _snapshot(name: str, market: str = "CN") -> ImportSnapshot:
    return ImportSnapshot(
        accounts=[{"account_id": "alipay_fund", "markets": []}],
        account_snapshots=[],
        positions=[
            {
                "account_id": "alipay_fund",
                "code": "FUND.270042",
                "name": name,
                "market": market,
                "asset_type": "fund",
                "normalized_market_value": 1000,
                "normalized_currency": "CNY",
                "missing_market_code": False,
                "snapshot_time": datetime.now(timezone.utc),
            }
        ],
    )


def test_alipay_nasdaq_fund_market_is_supplemented_to_us():
    snapshot = _snapshot("广发纳斯达克100ETF联接人民币")

    warnings = _supplement_markets(snapshot, "alipay")

    assert snapshot.positions[0]["market"] == "US"
    assert snapshot.accounts[0]["markets"] == ["US"]
    assert warnings == ["已根据基金/持仓名称补充 1 条市场字段"]


def test_alipay_qdii_without_region_keeps_existing_market():
    snapshot = _snapshot("某全球精选QDII基金")

    warnings = _supplement_markets(snapshot, "alipay")

    assert snapshot.positions[0]["market"] == "CN"
    assert snapshot.accounts[0]["markets"] == ["CN"]
    assert warnings == []


def test_missing_market_can_be_inferred_from_position_name():
    snapshot = _snapshot("恒生科技指数基金", market="")

    _supplement_markets(snapshot, "excel")

    assert snapshot.positions[0]["market"] == "HK"
    assert snapshot.accounts[0]["markets"] == ["HK"]
