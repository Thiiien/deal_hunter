import time
import pytest
from deal_hunter.config import Config
from deal_hunter.db import DB
from deal_hunter.models import Snapshot
from deal_hunter.scanner import Scanner
from deal_hunter.adapters.mock import MockAdapter
from deal_hunter.notifier import Notifier
from deal_hunter.quota import QuotaMonitor
from deal_hunter.web import create_app


def test_product_source_isolation(tmp_path):
    db_file = tmp_path / "test_iso.db"
    db = DB(str(db_file))

    # 1. User explicitly tracks product A
    snap_a = Snapshot(
        platform="shopee",
        item_key="item_user_1",
        url="https://shopee.vn/product-user-1",
        name="User Tracked Item",
        shop="Shop A",
        price=100000.0,
        list_price=120000.0,
        stock=True,
    )
    pid_a = db.add_product_url(snap_a.url, snap_a.platform, snap_a.item_key, source="user")
    db.upsert_product_meta(snap_a, source="user")

    # 2. Crawler discovers product B via keyword
    snap_b = Snapshot(
        platform="shopee",
        item_key="item_kw_1",
        url="https://shopee.vn/product-kw-1",
        name="Keyword Discovered Item",
        shop="Shop B",
        price=150000.0,
        list_price=200000.0,
        stock=True,
    )
    pid_b = db.upsert_product_meta(snap_b, source="keyword")

    # 3. Crawler discovers product C via flash sale
    snap_c = Snapshot(
        platform="shopee",
        item_key="item_fs_1",
        url="https://shopee.vn/product-fs-1",
        name="Flash Sale Item",
        shop="Shop C",
        price=200000.0,
        list_price=300000.0,
        stock=True,
    )
    pid_c = db.add_product_url(snap_c.url, snap_c.platform, snap_c.item_key, source="flash_sale")
    db.upsert_product_meta(snap_c, source="flash_sale")

    # Verify sources in DB
    row_a = db.get_product(pid_a)
    row_b = db.get_product(pid_b)
    row_c = db.get_product(pid_c)
    assert row_a["source"] == "user"
    assert row_b["source"] == "keyword"
    assert row_c["source"] == "flash_sale"

    # Verify get_active_tracked_products ONLY returns user products
    tracked = db.get_active_tracked_products()
    tracked_ids = [p["id"] for p in tracked]
    assert pid_a in tracked_ids
    assert pid_b not in tracked_ids
    assert pid_c not in tracked_ids

    # 4. If keyword search hits product A, user source MUST NOT be overwritten
    db.upsert_product_meta(snap_a, source="keyword")
    assert db.get_product(pid_a)["source"] == "user"

    # 5. If user later explicitly adds product B, source upgrades to 'user'
    db.add_product_url(snap_b.url, snap_b.platform, snap_b.item_key, source="user")
    assert db.get_product(pid_b)["source"] == "user"
    assert pid_b in [p["id"] for p in db.get_active_tracked_products()]


