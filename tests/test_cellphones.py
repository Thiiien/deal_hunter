"""ADR 0068: CellphoneS catalog sweep (first-party retailer, public API, no browser)."""
import json
import re
from dataclasses import replace

import pytest

from deal_hunter.adapters.base import BaseAdapter, ProductDelisted
from deal_hunter.adapters.cellphones import CellphonesAdapter
from deal_hunter.adapters.mock import MockAdapter
from deal_hunter.config import Config
from deal_hunter.db import DB
from deal_hunter.models import Snapshot
from deal_hunter.notifier import Notifier
from deal_hunter.quota import QuotaMonitor
from deal_hunter.scanner import Scanner
from deal_hunter.web import create_app


class _Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text

    def json(self):
        return self._data


class _FakeClient:
    """Answers the GraphQL query from a {(category, page): items} table and product pages from a string."""

    def __init__(self, pages, page_text="", page_status=200):
        self.pages, self.page_text, self.page_status = pages, page_text, page_status

    def post(self, url, content=None):
        q = json.loads(content)["query"]
        cat = re.search(r'categories:\["(\d+)"\]', q).group(1)
        page = int(re.search(r"page:(\d+)", q).group(1))
        return _Resp(200, {"data": {"products": self.pages.get((cat, page), [])}})

    def get(self, url):
        return _Resp(self.page_status, text=self.page_text)


def _item(pid, name, slug, price, special, cats):
    return {
        "general": {"product_id": pid, "name": name, "url_path": slug + ".html",
                    "categories": [{"categoryId": c, "name": n} for c, n in cats]},
        "filterable": {"price": price, "special_price": special},
    }


def _snap(price, item_key="laptop-a", list_price=25_000_000.0, name="Laptop A"):
    return Snapshot(platform="cellphones", item_key=item_key, url=f"https://cellphones.com.vn/{item_key}.html",
                    name=name, shop="CellphoneS", price=price, list_price=list_price, stock=True, category="Laptop")


def test_iter_catalog_skips_used_dedupes_and_maps_prices():
    pages = {
        ("3", 1): [
            _item(1, "iPhone 18 Pro 256GB", "iphone-18-pro", 38990000.0, 38690000.0, [(2, "Root"), (3, "Điện thoại")]),
            _item(2, "iPhone 15 cũ", "iphone-15-cu", 9000000.0, 0, [(29, "Hàng cũ"), (940, "Điện thoại cũ")]),
            _item(3, "Pin dự phòng", "pin", 900000, 0, [(3, "Điện thoại")]),
        ],
        ("30", 1): [_item(1, "iPhone 18 Pro 256GB", "iphone-18-pro", 38990000.0, 38690000.0, [(30, "Phụ kiện")])],
    }
    snaps = list(CellphonesAdapter(client=_FakeClient(pages)).iter_catalog(categories=("3", "30")))
    assert [s.item_key for s in snaps] == ["iphone-18-pro", "pin"]
    assert snaps[0].price == 38690000.0 and snaps[0].list_price == 38990000.0
    assert snaps[0].category == "Điện thoại" and snaps[0].url == "https://cellphones.com.vn/iphone-18-pro.html"
    assert snaps[1].price == 900000 and snaps[1].platform == "cellphones"


def test_fetch_reads_jsonld_and_404_is_delisted():
    page = ('<html><script type="application/ld+json">{"@type":"Product","name":"iPhone 18 Pro 256GB",'
            '"offers":{"@type":"Offer","price":"38690000","availability":"https://schema.org/InStock"}}</script></html>')
    snap = CellphonesAdapter(client=_FakeClient({}, page_text=page)).fetch("https://cellphones.com.vn/iphone-18-pro.html")
    assert snap.price == 38690000.0 and snap.stock is True and snap.item_key == "iphone-18-pro"
    with pytest.raises(ProductDelisted):
        CellphonesAdapter(client=_FakeClient({}, page_status=404)).fetch("https://cellphones.com.vn/x.html")


def test_parse_platform_and_item_key():
    url = "https://cellphones.com.vn/iphone-18-pro.html?utm=x"
    assert BaseAdapter.parse_platform(url) == "cellphones"
    assert BaseAdapter.parse_item_key(url) == "iphone-18-pro"
    # slugs with "-i5" / "-i7" must not fall into the Lazada "-i<id>" pattern
    assert BaseAdapter.parse_item_key("https://cellphones.com.vn/cpu-intel-core-i5-13600kf.html") == "cpu-intel-core-i5-13600kf"


