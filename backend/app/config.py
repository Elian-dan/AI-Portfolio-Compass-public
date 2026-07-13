from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional before dependency install
    load_dotenv = None


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"

if load_dotenv:
    load_dotenv(PROJECT_DIR / ".env")


class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'ai_trader.db'}"
    db_encryption_key: str = os.getenv("DB_ENCRYPTION_KEY", "")
    futu_host: str = os.getenv("FUTU_OPEND_HOST", "127.0.0.1")
    futu_port: int = int(os.getenv("FUTU_OPEND_PORT", "11111"))
    futu_trd_env: str = os.getenv("FUTU_TRD_ENV", "REAL")
    futu_default_market: str = os.getenv("FUTU_DEFAULT_MARKET", "US")
    futu_acc_id: str = os.getenv("FUTU_ACC_ID", "")
    futu_security_firm: str = os.getenv("FUTU_SECURITY_FIRM", "FUTUSECURITIES")
    news_provider: str = os.getenv("NEWS_PROVIDER", "marketaux")
    marketaux_api_token: str = os.getenv("MARKETAUX_API_TOKEN", "")
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_base_url: str = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
    alpha_vantage_api_key: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    fmp_api_key: str = os.getenv("FMP_API_KEY", "")
    polygon_api_key: str = os.getenv("POLYGON_API_KEY", "")
    tushare_token: str = os.getenv("TUSHARE_TOKEN", "")
    market_data_provider_priority: str = os.getenv("MARKET_DATA_PROVIDER_PRIORITY", "")
    news_provider_priority: str = os.getenv("NEWS_PROVIDER_PRIORITY", "")
    ai_provider: str = os.getenv("AI_PROVIDER", "deepseek")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    ocr_provider: str = os.getenv("OCR_PROVIDER", "disabled")
    ocr_local_engine: str = os.getenv("OCR_LOCAL_ENGINE", "paddleocr")
    ocr_lang: str = os.getenv("OCR_LANG", "ch")

    @property
    def sqlite_encryption_ready(self) -> bool:
        return bool(self.db_encryption_key)


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