def test_independent_intervals_settings_api(tmp_path):
    db_file = tmp_path / "test_api.db"
    db = DB(str(db_file))
    config = Config.from_env()
    adapter = MockAdapter()
    notifier = Notifier(config)
    quota = QuotaMonitor(config, notifier)
    scanner = Scanner(config, adapter, db, notifier, quota)
    app = create_app(config, db, scanner)
    client = app.test_client()

    # GET default settings
    r = client.get("/api/settings")
    assert r.status_code == 200
    d = r.get_json()
    assert "scan_interval_min" in d
    assert "keyword_interval_min" in d
    assert "megasale_interval_min" in d
    assert "price_error_interval_min" in d
    assert d["keyword_scan_enabled"] is False
    assert d["megasale_scan_enabled"] is False
    assert d["price_error_scan_enabled"] is False

    # POST new values for all 4 intervals and toggle flags
    payload = {
        "scan_interval_min": 25,
        "keyword_interval_min": 120,
        "megasale_interval_min": 45,
        "price_error_interval_min": 30,
        "deal_min_original_price": 600000.0,
        "keyword_include_unknown": True,
        "keyword_scan_enabled": False,
        "megasale_scan_enabled": False,
        "price_error_scan_enabled": True,
    }
    r = client.post("/api/settings", json=payload)
    assert r.status_code == 200
    res = r.get_json()
    assert res["status"] == "ok"
    assert res["scan_interval_min"] == 25
    assert res["keyword_interval_min"] == 120
    assert res["megasale_interval_min"] == 45
    assert res["price_error_interval_min"] == 30
    assert res["keyword_scan_enabled"] is False
    assert res["megasale_scan_enabled"] is False
    assert res["price_error_scan_enabled"] is True

    # Verify persisted in DB
    assert db.get_setting("scan_interval_min") == "25"
    assert db.get_setting("keyword_interval_min") == "120"
    assert db.get_setting("megasale_interval_min") == "45"
    assert db.get_setting("price_error_interval_min") == "30"
    assert db.get_setting("deal_min_original_price") == "600000.0"
    assert db.get_setting("keyword_scan_enabled") == "0"
    assert db.get_setting("megasale_scan_enabled") == "0"
    assert db.get_setting("price_error_scan_enabled") == "1"

    # Summary API reflects the intervals
    r_sum = client.get("/api/summary")
    assert r_sum.status_code == 200
    sum_data = r_sum.get_json()
    assert sum_data["scan_interval_min"] == 25
    assert sum_data["keyword_interval_min"] == 120
    assert sum_data["megasale_interval_min"] == 45
    assert sum_data["price_error_interval_min"] == 30


def test_scanner_scan_due(tmp_path):
    db_file = tmp_path / "test_due.db"
    db = DB(str(db_file))
    config = Config.from_env()
    config.scan_interval_min = 10
    config.keyword_interval_min = 30
    config.megasale_interval_min = 60
    config.price_error_interval_min = 60
    config.megasale_scan_enabled = True
    config.keyword_scan_enabled = True
    config.price_error_scan_enabled = True
    config.tmall_scan_enabled = True

    adapter = MockAdapter()
    notifier = Notifier(config)
    quota = QuotaMonitor(config, notifier)
    scanner = Scanner(config, adapter, db, notifier, quota)

    # Initial scan_due: all 4 are due because timestamps are 0.0
    results = scanner.scan_due()
    assert "tracked" in results
    assert "keyword" in results
    assert "megasale" in results
    assert "price_error" in results

    # Immediately calling scan_due again: none should be due
    results_2 = scanner.scan_due()
    assert results_2 == {}

    # Test disabling subsystems
    scanner._last_keyword_scan_time = 0.0
    scanner._last_megasale_scan_time = 0.0
    scanner._last_price_error_scan_time = 0.0
    scanner._last_tracked_scan_time = time.time() # not due

    config.keyword_scan_enabled = False
    config.megasale_scan_enabled = False
    config.price_error_scan_enabled = True

    results_3 = scanner.scan_due()
    assert "keyword" not in results_3
    assert "megasale" not in results_3
    assert "price_error" in results_3



def test_consecutive_failures_auto_deactivate_and_alert(tmp_path):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.base import FetchError

    db_file = tmp_path / "test_fails.db"
    db = DB(str(db_file))
    config = Config.from_env()

    # Create mock adapter that raises FetchError on fetch
    adapter = MockAdapter()
    adapter.fetch = MagicMock(side_effect=FetchError("Network timeout"))

    notifier = MagicMock(spec=Notifier)
    quota = MagicMock(spec=QuotaMonitor)
    quota.is_exhausted = False
    quota.check.return_value = 50

    scanner = Scanner(config, adapter, db, notifier, quota)

    # Add a user-tracked product
    pid = db.add_product_url("https://shopee.vn/p-fail-1", "shopee", "item_fail_1", source="user")
    assert db.get_product(pid)["active"] == 1
    assert db.get_product(pid)["fail_count"] == 0

    # Run tracked products scan 4 times
    for i in range(1, 5):
        scanner.scan_tracked_products()
        prod = db.get_product(pid)
        assert prod["active"] == 1
        assert prod["fail_count"] == i
        notifier.alert_admin.assert_not_called()

    # 5th scan: user product stays active=1 to protect user data, but alerts admin
    scanner.scan_tracked_products()
    prod = db.get_product(pid)
    assert prod["active"] == 1
    assert prod["fail_count"] == 5
    notifier.alert_admin.assert_called_once()
    alert_text = notifier.alert_admin.call_args[0][0]
    assert "Sản phẩm theo dõi gặp lỗi quét liên tiếp" in alert_text
    assert "item_fail_1" in alert_text or "p-fail-1" in alert_text

    # Test discovery product (e.g. flash_sale): auto-deactivates to active=0 after 5 failures
    pid_fs = db.add_product_url("https://shopee.vn/p-fail-fs", "shopee", "item_fail_fs", source="flash_sale")
    for _ in range(5):
        scanner._scan_platform("shopee", [db.get_product(pid_fs)])
    prod_fs = db.get_product(pid_fs)
    assert prod_fs["active"] == 0
    assert prod_fs["fail_count"] == 5