def test_record_retail_sweep_writes_history_only_on_change(db):
    def rows():
        return db.conn.execute("SELECT COUNT(*) FROM retail_price_history").fetchone()[0]

    r1 = db.record_retail_sweep([_snap(20_000_000.0)])[0]
    assert r1["changed"] is True and r1["peak_before"] is None and rows() == 1
    r2 = db.record_retail_sweep([_snap(20_000_000.0)])[0]
    assert r2["changed"] is False and r2["peak_before"] == 20_000_000.0 and rows() == 1
    db.conn.execute("UPDATE retail_price_history SET ts = datetime('now','-2 days')")
    db.conn.commit()
    assert db.record_retail_sweep([_snap(20_000_000.0)])[0]["changed"] is False and rows() == 2  # daily row
    r4 = db.record_retail_sweep([_snap(6_000_000.0)])[0]
    assert r4["changed"] is True and r4["peak_before"] == 20_000_000.0 and rows() == 3
    deals = db.get_retail_deals(min_price=500000.0)
    assert deals[0]["item_key"] == "laptop-a" and deals[0]["peak_price"] == 20_000_000.0 and deals[0]["price"] == 6_000_000.0
    assert db.get_retail_deals(min_price=500000.0, category="Điện thoại") == []
    assert db.get_retail_categories() == ["Laptop"]


class _FakeRetail:
    def __init__(self, *snaps):
        self.snaps = snaps

    def iter_catalog(self):
        return iter(self.snaps)


def _scanner():
    config = Config(db_path=":memory:", fetch_mode="mock", request_delay_sec=0.0,
                    only_target_price_alerts=True, price_error_scan_enabled=False)
    db = DB(":memory:")
    notifier = Notifier(config)
    scanner = Scanner(config, MockAdapter(), db, notifier, QuotaMonitor(config, notifier))
    scanner._recheck_price_anomaly = lambda *a, **k: None  # no 2-minute sleep in tests
    return config, db, notifier, scanner


def test_sweep_routes_price_error_to_admin_flow_despite_tracked_alert_mode():
    config, db, notifier, scanner = _scanner()
    assert scanner._retail == {}  # mock mode never touches the network
    sent = []
    notifier.alert_admin = lambda text, reply_markup=None: sent.append(text) or 1

    scanner._retail["cellphones"] = _FakeRetail(
        _snap(20_000_000.0),
        _snap(300_000.0, item_key="cap", list_price=2_000_000.0, name="Cáp sạc"),
    )
    assert scanner.sweep_cellphones()["anomalies"] == 0  # 20% below list price; the cable is under the 500k floor
    scanner._retail["cellphones"] = _FakeRetail(_snap(5_000_000.0))  # 75% below the 7-day peak
    res = scanner.sweep_cellphones()
    assert res["anomalies"] == 1 and len(sent) == 1 and "[CELLPHONES]" in sent[0]
    anom = db.get_anomalies()[0]
    assert anom["platform"] == "cellphones" and anom["baseline"] == 20_000_000.0 and anom["stage"] == "confirming"
    assert scanner.sweep_cellphones()["anomalies"] == 0  # same price again: no change, no duplicate
    assert json.loads(db.get_setting("cellphones_last_sweep"))["count"] == 1
    # the marketplace gate still holds for Shopee/Lazada items
    scanner._handle_price_error(1, replace(_snap(1.0), platform="lazada"), 100000.0, 1000000.0, 0.9)
    assert len(sent) == 1


def test_settings_and_retail_api_and_track_button():
    config, db, notifier, scanner = _scanner()
    client = create_app(config, db, scanner).test_client()
    d = client.get("/api/settings").get_json()
    assert d["cellphones_scan_enabled"] is False and d["cellphones_interval_min"] == 15
    r = client.post("/api/settings", json={"cellphones_scan_enabled": True, "cellphones_interval_min": 5})
    assert r.status_code == 200 and db.get_setting("cellphones_scan_enabled") == "1" and db.get_setting("cellphones_interval_min") == "5"
    assert client.post("/api/settings", json={"cellphones_interval_min": 0}).status_code == 400

    db.record_retail_sweep([_snap(20_000_000.0), _snap(39_000.0, item_key="bao-da", list_price=890_000.0, name="Bao da Samsung Galaxy A34")])
    db.record_retail_sweep([_snap(12_000_000.0)])
    d = client.get("/api/retail-deals").get_json()
    assert len(d["items"]) == 1  # the case with an inflated list price is filtered as an accessory
    assert d["items"][0]["disc_peak_pct"] == 40 and d["items"][0]["disc_list_pct"] == 52
    assert d["items"][0]["affiliate_url"] == "https://cellphones.com.vn/laptop-a.html" and d["categories"] == ["Laptop"]

    r = client.post("/api/products", json={"url": "https://cellphones.com.vn/laptop-a.html"})
    assert r.status_code == 200 and r.get_json()["platform"] == "cellphones"
