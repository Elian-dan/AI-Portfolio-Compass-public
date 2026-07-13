from app.services.providers import account_provider_statuses, normalize_symbol, provider_registry


def test_provider_registry_routes_account_source_first():
    registry = provider_registry()

    hk_quote = registry.choose(data_type="quote", market="HK", broker_provider="futu")
    us_news = registry.choose(data_type="news", market="US", broker_provider="", preferred=["alpha_vantage"])
    cn_announcement = registry.choose(data_type="announcement", market="CN", broker_provider="")

    assert hk_quote is not None
    assert hk_quote.name == "futu"
    assert us_news is not None
    assert us_news.name == "alpha_vantage"
    assert cn_announcement is not None
    assert cn_announcement.name == "cninfo"


def test_non_futu_cn_account_does_not_route_to_futu_opend():
    states = account_provider_statuses("alipay", ["CN"])
    quote = next(item for item in states if item["data_type"] == "quote")
    news = next(item for item in states if item["data_type"] == "news")
    announcement = next(item for item in states if item["data_type"] == "announcement")

    assert quote["provider"] == "tushare"
    assert news["status"] == "unsupported"
    assert announcement["provider"] == "cninfo"
    assert all(item["provider"] != "futu" for item in states)


def test_provider_health_reports_not_configured_for_missing_keys():
    states = account_provider_statuses("manual", ["US"])
    alpaca_quote = next(item for item in states if item["data_type"] == "quote" and item["provider"] == "alpaca")

    assert alpaca_quote["status"] == "not_configured"
    assert "ALPACA_API_KEY" in alpaca_quote["message"]


def test_symbol_normalization_for_supported_markets():
    assert normalize_symbol("US.AAPL", "alpaca") == "AAPL"
    assert normalize_symbol("HK.00700", "futu") == "HK.00700"
    assert normalize_symbol("CN.600519", "tushare") == "600519.SH"
    assert normalize_symbol("CN.000001", "tushare") == "000001.SZ"