def test_lazada_tracked_products_fail_count_does_not_deactivate(tmp_path):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.base import FetchError

    db_file = tmp_path / "test_lzd_fails.db"
    db = DB(str(db_file))
    config = Config.from_env()
    notifier = MagicMock(spec=Notifier)
    quota = MagicMock(spec=QuotaMonitor)
    quota.is_exhausted = False
    quota.check.return_value = 50

    adapter = MockAdapter()
    adapter.fetch = MagicMock(side_effect=FetchError("Lazada MTOP challenge or slider captcha"))

    scanner = Scanner(config, adapter, db, notifier, quota)

    # User adds a Lazada product
    pid = db.add_product_url(
        "https://www.lazada.vn/products/aula-s75-pro-i13347642637.html",
        "lazada",
        "13347642637",
        source="user"
    )
    assert db.get_product(pid)["active"] == 1
    assert db.get_product(pid)["fail_count"] == 0

    # Scan fails 6 consecutive times on Lazada
    for _ in range(6):
        scanner.scan_tracked_products()

    # User product MUST remain active=1 and NEVER auto-deactivate to active=0
    prod = db.get_product(pid)
    assert prod["active"] == 1
    assert prod["fail_count"] == 6
    assert pid in [p["id"] for p in db.get_active_tracked_products()]


def test_success_resets_fail_count(tmp_path):
    from unittest.mock import MagicMock

    db_file = tmp_path / "test_success.db"
    db = DB(str(db_file))
    config = Config.from_env()

    adapter = MockAdapter(price_sequence=[100000.0])
    notifier = MagicMock(spec=Notifier)
    quota = MagicMock(spec=QuotaMonitor)
    quota.is_exhausted = False
    quota.check.return_value = 50

    scanner = Scanner(config, adapter, db, notifier, quota)

    pid = db.add_product_url("https://shopee.vn/p-good-1", "shopee", "item_good_1", source="user")

    # Simulate some prior failures
    db.increment_product_fail_count(pid)
    db.increment_product_fail_count(pid)
    assert db.get_product(pid)["fail_count"] == 2

    # Successful scan resets fail_count to 0
    res = scanner.scan_tracked_products()
    assert res["ok"] == 1
    assert db.get_product(pid)["fail_count"] == 0


