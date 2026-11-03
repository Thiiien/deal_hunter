import csv
import json
from pathlib import Path

from .base import BaseAdapter, FetchError
from ..models import Snapshot


class FeedAdapter(BaseAdapter):
    """Reads product data from a CSV or JSON affiliate feed file.

    Expected CSV columns: url, name, shop, price, list_price, stock, rating, sold
    Expected JSON: array of objects with the same keys.

    Call discover() to get all URLs in the feed for auto-registration.
    """

    def __init__(self, feed_path: str = "data/feed.csv"):
        self._path = Path(feed_path)
        self._cache: dict[str, dict] = {}
        self._load()

    def _load(self):
        if not self._path.exists():
            return
        if self._path.suffix.lower() == ".json":
            items = json.loads(self._path.read_text(encoding="utf-8"))
            self._cache = {item["url"]: item for item in items if "url" in item}
        else:
            with self._path.open(encoding="utf-8") as f:
                self._cache = {row["url"]: row for row in csv.DictReader(f) if "url" in row}

    def fetch(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
        data = self._cache.get(url)
        if data is None:
            raise FetchError(f"URL not in feed: {url}")
        try:
            return Snapshot(
                platform=self.parse_platform(url),
                item_key=self.parse_item_key(url),
                url=url,
                name=data.get("name", ""),
                shop=data.get("shop", ""),
                price=float(data["price"]),
                list_price=float(data["list_price"]) if data.get("list_price") else None,
                stock=_parse_stock(data.get("stock")),
                rating=None if is_tracked else (float(data["rating"]) if data.get("rating") else None),
                sold=int(data["sold"]) if data.get("sold") else None,
            )
        except (KeyError, ValueError) as exc:
            raise FetchError(f"Bad feed data for {url}: {exc}") from exc

    def discover(self) -> list[str]:
        """Return all product URLs in the feed (for auto-registration on startup)."""
        return list(self._cache.keys())

    def search(self, keyword: str, limit: int = 5) -> list[str]:
        kw = keyword.lower()
        matched = []
        for url, data in self._cache.items():
            name = (data.get("name") or "").lower()
            if kw in name or kw in url.lower():
                matched.append(url)
                if len(matched) >= limit:
                    break
        return matched


def _parse_stock(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() not in ("0", "false", "out", "hết hàng")
