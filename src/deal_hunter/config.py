import os
from dataclasses import dataclass


@dataclass
class Config:
    db_path: str = "data/deals.db"
    fetch_mode: str = "playwright"           # mock | feed | playwright
    deal_min_discount: float = 30.0          # percent (30 = 30%)
    deal_min_rating: float = 4.0
    deal_min_original_price: float = 500000.0 # filter junk items with pre-discount value < 500k
    scan_interval_min: int = 2
    request_delay_sec: float = 2.0
    nopecha_api_key: str = ""
    aff_shopee: str = "{raw}"
    aff_lazada: str = "{raw}"
    aff_tiktok: str = "{raw}"
    telegram_token: str = ""
    admin_chat_id: str = ""
    telegram_channel_id: str = ""
    web_host: str = "127.0.0.1"
    web_port: int = 5000
    extensions_dir: str = "extensions"
    keyword_include_unknown: bool = False
    keyword_result_limit: int = 30
    keyword_interval_min: int = 180
    megasale_interval_min: int = 60
    price_error_interval_min: int = 60
    tmall_interval_min: int = 120
    keyword_scan_enabled: bool = True
    megasale_scan_enabled: bool = False
    price_error_scan_enabled: bool = True
    tmall_scan_enabled: bool = True
    tmall_min_price: float = 100000.0
    tmall_max_price: float = 20000000.0
    only_target_price_alerts: bool = False
    cdp_url: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            db_path=os.getenv("DB_PATH", "data/deals.db"),
            fetch_mode=os.getenv("FETCH_MODE", "playwright"),
            deal_min_discount=float(os.getenv("DEAL_MIN_DISCOUNT", "30")),
            deal_min_rating=float(os.getenv("DEAL_MIN_RATING", "4.0")),
            deal_min_original_price=float(os.getenv("DEAL_MIN_ORIGINAL_PRICE", "500000")),
            scan_interval_min=int(os.getenv("SCAN_INTERVAL_MIN", "2")),
            request_delay_sec=float(os.getenv("REQUEST_DELAY_SEC", "2")),
            nopecha_api_key=os.getenv("NOPECHA_API_KEY", ""),
            aff_shopee=os.getenv("AFF_SHOPEE", "{raw}"),
            aff_lazada=os.getenv("AFF_LAZADA", "{raw}"),
            aff_tiktok=os.getenv("AFF_TIKTOK", "{raw}"),
            telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
            admin_chat_id=os.getenv("ADMIN_CHAT_ID", ""),
            telegram_channel_id=os.getenv("TELEGRAM_CHANNEL_ID", ""),
            web_host=os.getenv("WEB_HOST", "127.0.0.1"),
            web_port=int(os.getenv("WEB_PORT", "5000")),
            extensions_dir=os.getenv("EXTENSIONS_DIR", "extensions"),
            keyword_include_unknown=os.getenv("KEYWORD_INCLUDE_UNKNOWN", "0").lower() in ("1", "true", "yes"),
            keyword_result_limit=int(os.getenv("KEYWORD_RESULT_LIMIT", "30")),
            keyword_interval_min=int(os.getenv("KEYWORD_INTERVAL_MIN", "180")),
            megasale_interval_min=int(os.getenv("MEGASALE_INTERVAL_MIN", "60")),
            price_error_interval_min=int(os.getenv("PRICE_ERROR_INTERVAL_MIN", "60")),
            tmall_interval_min=int(os.getenv("TMALL_INTERVAL_MIN", "120")),
            keyword_scan_enabled=os.getenv("KEYWORD_SCAN_ENABLED", "1").lower() in ("1", "true", "yes"),
            megasale_scan_enabled=os.getenv("MEGASALE_SCAN_ENABLED", "0").lower() in ("1", "true", "yes"),
            price_error_scan_enabled=os.getenv("PRICE_ERROR_SCAN_ENABLED", "1").lower() in ("1", "true", "yes"),
            tmall_scan_enabled=os.getenv("TMALL_SCAN_ENABLED", "1").lower() in ("1", "true", "yes"),
            tmall_min_price=float(os.getenv("TMALL_MIN_PRICE", "100000")),
            tmall_max_price=float(os.getenv("TMALL_MAX_PRICE", "20000000")),
            only_target_price_alerts=os.getenv("ONLY_TARGET_PRICE_ALERTS", "1").lower() in ("1", "true", "yes"),
            cdp_url=os.getenv("CDP_URL", ""),
        )