def test_dynamic_fallback_reevaluation(tmp_path):
    """Verify fallback engine dynamically updates to cheaper candidate when discovered."""
    from deal_hunter.models import VariantInfo

    db_file = tmp_path / "test_fallback_dyn.db"
    db = DB(str(db_file))

    # Product with 3 variants:
    # Baseline: Pro Đen (772,000₫ baseline, initially in stock)
    # Var 1: Xingyu Cam (880,000₫, in stock)
    # Var 2: Pro Trắng (originally 1,005,000₫, exceeds 20% ceiling = 926,400₫)
    pid = db.add_product_url("https://www.lazada.vn/products/i12345.html", "lazada", "12345", source="user")
    
    snap0 = Snapshot(
        platform="lazada",
        item_key="12345",
        url="https://www.lazada.vn/products/i12345.html",
        name="ATK Gear Tai Nghe",
        shop="ATK Official",
        price=772000.0,
        list_price=1000000.0,
        stock=True,
        variants=[
            VariantInfo(variant_key="var_black", name="ATK N9 Pro Đen", price=772000.0, stock_state="in"),
            VariantInfo(variant_key="var_orange", name="ATK N9 Xingyu Cam", price=880000.0, stock_state="in"),
            VariantInfo(variant_key="var_white", name="ATK N9 Pro Trắng", price=1005000.0, stock_state="in"),
        ],
    )
    db.update_product_from_snapshot(pid, snap0)
    db.save_snapshot(pid, snap0)

    # Main variant is var_black (lowest initial in-stock)
    main_v = db.conn.execute("SELECT id FROM variants WHERE product_id=? AND variant_key='var_black'", (pid,)).fetchone()
    db.set_main_variant(pid, main_v["id"])

    # Now Pro Đen goes out of stock
    snap1 = Snapshot(
        platform="lazada",
        item_key="12345",
        url="https://www.lazada.vn/products/i12345.html",
        name="ATK Gear Tai Nghe",
        shop="ATK Official",
        price=772000.0,
        list_price=1000000.0,
        stock=False,
        variants=[
            VariantInfo(variant_key="var_black", name="ATK N9 Pro Đen", price=772000.0, stock_state="out"),
            VariantInfo(variant_key="var_orange", name="ATK N9 Xingyu Cam", price=880000.0, stock_state="in"),
            VariantInfo(variant_key="var_white", name="ATK N9 Pro Trắng", price=1005000.0, stock_state="in"),
        ],
    )
    db.update_product_from_snapshot(pid, snap1)
    db.save_snapshot(pid, snap1)

    # 1st scan: suspect_out
    res1 = db.evaluate_variant_state(pid)
    assert res1["action"] == "suspect_out"

    # 2nd scan: confirmed out -> picks Xingyu Cam (880k) because Pro Trắng was 1.005k > ceiling 926.4k
    res2 = db.evaluate_variant_state(pid)
    assert res2["action"] == "fallback_applied"
    assert res2["price"] == 880000.0
    assert "Xingyu Cam" in res2["chosen_variant_name"]

    # Now Flash Sale / On-demand probe discovers Pro Trắng is actually 540,700₫!
    snap2 = Snapshot(
        platform="lazada",
        item_key="12345",
        url="https://www.lazada.vn/products/i12345.html",
        name="ATK Gear Tai Nghe",
        shop="ATK Official",
        price=540700.0,
        list_price=1005000.0,
        stock=True,
        variants=[
            VariantInfo(variant_key="var_black", name="ATK N9 Pro Đen", price=772000.0, stock_state="out"),
            VariantInfo(variant_key="var_orange", name="ATK N9 Xingyu Cam", price=880000.0, stock_state="in"),
            VariantInfo(variant_key="var_white", name="ATK N9 Pro Trắng", price=540700.0, stock_state="in", stock_source="lazada_dom_swatch"),
        ],
    )
    db.update_product_from_snapshot(pid, snap2)
    db.save_snapshot(pid, snap2)

    # 3rd scan: dynamic re-evaluation selects Pro Trắng (540,700₫) instead of staying locked on 880,000₫
    res3 = db.evaluate_variant_state(pid)
    assert res3["action"] == "fallback_applied"
    assert res3["price"] == 540700.0
    assert "Pro Trắng" in res3["chosen_variant_name"]

    # Verify price_history was synced with stock=1
    latest_ph = db.conn.execute("SELECT price, stock FROM price_history WHERE product_id=? ORDER BY ts DESC LIMIT 1", (pid,)).fetchone()
    assert latest_ph["price"] == 540700.0
    assert latest_ph["stock"] == 1


