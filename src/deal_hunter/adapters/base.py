import hashlib
import re
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from ..models import Snapshot


class Blocked(Exception):
    """Platform detected automation and blocked the entire session.

    Caller (scanner) should stop scanning this platform for the rest of
    the current cycle and alert the admin.
    """


class FetchError(Exception):
    """Transient error for a single product.

    Caller (scanner) should log and skip this product, then continue.
    """


class ProductDelisted(FetchError):
    """Product was removed, deleted, or page returned 404."""


class BaseAdapter(ABC):
    """Contract for all data sources.

    To add a new platform: subclass BaseAdapter, implement fetch(), and
    register it in get_adapter() in scanner.py. Nothing else changes.
    """

    @abstractmethod
    def fetch(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
        """Fetch the current product state from url.

        Returns:
            Snapshot with current price, stock, rating, etc.
        Raises:
            Blocked:    stop scanning this platform this cycle
            FetchError: skip this product, continue with next
        """

    def fast_fetch(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot | None:
        """Lightweight / API-based fast fetch. Returns None if fallback to full fetch() is needed."""
        return None

    def search(self, keyword: str, limit: int = 5, platform: str = "all", filters: dict | None = None) -> list[str]:
        """Search products by keyword and return a list of product URLs."""
        return []

    def crawl_tmall_subsidy(self, limit: int = 30, min_price: float = 0.0, max_price: float = float("inf")) -> list[Snapshot]:
        """Crawl products from Lazada TMALL Subsidy catalog."""
        return []

    def ensure_authenticated(self, platform: str = "all") -> bool:
        """Verify session/authentication. Returns True if ready to scan."""
        return True



    # ── Shared URL parsing utilities ──────────────────────────────────────

    @staticmethod
    def parse_platform(url: str) -> str:
        if "shopee" in url:
            return "shopee"
        if "lazada" in url:
            return "lazada"
        if "tiktok" in url:
            return "tiktok"
        return "unknown"

    @staticmethod
    def parse_item_key(url: str) -> str:
        """Extract a stable, platform-scoped product identifier from a URL."""
        # Shopee: /product/<shopid>/<itemid>
        m = re.search(r"/product/(\d+)/(\d+)", url)
        if m:
            return f"{m.group(1)}.{m.group(2)}"
        # Shopee: product-name-i.<shopid>.<itemid>
        m = re.search(r"-i\.(\d+)\.(\d+)", url)
        if m:
            return f"{m.group(1)}.{m.group(2)}"
        # Lazada: -i<itemid>-s<shopid>.html or -i<itemid>.html
        m = re.search(r"-i(\d+)(?:-s(\d+))?", url)
        if m:
            return f"{m.group(1)}.{m.group(2)}" if m.group(2) else m.group(1)
        # TikTok Shop: /product/<id>
        m = re.search(r"/product/(\w+)", url)
        if m:
            return m.group(1)
        # Fallback: stable hash of host + path
        p = urlparse(url)
        return hashlib.md5(f"{p.netloc}{p.path}".encode()).hexdigest()[:16]

