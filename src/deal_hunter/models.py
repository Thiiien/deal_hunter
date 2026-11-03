from dataclasses import dataclass, field
from enum import Enum


class DealStatus(Enum):
    REAL_DEAL = "real_deal"
    FAKE_LIST_PRICE = "fake_list_price"
    INSUFFICIENT_HISTORY = "insufficient_history"
    NORMAL = "normal"


@dataclass
class VariantInfo:
    variant_key: str
    name: str
    price: float | None = None
    list_price: float | None = None
    stock_state: str = "unknown"  # "in", "out", "unknown"
    stock_qty: int | None = None
    stock_source: str = ""
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class Snapshot:
    """Normalized product data captured at one scan point."""
    platform: str
    item_key: str
    url: str
    name: str
    shop: str
    price: float
    list_price: float | None   # shop-published original price (may be inflated)
    stock: bool | None         # None = unknown
    rating: float | None = None
    sold: int | None = None
    category: str = ""
    voucher_code: str = ""
    voucher_discount: float = 0.0
    final_price: float | None = None
    origin: str = ""
    shop_country: str = ""
    ships_from: str = ""
    services: str = ""
    verified: int = 1
    variants: list[VariantInfo] = field(default_factory=list)
    sku_from_url: str = ""


@dataclass
class DetectionResult:
    """Output of detector.detect() for one product snapshot."""
    status: DealStatus
    disc_hist: float | None    # discount ratio vs 30-day median (0.30 = 30% off)
    disc_list: float | None    # discount ratio vs list_price
    median_30d: float | None