def test_on_demand_swatch_probing_only_when_out_of_stock():
    """Verify swatches are only clicked when out of stock; zero-click when in-stock."""
    from unittest.mock import MagicMock
    from deal_hunter.adapters.playwright import PlaywrightAdapter

    config = Config.from_env()
    adapter = PlaywrightAdapter(config)

    # Case 1: IN-STOCK -> Zero clicks on swatches
    page_in = MagicMock()
    page_in.url = "https://www.lazada.vn/products/test-in-stock-i100.html"
    page_in.locator.return_value.all_inner_texts.return_value = []
    page_in.locator.return_value.count.return_value = 1
    page_in.locator.return_value.first.inner_text.return_value = "500.000 ₫"
    clicked_swatches_in = []

    def eval_in(code, *args):
        if "next-btn-buy" in code:
            return False  # IN STOCK!
        if "elements[idx].click()" in code:
            clicked_swatches_in.append(args[0])
            return None
        return None

    page_in.evaluate.side_effect = eval_in
    snap_in = adapter._parse_lazada(page_in, "https://www.lazada.vn/products/test-in-stock-i100.html")
    assert snap_in.stock is True
    assert snap_in.price == 500000.0
    assert len(clicked_swatches_in) == 0  # Zero clicks!

    # Case 2: OUT-OF-STOCK -> Swatch probing triggers
    page_out = MagicMock()
    page_out.url = "https://www.lazada.vn/products/test-out-of-stock-i200.html"
    page_out.locator.return_value.all_inner_texts.return_value = []
    page_out.locator.return_value.count.return_value = 0
    clicked_swatches_out = []

    def eval_out(code, *args):
        if "let price = null" in code:
            # Swatch probe evaluation
            return {"price": 540700.0, "listPrice": 1005000.0, "inStock": True}
        if "next-btn-buy" in code:
            return True  # OUT OF STOCK!
        if "const list = [];" in code and "elements.forEach" in code:
            return [
                {"index": 0, "name": "Màu Đen", "isSelected": True, "isDisabled": False},
                {"index": 1, "name": "Màu Trắng", "isSelected": False, "isDisabled": False},
            ]
        if "elements[idx].click()" in code:
            clicked_swatches_out.append(args[0])
            return None
        if "next-dialog-close" in code:
            return None
        return None

    page_out.evaluate.side_effect = eval_out
    snap_out = adapter._parse_lazada(page_out, "https://www.lazada.vn/products/test-out-of-stock-i200.html")
    assert snap_out.stock is True
    assert snap_out.price == 540700.0
    assert 1 in clicked_swatches_out  # Swatch 1 was clicked because initial was out of stock


def test_is_tmall_electronics_filter():
    from deal_hunter.classifier import is_tmall_electronics

    # Positive: Electronics
    ok, cat = is_tmall_electronics("Điện thoại thông minh Xiaomi Redmi Note 13 8GB/128GB")
    assert ok is True and cat == "Thiết Bị Điện Tử"

    ok, cat = is_tmall_electronics("Màn hình máy tính 24 inch IPS 100Hz viền mỏng")
    assert ok is True and cat == "Thiết Bị Điện Tử"

    # Positive: Accessories
    ok, cat = is_tmall_electronics("Củ sạc nhanh GaN 65W Type-C 3 cổng PD chính hãng")
    assert ok is True and cat == "Phụ Kiện Điện Tử"

    ok, cat = is_tmall_electronics("Tai nghe Bluetooth Không dây chống ồn TWS")
    assert ok is True and cat == "Phụ Kiện Điện Tử"

    ok, cat = is_tmall_electronics("Bàn phím cơ không dây RGB Hot-swap")
    assert ok is True and cat == "Phụ Kiện Điện Tử"

    # Negative: Cosmetics, fashion, food, gift cards
    assert is_tmall_electronics("Son môi lì kem mịn môi kháng nước")[0] is False
    assert is_tmall_electronics("Kem dưỡng ẩm chống lão hóa da ban đêm")[0] is False
    assert is_tmall_electronics("Váy hoa nhí dáng xòe thời trang nữ")[0] is False
    assert is_tmall_electronics("Áo sơ mi nam công sở cotton")[0] is False
    assert is_tmall_electronics("Thẻ quà tặng mã nạp 50k Lazada")[0] is False
    assert is_tmall_electronics("Khăn tắm chà lưng cotton mềm mịn")[0] is False


