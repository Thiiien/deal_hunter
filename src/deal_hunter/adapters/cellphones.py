"""CellphoneS, a first-party retailer (ADR 0068).

Catalog sweep through the public GraphQL API; a single product through the page's JSON-LD.
Measured 04/11/2026: JSON-LD price == rendered price == API special_price (or price when special_price is 0).
"""
import json
import logging
import re

import httpx

from .base import BaseAdapter, FetchError, ProductDelisted
from ..models import Snapshot

log = logging.getLogger(__name__)

API_URL = "https://api.cellphones.com.vn/v2/graphql/query"
BASE_URL = "https://cellphones.com.vn/"
PAGE_SIZE = 200
USED_CATEGORY_ID = 29  # "Hàng cũ": excluded by decision, its prices move per unit
# top-level categories measured 04/11/2026; a query without a category is capped at 10,000 products
# "2" (Root) last: it catches products filed under no other top-level category, shown as "Khác"
DEFAULT_CATEGORIES = ("3", "380", "4", "30", "220", "610", "845", "663", "784", "705", "1123", "1676", "1532", "2")
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Content-Type": "application/json",
}
# shortcut: province_id / stock_available_id copied from the site's own query, so the sweep sees what a HCM visitor sees; revisit if stock looks wrong
_QUERY = (
    'query X{ products(filter:{static:{categories:["%s"],province_id:30,stock:{from:0},'
    'stock_available_id:[46,56,152,4164],filter_price:{from:0,to:500000000}},dynamic:{}},'
    'page:%d,size:%d,sort:[{view:desc}]){general{product_id name url_path categories{categoryId name}} '
    'filterable{price special_price}}}'
)
_LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def _jsonld_product(page_html: str) -> dict | None:
    for m in _LD_RE.finditer(page_html):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(data, list):
            nodes = data
        elif isinstance(data, dict):
            nodes = data.get("@graph", [data])
        else:
            nodes = []
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "Product":
                return node
    return None


class CellphonesAdapter(BaseAdapter):
    def __init__(self, client=None):
        self._client = client or httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True)

    # ── Catalog sweep ────────────────────────────────────────────────────────

    def iter_catalog(self, categories=DEFAULT_CATEGORIES):
        """Yield one Snapshot per new product; used goods and duplicates across categories are skipped."""
        seen: set = set()
        for cat in categories:
            page = 1
            while True:
                items = self._query(cat, page)
                for item in items:
                    snap = self._to_snapshot(cat, item, seen)
                    if snap:
                        yield snap
                if len(items) < PAGE_SIZE:
                    break
                page += 1

    def _query(self, cat: str, page: int) -> list:
        body = {"query": _QUERY % (cat, page, PAGE_SIZE), "variables": {}}
        r = self._client.post(API_URL, content=json.dumps(body))
        if r.status_code != 200:
            raise FetchError(f"CellphoneS API HTTP {r.status_code} (ngành {cat}, trang {page})")
        data = r.json().get("data") or {}
        return data.get("products") or []

    @staticmethod
    def _to_snapshot(cat: str, item: dict, seen: set) -> Snapshot | None:
        g = item.get("general") or {}
        f = item.get("filterable") or {}
        pid, url_path = g.get("product_id"), g.get("url_path")
        if pid is None or pid in seen or not url_path or url_path in seen:
            return None
        seen.update((pid, url_path))  # a few listings share one URL; the page shows one price, keep the first
        cats = g.get("categories") or []
        if any(c.get("categoryId") == USED_CATEGORY_ID or str(c.get("name") or "").strip().lower().endswith(" cũ") for c in cats):
            return None
        list_price = float(f.get("price") or 0) or None
        special = float(f.get("special_price") or 0)
        price = special if special > 0 else (list_price or 0.0)
        if price <= 0:
            return None
        url = BASE_URL + url_path
        return Snapshot(
            platform="cellphones",
            item_key=BaseAdapter.parse_item_key(url),
            url=url,
            name=str(g.get("name") or "").strip(),
            shop="CellphoneS",
            price=price,
            list_price=list_price,
            stock=True,  # the API only lists goods on sale; the page confirms before any alert is published
            category="Khác" if cat == "2" else next((str(c.get("name")) for c in cats if str(c.get("categoryId")) == str(cat)), ""),
        )

    # ── One product (tracked items and the 2-minute recheck) ────────────────

    def fetch(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
        r = self._client.get(url)
        if r.status_code == 404:
            raise ProductDelisted(f"CellphoneS 404: {url}")
        if r.status_code != 200:
            raise FetchError(f"CellphoneS HTTP {r.status_code}: {url}")
        product = _jsonld_product(r.text) or {}
        offers = product.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        try:
            price = float(str(offers.get("price") or offers.get("lowPrice") or 0).replace(",", ""))
        except ValueError:
            price = 0.0
        if price <= 0:
            raise FetchError(f"CellphoneS: không đọc được giá JSON-LD: {url}")
        availability = str(offers.get("availability") or "")
        return Snapshot(
            platform="cellphones",
            item_key=BaseAdapter.parse_item_key(url),
            url=url,
            name=str(product.get("name") or "").strip(),
            shop="CellphoneS",
            price=price,
            list_price=None,
            stock=("InStock" in availability) if availability else None,
            final_price=price,
        )
