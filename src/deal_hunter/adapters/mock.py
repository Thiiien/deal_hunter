import random

from .base import BaseAdapter
from ..models import Snapshot

# Deterministic price sequences for testing the 30-day median detection logic.
# Keys match the item_keys parsed from the sample URLs used in tests.
_FIXED_PRICES: dict[str, list[float]] = {}


class MockAdapter(BaseAdapter):
    """Returns fake data without any network access.

    Use for:
    - Automated tests (deterministic mode via price_sequence)
    - Quick local demos when you don't have real credentials

    price_sequence: if provided, each call to fetch() pops the next price.
    Falls back to random prices when the sequence is exhausted.
    """

    def __init__(self, price_sequence: list[float] | None = None, rating: float = 4.8):
        self._seq = list(price_sequence) if price_sequence else []
        self._rating = rating

    def fetch(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
        platform = self.parse_platform(url)
        item_key = self.parse_item_key(url)
        price = self._seq.pop(0) if self._seq else round(random.uniform(50_000, 500_000), -3)
        list_price = round(price * random.uniform(1.2, 2.0), -3)
        return Snapshot(
            platform=platform,
            item_key=item_key,
            url=url,
            name=f"Mock Product [{item_key}]",
            shop="Mock Shop",
            price=price,
            list_price=list_price,
            stock=True,
            rating=None if is_tracked else self._rating,
            sold=random.randint(10, 1000),
        )

    def search(self, keyword: str, limit: int = 5, platform: str = "all", filters: dict | None = None) -> list[str]:
        slug = "".join(c for c in keyword.lower().replace(" ", "-") if c.isalnum() or c == "-") or "prod"
        shopee_urls = [f"https://shopee.vn/{slug}-i.{100 + i}.{200 + i}" for i in range(1, limit + 1)]
        lazada_urls = [f"https://www.lazada.vn/products/{slug}-i{300 + i}.html" for i in range(1, limit + 1)]
        if platform == "shopee":
            return shopee_urls[:limit]
        if platform == "lazada":
            return lazada_urls[:limit]
        interleaved = []
        for s, l in zip(shopee_urls, lazada_urls):
            interleaved.extend([s, l])
        return interleaved[:limit]

    def crawl_flash_sale(self, limit: int = 30, platform: str = "shopee") -> list[Snapshot]:
        platforms = ["shopee", "lazada"] if platform == "all" else [platform]
        res = []
        for p in platforms:
            for i in range(1, limit + 1):
                key = f"{p}_{1000 + i}"
                res.append(Snapshot(
                    platform=p,
                    item_key=key,
                    url=f"https://www.{p}.vn/p-{key}",
                    name=f"Flash Sale [{p.title()}] Deal {i}",
                    shop=f"Top {p.title()} Shop",
                    price=100000.0,
                    list_price=160000.0,
                    stock=True,
                    rating=4.9,
                    sold=500 + i * 10,
                    category="Thiết Bị Điện Tử",
                ))
        return res

    def crawl_tmall_subsidy(self, limit: int = 30, min_price: float = 0.0, max_price: float = float("inf")) -> list[Snapshot]:
        samples = [
            ("Tai nghe Bluetooth Không dây chống ồn TWS", "Phụ Kiện Điện Tử", 350000.0, 700000.0),
            ("Củ sạc nhanh GaN 65W Type-C 3 cổng PD", "Phụ Kiện Điện Tử", 280000.0, 560000.0),
            ("Chuột không dây công thái học Bluetooth/Wireless", "Phụ Kiện Điện Tử", 220000.0, 450000.0),
            ("Bàn phím cơ không dây RGB Hot-swap", "Phụ Kiện Điện Tử", 650000.0, 1200000.0),
            ("Pin sạc dự phòng 20000mAh 22.5W sạc nhanh", "Phụ Kiện Điện Tử", 320000.0, 600000.0),
            ("Điện thoại thông minh Redmi Note 13 8GB/128GB", "Thiết Bị Điện Tử", 3990000.0, 4890000.0),
            ("Màn hình máy tính 24 inch IPS 100Hz viền mỏng", "Thiết Bị Điện Tử", 1850000.0, 2600000.0),
            ("Loa Bluetooth di động công suất lớn chống nước", "Thiết Bị Điện Tử", 520000.0, 950000.0),
            ("Đồng hồ thông minh Smartwatch theo dõi sức khỏe", "Thiết Bị Điện Tử", 790000.0, 1500000.0),
            ("Máy chiếu mini HD hỗ trợ 4K kết nối WiFi", "Thiết Bị Điện Tử", 1450000.0, 2500000.0),
        ]
        res = []
        i = 1
        while len(res) < limit and i <= limit * 3:
            name, cat, p, lp = samples[(i - 1) % len(samples)]
            i += 1
            if not (min_price <= p <= max_price):
                continue
            key = f"tmall_{2000 + i}"
            res.append(Snapshot(
                platform="lazada",
                item_key=key,
                url=f"https://www.lazada.vn/products/tmall-deal-{key}.html",
                name=f"[TMALL TRỢ GIÁ] {name} #{i}",
                shop="LazMall Tmall",
                price=p,
                list_price=lp,
                stock=True,
                rating=None,
                sold=200 + i * 5,
                category=cat,
            ))
        return res