def test_mock_adapter_crawl_tmall_subsidy():
    adapter = MockAdapter()
    snaps = adapter.crawl_tmall_subsidy(limit=5, min_price=300000.0, max_price=1000000.0)
    assert len(snaps) > 0
    for s in snaps:
        assert s.platform == "lazada"
        assert s.rating is None
        assert s.stock is True
        assert "[TMALL TRỢ GIÁ]" in s.name
        assert s.category in ("Thiết Bị Điện Tử", "Phụ Kiện Điện Tử")
        assert 300000.0 <= s.price <= 1000000.0


def test_scanner_tmall_subsidy_discovery_and_isolation(tmp_path):
    db_file = tmp_path / "test_tmall.db"
    db = DB(str(db_file))
    cfg = Config(
        tmall_scan_enabled=True,
        tmall_interval_min=120,
        tmall_min_price=250000.0,
        tmall_max_price=2000000.0
    )
    adapter = MockAdapter()
    notifier = Notifier(cfg)
    quota = QuotaMonitor(cfg, notifier)
    scanner = Scanner(cfg, adapter, db, notifier, quota)

    discovered = scanner.discover_tmall_subsidy(limit=3)
    assert len(discovered) == 3

    # Check products in DB have source='lazada_tmall' and valid electronics category
    all_prods = db.get_active_products()
    assert len(all_prods) == 3
    for p in all_prods:
        assert p["source"] == "lazada_tmall"
        assert p["category"] in ("Thiết Bị Điện Tử", "Phụ Kiện Điện Tử")

    # Test scan_due respects tmall_scan_enabled
    scanner._last_tmall_scan_time = 0.0
    scanner._last_tracked_scan_time = time.time()
    scanner._last_keyword_scan_time = time.time()
    scanner._last_megasale_scan_time = time.time()
    scanner._last_price_error_scan_time = time.time()

    cfg.tmall_scan_enabled = False
    due_res = scanner.scan_due()
    assert "tmall" not in due_res

    cfg.tmall_scan_enabled = True
    due_res_2 = scanner.scan_due()
    assert "tmall" in due_res_2


def test_tmall_api_endpoints(tmp_path):
    db_file = tmp_path / "test_tmall_api.db"
    db = DB(str(db_file))
    cfg = Config(
        tmall_scan_enabled=True,
        tmall_interval_min=120,
        tmall_min_price=100000.0,
        tmall_max_price=20000000.0
    )
    adapter = MockAdapter()
    notifier = Notifier(cfg)
    quota = QuotaMonitor(cfg, notifier)
    scanner = Scanner(cfg, adapter, db, notifier, quota)
    app = create_app(cfg, db, scanner)
    client = app.test_client()

    # 1. Summary includes tmall settings and price range
    res = client.get("/api/summary")
    assert res.status_code == 200
    data = res.get_json()
    assert data["tmall_scan_enabled"] is True
    assert data["tmall_interval_min"] == 120
    assert data["tmall_min_price"] == 100000.0
    assert data["tmall_max_price"] == 20000000.0

    # 2. Get and update settings including price range
    res = client.get("/api/settings")
    assert res.status_code == 200
    assert res.get_json()["tmall_scan_enabled"] is True
    assert res.get_json()["tmall_min_price"] == 100000.0

    res = client.post("/api/settings", json={
        "tmall_scan_enabled": False,
        "tmall_interval_min": 60,
        "tmall_min_price": 200000.0,
        "tmall_max_price": 15000000.0,
    })
    assert res.status_code == 200
    assert cfg.tmall_scan_enabled is False
    assert cfg.tmall_interval_min == 60
    assert cfg.tmall_min_price == 200000.0
    assert cfg.tmall_max_price == 15000000.0

    # 3. Trigger on-demand crawl-tmall
    res = client.post("/api/crawl-tmall")
    assert res.status_code == 200
    assert res.get_json()["status"] == "started"


def test_tmall_real_time_filtering_and_immediate_cleanup(tmp_path):
    db_file = tmp_path / "test_tmall_filter.db"
    db = DB(str(db_file))
    cfg = Config(
        tmall_scan_enabled=True,
        tmall_interval_min=120,
        tmall_min_price=100000.0,
        tmall_max_price=20000000.0
    )
    adapter = MockAdapter()
    notifier = Notifier(cfg)
    quota = QuotaMonitor(cfg, notifier)
    scanner = Scanner(cfg, adapter, db, notifier, quota)
    app = create_app(cfg, db, scanner)
    client = app.test_client()

    # Product 1: valid (500k, Phụ Kiện Điện Tử)
    s1 = Snapshot(platform="lazada", item_key="tmall_valid", url="https://lazada.vn/p1.html", name="Tai nghe", shop="TMALL", price=500000.0, list_price=600000.0, stock=True, category="Phụ Kiện Điện Tử")
    pid1 = db.add_product_url(s1.url, s1.platform, s1.item_key, source="lazada_tmall")
    db.upsert_product_meta(s1, source="lazada_tmall")
    db.save_snapshot(pid1, s1)

    # Product 2: price over max (35 triệu)
    s2 = Snapshot(platform="lazada", item_key="tmall_expensive", url="https://lazada.vn/p2.html", name="iPhone 18", shop="TMALL", price=35000000.0, list_price=36000000.0, stock=True, category="Thiết Bị Điện Tử")
    pid2 = db.add_product_url(s2.url, s2.platform, s2.item_key, source="lazada_tmall")
    db.upsert_product_meta(s2, source="lazada_tmall")
    db.save_snapshot(pid2, s2)

    # Product 3: price under min (50k)
    s3 = Snapshot(platform="lazada", item_key="tmall_cheap", url="https://lazada.vn/p3.html", name="Dây chun", shop="TMALL", price=50000.0, list_price=60000.0, stock=True, category="Phụ Kiện Điện Tử")
    pid3 = db.add_product_url(s3.url, s3.platform, s3.item_key, source="lazada_tmall")
    db.upsert_product_meta(s3, source="lazada_tmall")
    db.save_snapshot(pid3, s3)

    # Product 4: wrong category (Son môi - Đời Sống & Tiêu Dùng)
    s4 = Snapshot(platform="lazada", item_key="tmall_cosmetic", url="https://lazada.vn/p4.html", name="Son môi", shop="TMALL", price=300000.0, list_price=400000.0, stock=True, category="Đời Sống & Tiêu Dùng")
    pid4 = db.add_product_url(s4.url, s4.platform, s4.item_key, source="lazada_tmall")
    db.upsert_product_meta(s4, source="lazada_tmall")
    db.save_snapshot(pid4, s4)

    # 1. API /api/products MUST only return valid product #1 in real-time
    res = client.get("/api/products")
    assert res.status_code == 200
    prods = res.get_json()
    tmall_ids = [p["id"] for p in prods if p.get("source") == "lazada_tmall"]
    assert tmall_ids == [pid1]

    # 2. Update settings via POST /api/settings triggers immediate DB purge
    res_set = client.post("/api/settings", json={"tmall_max_price": 10000000.0})
    assert res_set.status_code == 200

    # In DB, invalid products #2, #3, #4 must now be permanently deleted
    all_db = [dict(p) for p in db.get_products_with_latest_price() if dict(p).get("source") == "lazada_tmall"]
    assert len(all_db) == 1
    assert all_db[0]["id"] == pid1


def test_track_deal_with_target_price_upgrades_source(tmp_path):
    db_file = tmp_path / "test_track_target.db"
    db = DB(str(db_file))
    cfg = Config()
    adapter = MockAdapter()
    notifier = Notifier(cfg)
    quota = QuotaMonitor(cfg, notifier)
    scanner = Scanner(cfg, adapter, db, notifier, quota)
    app = create_app(cfg, db, scanner)
    client = app.test_client()

    # Pre-populate a product discovered from TMALL (source='lazada_tmall')
    s_tmall = Snapshot(
        platform="lazada",
        url="https://www.lazada.vn/products/item-i123456789.html",
        item_key="123456789",
        name="Tai nghe Bluetooth TMALL",
        shop="Official Shop",
        price=350000.0,
        list_price=500000.0,
        stock=True,
        category="Thiết Bị Điện Tử",
    )
    pid = db.add_product_url(s_tmall.url, s_tmall.platform, s_tmall.item_key, source="lazada_tmall")
    db.upsert_product_meta(s_tmall, source="lazada_tmall")
    db.save_snapshot(pid, s_tmall, campaign="TMALL Trợ Giá")

    assert db.get_product(pid)["source"] == "lazada_tmall"
    assert db.get_product(pid)["target_price"] is None
    assert pid not in [p["id"] for p in db.get_active_tracked_products()]

    # User tracks it with target_price = 280,000₫
    res = client.post("/api/products", json={
        "url": s_tmall.url,
        "target_price": 280000.0
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["id"] == pid

    # Verify source upgraded to 'user', target_price stored, and in active tracked products
    updated = db.get_product(pid)
    assert updated["source"] == "user"
    assert updated["target_price"] == 280000.0
    assert pid in [p["id"] for p in db.get_active_tracked_products()]


def test_product_reactivate_endpoint_and_include_inactive(tmp_path):
    from deal_hunter.web import create_app
    db_file = tmp_path / "test_reactivate.db"
    db = DB(str(db_file))
    config = Config.from_env()
    app = create_app(config, db, None)
    client = app.test_client()

    pid = db.add_product_url("https://lazada.vn/p1", "lazada", "item1", source="user")
    # Deactivate
    with db._lock:
        db.conn.execute("UPDATE products SET active=0, fail_count=5 WHERE id=?", (pid,))
        db.conn.commit()

    # get_products_with_latest_price(include_inactive=False) excludes it
    assert len(db.get_products_with_latest_price(include_inactive=False)) == 0
    # include_inactive=True includes it
    assert len(db.get_products_with_latest_price(include_inactive=True)) == 1

    # Call reactivate endpoint
    res = client.post(f"/api/products/{pid}/reactivate")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ok"
    assert res.get_json()["active"] == 1

    # Product is active again and fail_count is reset to 0
    prod = db.get_product(pid)
    assert prod["active"] == 1
    assert prod["fail_count"] == 0
    assert len(db.get_products_with_latest_price(include_inactive=False)) == 1


def test_db_init_keeps_deactivated_user_products(tmp_path):
    """Restart must not revive products the user or delisting deactivated (known issue #1, fixed 03/11)."""
    db_file = tmp_path / "test_auto_heal.db"
    db = DB(str(db_file))
    pid = db.add_product_url("https://lazada.vn/p_user", "lazada", "u1", source="user")
    # Simulate legacy bug: deactivated due to fail_count >= 5
    with db._lock:
        db.conn.execute("UPDATE products SET active=0, fail_count=5 WHERE id=?", (pid,))
        db.conn.commit()
    assert len(db.get_active_tracked_products()) == 0

    db2 = DB(str(db_file))
    assert db2.get_active_tracked_products() == []


def test_subsystem_suspension_db_settings_and_price_error_suppression(tmp_path):
    from unittest.mock import MagicMock
    from deal_hunter.adapters.base import Snapshot
    db_file = tmp_path / "test_suspension.db"
    db = DB(str(db_file))
    # Disable subsystems in DB
    db.set_setting("keyword_scan_enabled", "0")
    db.set_setting("megasale_scan_enabled", "0")
    db.set_setting("price_error_scan_enabled", "0")
    db.set_setting("tmall_scan_enabled", "0")

    config = Config.from_env()
    adapter = MockAdapter()
    notifier = MagicMock()
    quota = MagicMock()
    scanner = Scanner(config, adapter, db, notifier, quota)

    # Initial scan_due: only tracked products should be due, not keyword/megasale/price_error/tmall
    results = scanner.scan_due()
    assert "tracked" in results
    assert "keyword" not in results
    assert "megasale" not in results
    assert "price_error" not in results
    assert "tmall" not in results

    # Verify _handle_price_error suppression when price_error_scan_enabled is 0
    s = Snapshot(platform="lazada", item_key="k1", name="Test Item", shop="Shop 1", url="https://lazada.vn/p1", price=100000.0, list_price=1000000.0, stock=True)
    scanner._handle_price_error(product_id=1, snapshot=s, price=100000.0, baseline=1000000.0, discount=0.90)
    # No anomaly created, no alert sent
    assert len(db.get_anomalies()) == 0
    notifier.alert_admin.assert_not_called()
