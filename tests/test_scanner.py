"""Tests for Scanner — uses MockAdapter and in-memory DB, no network."""

from unittest.mock import MagicMock





from deal_hunter.adapters.mock import MockAdapter

from deal_hunter.notifier import Notifier

from deal_hunter.quota import QuotaMonitor

from deal_hunter.scanner import Scanner





def _make_scanner(config, db, prices=None):

    adapter = MockAdapter(price_sequence=prices)

    notifier = MagicMock(spec=Notifier)

    quota = MagicMock(spec=QuotaMonitor)

    quota.is_exhausted = False

    quota.check.return_value = 50

    return Scanner(config, adapter, db, notifier, quota), notifier





def _add_product(db, url="https://shopee.vn/p-i.111.222"):

    from deal_hunter.adapters.base import BaseAdapter

    return db.add_product_url(url, BaseAdapter.parse_platform(url), BaseAdapter.parse_item_key(url))





# ── Basic scan ────────────────────────────────────────────────────────────────



def test_scan_all_saves_price_history(config, db):

    _add_product(db)

    scanner, _ = _make_scanner(config, db)

    result = scanner.scan_all()

    assert result["ok"] == 1

    assert result["fail"] == 0

    history = db.get_price_history_30d(1)

    assert len(history) == 1





def test_scan_all_no_products_returns_zero(config, db):

    scanner, _ = _make_scanner(config, db)

    result = scanner.scan_all()

    assert result == {"ok": 0, "fail": 0}





def test_quota_exhausted_does_not_skip_scan(config, db):

    _add_product(db)

    adapter = MockAdapter()

    notifier = MagicMock(spec=Notifier)

    quota = MagicMock(spec=QuotaMonitor)

    quota.is_exhausted = True

    scanner = Scanner(config, adapter, db, notifier, quota)

    result = scanner.scan_all()

    # Scanning proceeds by cookie even when captcha quota is exhausted

    assert result["ok"] == 1

    assert db.get_price_history_30d(1) != []







# ── Deal detection integration ─────────────────────────────────────────────────



def test_deal_triggers_broadcast_after_enough_history(config, db):

    """Simulate 5 scans: first 4 at 100k (builds history), 5th at 60k (deal)."""

    url = "https://shopee.vn/p-i.111.222"

    _add_product(db, url)



    # Scans 1-4: build history at 100_000

    for _ in range(4):

        scanner, notifier = _make_scanner(config, db, prices=[100_000])

        scanner.scan_all()



    # Scan 5: price drops to 60_000 (40% off median of 100_000)

    scanner, notifier = _make_scanner(config, db, prices=[60_000])

    scanner.scan_all()



    notifier.broadcast_deal.assert_called_once()

    call_args = notifier.broadcast_deal.call_args

    assert "60" in call_args[0][0] or "60" in str(call_args)





def test_no_deal_alert_during_cold_start(config, db):

    """First 3 scans: deal detection (median) should NOT fire (cold start).

    Price-drop broadcast may fire on 3rd scan (60k vs 100k) — that's correct."""

    url = "https://shopee.vn/p-i.111.222"

    _add_product(db, url)



    for i in range(3):

        scanner, notifier = _make_scanner(config, db, prices=[100_000 if i < 2 else 60_000])

        scanner.scan_all()



    # REAL_DEAL alert (includes "trung vi") must NOT have fired during cold start

    for call in notifier.broadcast_deal.call_args_list:

        msg = call[0][0] if call[0] else ""

        assert "trung v\u1ecb" not in msg, "REAL_DEAL alert fired too early (cold start)"





# ── Alerter anti-duplication ──────────────────────────────────────────────────



def test_deal_not_resent_within_24h(config, db):

    url = "https://shopee.vn/p-i.111.222"

    _add_product(db, url)



    # Build sufficient history

    for _ in range(4):

        scanner, _ = _make_scanner(config, db, prices=[100_000])

        scanner.scan_all()



    # First deal scan

    scanner, notifier = _make_scanner(config, db, prices=[60_000])

    scanner.scan_all()

    assert notifier.broadcast_deal.call_count == 1



    # Immediate second scan at same deal price — should NOT re-send

    scanner2, notifier2 = _make_scanner(config, db, prices=[60_000])

    scanner2.scan_all()

    notifier2.broadcast_deal.assert_not_called()





def test_discover_keyword(config, db):

    scanner, _ = _make_scanner(config, db)

    pids = scanner.discover_keyword("ban phim", limit=3)

    assert len(pids) == 3

    active = db.get_active_products()

    assert len(active) == 3

    prod = db.get_product(pids[0])

    assert prod["name"] in ("ban phim", "Mock Product [101.201]")





def test_discover_keyword_lowest_only(config, db):

    scanner, _ = _make_scanner(config, db, prices=[150_000, 79_000, 320_000])

    pids = scanner.discover_keyword("chuot logitech", limit=3, lowest_only=True)

    assert len(pids) == 1

    prod = db.get_product(pids[0])

    assert prod is not None

    assert prod["source"] == "user"

    latest_price = db.get_latest_price(pids[0])

    assert latest_price == 79_000





def test_discover_keyword_lazada(config, db):

    scanner, _ = _make_scanner(config, db)

    pids = scanner.discover_keyword("ban phim", limit=3, platform="lazada")

    assert len(pids) == 3

    prod = db.get_product(pids[0])

    assert prod["platform"] == "lazada"

    assert "lazada.vn" in prod["url"]





def test_discover_keyword_cross_platform_lowest(config, db):

    # Candidate 1 (Shopee): 150_000, Candidate 2 (Lazada): 85_000, Candidate 3 (Shopee): 200_000

    scanner, _ = _make_scanner(config, db, prices=[150_000, 85_000, 200_000])

    pids = scanner.discover_keyword("chuot logitech", limit=3, lowest_only=True, platform="all")

    assert len(pids) == 1

    prod = db.get_product(pids[0])

    assert prod["platform"] == "lazada"

    assert db.get_latest_price(pids[0]) == 85_000





def test_discover_keyword_blocked(config, db):

    from deal_hunter.adapters.base import Blocked

    scanner, notifier = _make_scanner(config, db)

    scanner._adapter.search = MagicMock(side_effect=Blocked("Blocked"))

    pids = scanner.discover_keyword("ban phim", limit=3)

    assert pids == []

    notifier.alert_admin.assert_called_once()







def test_target_price_triggers_alert(config, db):

    """When snapshot price is <= target_price, trigger alert even without 30d history."""

    url = "https://shopee.vn/p-i.111.222"

    pid = _add_product(db, url)

    db.set_target_price(pid, 80_000)



    # Scan with price 75_000 (<= 80_000)

    scanner, notifier = _make_scanner(config, db, prices=[75_000, 75_000])

    scanner.scan_all()



    notifier.broadcast_deal.assert_called_once()

    msg = notifier.broadcast_deal.call_args[0][0]

    assert "ĐẠT GIÁ MONG MUỐN" in msg

    assert "75,000" in msg

    assert "80,000" in msg



    # ADR 0065: same price again within 24h is not repeated

    scanner.scan_all()

    assert notifier.broadcast_deal.call_count == 1





def test_target_alert_repeats_on_further_drop_and_reentry(config, db):

    """ADR 0065: alert again on ≥5% further drop, and after leaving and re-entering the target range."""

    pid = _add_product(db)

    db.set_target_price(pid, 80_000)

    scanner, notifier = _make_scanner(config, db, prices=[79_000, 79_000, 70_000, 90_000, 79_000])

    scanner.scan_all()   # 79k: enters range -> alert

    scanner.scan_all()   # 79k: unchanged -> silent

    assert notifier.broadcast_deal.call_count == 1

    scanner.scan_all()   # 70k: >=5% further drop -> alert

    assert notifier.broadcast_deal.call_count == 2

    scanner.scan_all()   # 90k: leaves range -> silent, state forgotten

    assert notifier.broadcast_deal.call_count == 2

    scanner.scan_all()   # 79k: re-entry -> alert

    assert notifier.broadcast_deal.call_count == 3





def test_tier2_failure_skips_cycle(config, db):

    """ADR 0060: when the tier-2 verifier fails, the unverified tier-1 price is neither saved nor alerted."""

    from deal_hunter.adapters.base import FetchError

    from deal_hunter.models import Snapshot

    pid = _add_product(db)

    db.set_target_price(pid, 80_000)

    adapter = MagicMock()

    adapter.ensure_authenticated.return_value = True

    adapter.fast_fetch.return_value = Snapshot(platform="shopee", item_key="111.222", url="https://shopee.vn/p-i.111.222", name="P", shop="S", price=70_000, list_price=None, stock=True)

    adapter.fetch.side_effect = FetchError("captcha")

    notifier = MagicMock(spec=Notifier)

    quota = MagicMock(spec=QuotaMonitor)

    quota.is_exhausted = False

    scanner = Scanner(config, adapter, db, notifier, quota)

    assert scanner.scan_product(pid) is None

    notifier.broadcast_deal.assert_not_called()

    assert db.get_latest_price(pid) is None





def test_target_alert_escapes_html_in_name(config, db):

    from deal_hunter.models import Snapshot

    pid = _add_product(db)

    db.set_target_price(pid, 80_000)

    adapter = MagicMock(spec=["fetch", "ensure_authenticated"])

    adapter.ensure_authenticated.return_value = True

    adapter.fetch.return_value = Snapshot(platform="shopee", item_key="111.222", url="https://shopee.vn/p-i.111.222", name="Combo <Hàng chính hãng>", shop="S", price=75_000, list_price=None, stock=True)

    notifier = MagicMock(spec=Notifier)

    quota = MagicMock(spec=QuotaMonitor)

    quota.is_exhausted = False

    Scanner(config, adapter, db, notifier, quota).scan_product(pid)

    msg = notifier.broadcast_deal.call_args[0][0]

    assert "&lt;Hàng chính hãng&gt;" in msg





def test_target_price_does_not_trigger_when_above(config, db):

    """When snapshot price is > target_price, do not trigger target price alert."""

    url = "https://shopee.vn/p-i.111.222"

    pid = _add_product(db, url)

    db.set_target_price(pid, 50_000)



    # Scan with price 75_000 (> 50_000)

    scanner, notifier = _make_scanner(config, db, prices=[75_000])

    scanner.scan_all()



    notifier.broadcast_deal.assert_not_called()





def test_scan_all_concurrency_lock(config, db):

    """When a scan is already running, concurrent scan_all call exits immediately."""

    _add_product(db)

    scanner, _ = _make_scanner(config, db)

    # Simulate a running scan holding the lock

    scanner._scan_lock.acquire()

    try:

        assert scanner.is_scanning is True

        res = scanner.scan_all()

        assert res == {"ok": 0, "fail": 0, "msg": "scan_in_progress"}

    finally:

        scanner._scan_lock.release()

    assert scanner.is_scanning is False





def test_scan_product_deactivates_flash_sale_when_out_of_stock(config, db):

    """When a flash_sale product is out of stock, it is deactivated."""

    from deal_hunter.models import Snapshot

    pid = db.add_product_url("https://shopee.vn/fs-i.999.888", "shopee", "999.888", source="flash_sale")

    scanner, notifier = _make_scanner(config, db)

    # Mock adapter fetch to return out-of-stock snapshot

    scanner._adapter.fetch = MagicMock(return_value=Snapshot(

        platform="shopee", item_key="999.888", url="https://shopee.vn/fs-i.999.888",

        name="Flash Deal Sold Out", shop="", price=50_000, list_price=100_000,

        stock=False, rating=4.5, sold=50,

    ))

    snap = scanner.scan_product(pid)

    assert snap.stock is False

    prod = db.get_product(pid)

    assert prod["active"] == 0

    notifier.broadcast_deal.assert_not_called()





def test_scan_product_suppresses_alerts_when_out_of_stock(config, db):

    """When user product meets target price or deal criteria but is out of stock, alerts are suppressed."""

    from deal_hunter.models import Snapshot

    pid = db.add_product_url("https://shopee.vn/u-i.777.666", "shopee", "777.666", source="user")

    db.set_target_price(pid, 100_000)

    scanner, notifier = _make_scanner(config, db)

    # Price is 50_000 (below target price of 100_000), but stock is False

    scanner._adapter.fetch = MagicMock(return_value=Snapshot(

        platform="shopee", item_key="777.666", url="https://shopee.vn/u-i.777.666",

        name="User Product OOS", shop="", price=50_000, list_price=100_000,

        stock=False, rating=4.8, sold=120,

    ))

    snap = scanner.scan_product(pid)

    assert snap.stock is False

    prod = db.get_product(pid)

    # User product stays active for restock

    assert prod["active"] == 1

    # But alert is strictly suppressed!

    notifier.broadcast_deal.assert_not_called()





def test_compare_shops_finds_cheaper_alternative(config, db):

    """compare_shops finds cheaper shop for a tracked product."""

    from deal_hunter.models import Snapshot

    pid = db.add_product_url("https://shopee.vn/shopA-i.111.222", "shopee", "111.222", source="user")

    # Current product snapshot at 200,000₫

    cur_snap = Snapshot(

        platform="shopee", item_key="111.222", url="https://shopee.vn/shopA-i.111.222",

        name="Bàn Phím Cơ Aula F75", shop="Shop A", price=200_000, list_price=250_000, stock=True,

        rating=4.9, sold=500,

    )

    db.upsert_product_meta(cur_snap)

    db.save_snapshot(pid, cur_snap)



    scanner, _ = _make_scanner(config, db)

    scanner._adapter.search = MagicMock(return_value=["https://shopee.vn/shopB-i.333.444"])

    # Shop B sells same item at 160,000₫ with 10k voucher -> final 150,000₫

    cheaper_snap = Snapshot(

        platform="shopee", item_key="333.444", url="https://shopee.vn/shopB-i.333.444",

        name="Bàn Phím Cơ Aula F75 Pro Chính Hãng", shop="Shop B", price=160_000, list_price=220_000,

        stock=True, rating=4.8, sold=300, voucher_code="SHOPB10K", voucher_discount=10_000, final_price=150_000,

    )

    scanner._adapter.fetch = MagicMock(return_value=cheaper_snap)



    res = scanner.compare_shops(pid)

    assert res["status"] == "found_cheaper"

    assert res["savings"] == 50_000.0

    assert res["cheaper_product"]["name"] == cheaper_snap.name

    assert res["cheaper_product"]["final_price"] == 150_000





def test_discover_flash_sale_multi_platform(config, db):

    """discover_flash_sale supports shopee, lazada, and all platforms."""

    scanner, _ = _make_scanner(config, db)

    # Test Shopee

    ids_shopee = scanner.discover_flash_sale(limit=2, platform="shopee")

    assert len(ids_shopee) == 2

    for pid in ids_shopee:

        p = db.get_product(pid)

        assert p["platform"] == "shopee"

        assert p["source"] == "flash_sale"



    # Test Lazada

    ids_lazada = scanner.discover_flash_sale(limit=2, platform="lazada")

    assert len(ids_lazada) == 2

    for pid in ids_lazada:

        p = db.get_product(pid)

        assert p["platform"] == "lazada"

        assert p["source"] == "flash_sale"



    # Test all

    ids_all = scanner.discover_flash_sale(limit=2, platform="all")

    assert len(ids_all) == 4

    platforms = {db.get_product(pid)["platform"] for pid in ids_all}

    assert "shopee" in platforms

    assert "lazada" in platforms





def test_product_delisted_auto_deactivation(config, db):

    from deal_hunter.adapters.base import ProductDelisted

    pid = _add_product(db, "https://www.lazada.vn/products/deleted-i999-s999.html")

    assert db.get_product(pid)["active"] == 1



    adapter = MagicMock()

    adapter.fetch.side_effect = ProductDelisted("Product 404")

    notifier = MagicMock()

    quota = MagicMock(is_exhausted=False)

    scanner = Scanner(config, adapter, db, notifier, quota)



    res = scanner.scan_product(pid)

    assert res is None

    assert db.get_product(pid)["active"] == 0

    notifier.alert_admin.assert_called_once()

    assert "ngừng kinh doanh" in notifier.alert_admin.call_args[0][0]





def test_tracked_product_price_drop_alert(config, db):

    pid = _add_product(db, "https://shopee.vn/p-i.111.222")



    # Initial scan at 200_000

    s1, _ = _make_scanner(config, db, prices=[200_000])

    s1.scan_all()



    # Second scan with price drop to 150_000

    s2, notifier2 = _make_scanner(config, db, prices=[150_000])

    s2.scan_all()



    notifier2.broadcast_deal.assert_called_once()

    assert "GI\u1ea2M GI\xc1 S\u1ea2N PH\u1ea8M THEO D\xd5I" in notifier2.broadcast_deal.call_args[0][0]

    assert "150,000" in notifier2.broadcast_deal.call_args[0][0]





def test_discover_flash_sale_instant_alert_muted(config, db):

    """Flash sale items are saved to DB but Telegram broadcast is muted per user request."""

    from deal_hunter.models import Snapshot

    scanner, notifier = _make_scanner(config, db)

    deal_snap = Snapshot(

        platform="shopee", item_key="11.22", url="https://shopee.vn/p-11.22",

        name="Hot Deal Mouse", shop="Logi Shop", price=60_000, list_price=100_000,

        stock=True, rating=4.8, sold=300, voucher_code="SHOP_10K", voucher_discount=10_000,

        final_price=50_000,

    )

    normal_snap = Snapshot(

        platform="shopee", item_key="33.44", url="https://shopee.vn/p-33.44",

        name="Small Deal Mouse", shop="Shop B", price=90_000, list_price=100_000,

        stock=True, rating=4.0, sold=10,

    )

    scanner._adapter.crawl_flash_sale = MagicMock(return_value=[deal_snap, normal_snap])

    ids = scanner.discover_flash_sale(limit=2)

    assert len(ids) == 2

    # Telegram broadcast muted for flash sale

    assert notifier.broadcast_deal.call_count == 0





def test_discover_tmall_subsidy_muted_in_flash_sale(config, db):

    """TMALL items discovered via flash sale do not broadcast to Telegram."""

    from deal_hunter.models import Snapshot

    scanner, notifier = _make_scanner(config, db)

    akko_snap = Snapshot(

        platform="lazada", item_key="111.222", url="https://www.lazada.vn/products/akko-i111.html",

        name="[TMALL TRỢ GIÁ] Akko | Bàn Phím Cơ Gem 01", shop="AKKO Official Store",

        price=357_735, list_price=3_407_000, stock=True, rating=4.9, sold=120,

    )

    scanner._adapter.crawl_flash_sale = MagicMock(return_value=[akko_snap])

    ids = scanner.discover_flash_sale(limit=1, platform="lazada")

    assert len(ids) == 1

    assert notifier.broadcast_deal.call_count == 0





def test_discover_flash_sale_filters_junk_under_500k(config, db):

    """Items with original/list price < deal_min_original_price (500k) are discarded as junk."""

    from deal_hunter.models import Snapshot

    config.deal_min_original_price = 500_000.0

    scanner, notifier = _make_scanner(config, db)



    junk_snap = Snapshot(

        platform="shopee", item_key="junk1", url="https://shopee.vn/op-lung-i.1.2",

        name="Ốp lưng điện thoại Silicon", shop="Shop Phụ Kiện", price=15_000, list_price=30_000,

        stock=True, rating=4.8, sold=500,

    )

    good_snap = Snapshot(

        platform="lazada", item_key="good1", url="https://www.lazada.vn/products/ram-i99.html",

        name="RAM Laptop 16GB", shop="Lenovo Official", price=588_550, list_price=5_257_000,

        stock=True, rating=4.9, sold=80,

    )



    scanner._adapter.crawl_flash_sale = MagicMock(return_value=[junk_snap, good_snap])

    ids = scanner.discover_flash_sale(limit=2)

    # Only good_snap (list_price 5.2M >= 500k) should be saved

    assert len(ids) == 1

    saved_prod = db.get_product(ids[0])

    assert saved_prod["name"] == "RAM Laptop 16GB"

    # Total active products in db is exactly 1 (junk was never added)

    assert len(db.get_active_products()) == 1





def test_real_deal_alert_suppressed_for_junk_under_500k(config, db):

    """Auto-discovered deals with 30-day median < 500k are not broadcasted to Telegram channel."""

    config.deal_min_original_price = 500_000.0

    url = "https://shopee.vn/p-i.999.888"

    pid = db.add_product_url(url, "shopee", "999.888", source="flash_sale")



    # Scans 1-4: 30-day median = 200_000 (< 500k)

    for _ in range(4):

        scanner, notifier = _make_scanner(config, db, prices=[200_000])

        scanner.scan_all()



    # Scan 5: drops to 100_000 (50% off median 200k)

    scanner, notifier = _make_scanner(config, db, prices=[100_000])

    scanner.scan_all()



    # broadcast_deal must NOT be called because median 200k < min_original_price 500k

    notifier.broadcast_deal.assert_not_called()





def test_scan_product_detects_price_error_against_prior_scan_price(config, db):

    """When a tracked product has < 3 scans (no median_30d), a severe drop vs history[0] triggers price error."""

    from unittest.mock import MagicMock

    config.deal_min_original_price = 500_000.0

    url = "https://www.lazada.vn/products/aula-f75-i123.html"

    pid = db.add_product_url(url, "lazada", "123", source="user")



    # Scan 1: regular price 2,230,000₫

    scanner, notifier = _make_scanner(config, db, prices=[2_230_000.0])

    scanner.scan_product(pid)



    # Scan 2: price erroneously drops to 223,000₫ (90% drop)

    scanner2, notifier2 = _make_scanner(config, db, prices=[223_000.0])

    scanner2._handle_price_error = MagicMock()

    scanner2.scan_product(pid)



    # _handle_price_error must be called using history[0] (2,230,000) as baseline

    scanner2._handle_price_error.assert_called_once()

    args = scanner2._handle_price_error.call_args[0]

    assert args[0] == pid

    assert args[2] == 223_000.0

    assert args[3] == 2_230_000.0

    assert round(args[4], 2) == 0.90





def test_scan_product_tracked_skips_rating(config, db):

    """User tracked product passes is_tracked=True to adapter and bypasses rating requirement."""

    from unittest.mock import MagicMock

    config.deal_min_rating = 4.8

    url = "https://shopee.vn/product-i.111.222"

    pid = db.add_product_url(url, "shopee", "111.222", source="user")



    scanner, _ = _make_scanner(config, db, prices=[100_000])

    orig_fetch = scanner._adapter.fetch

    scanner._adapter.fetch = MagicMock(side_effect=lambda *args, **kwargs: orig_fetch(*args, **kwargs))



    snap = scanner.scan_product(pid)

    assert snap is not None

    # Adapter fetch was called with is_tracked=True

    scanner._adapter.fetch.assert_called_once_with(url, target_sku=None, is_tracked=True)





def test_scan_platform_blocked_token_fallback(config, db):

    from unittest.mock import MagicMock, patch

    from deal_hunter.adapters.base import Blocked

    from deal_hunter.scanner import Scanner



    _add_product(db, url="https://shopee.vn/product-i.123.456")

    adapter = MagicMock()

    adapter.fetch.side_effect = Blocked("Bot detected")

    notifier = MagicMock()

    quota = MagicMock()

    quota.is_exhausted = False

    quota.get_remaining_credits.return_value = 0



    scanner = Scanner(config, adapter, db, notifier, quota)

    products = [{"id": 1, "url": "https://shopee.vn/product-i.123.456"}]



    # Case 1: Token invalid

    with patch("deal_hunter.login.check_session_valid", return_value=False):

        ok, fail = scanner._scan_platform("shopee", products)

        assert ok == 0

        assert fail == 1

        assert any("hết hạn" in call[0][0] for call in notifier.alert_admin.call_args_list)



    # Case 2: Token valid, but captcha blocked (quota exhausted)

    notifier.reset_mock()

    scanner._paused_until.clear(); scanner._pause_alerted.clear()  # ADR 0067: end the pause the first block started

    with patch("deal_hunter.login.check_session_valid", return_value=True):

        ok, fail = scanner._scan_platform("shopee", products)

        assert ok == 0

        assert fail == 1

        assert any("Captcha" in call[0][0] for call in notifier.alert_admin.call_args_list)

















def test_scan_product_tier1_fast_fetch_success(config, db):
    from deal_hunter.models import Snapshot
    p_id = _add_product(db, "https://shopee.vn/product-i.123.456")
    db.set_target_price(p_id, 500000)
    db.save_snapshot(p_id, Snapshot(platform="shopee", item_key="123.456", url="https://shopee.vn/product-i.123.456", name="Shopee Item", shop="Test Shop", price=800000, list_price=1000000, stock=True))

    scanner, _ = _make_scanner(config, db)
    fast_snap = Snapshot(platform="shopee", item_key="123.456", url="https://shopee.vn/product-i.123.456", name="Shopee Item", shop="Test Shop", price=790000, list_price=1000000, stock=True)
    scanner._adapter.fast_fetch = MagicMock(return_value=fast_snap)
    scanner._adapter.fetch = MagicMock()

    res = scanner.scan_product(p_id)

    assert res == fast_snap
    scanner._adapter.fast_fetch.assert_called_once()
    scanner._adapter.fetch.assert_not_called()


def test_scan_product_tier1_fast_fetch_escalates_to_tier2(config, db):
    from deal_hunter.models import Snapshot
    p_id = _add_product(db, "https://shopee.vn/product-i.123.456")
    db.set_target_price(p_id, 500000)
    db.save_snapshot(p_id, Snapshot(platform="shopee", item_key="123.456", url="https://shopee.vn/product-i.123.456", name="Shopee Item", shop="Test Shop", price=800000, list_price=1000000, stock=True))

    scanner, _ = _make_scanner(config, db)
    # Fast fetch detects price drop > 20% (800k -> 450k)
    fast_snap = Snapshot(platform="shopee", item_key="123.456", url="https://shopee.vn/product-i.123.456", name="Shopee Item", shop="Test Shop", price=450000, list_price=1000000, stock=True)
    verified_snap = Snapshot(platform="shopee", item_key="123.456", url="https://shopee.vn/product-i.123.456", name="Shopee Item", shop="Test Shop", price=450000, list_price=1000000, stock=True)

    scanner._adapter.fast_fetch = MagicMock(return_value=fast_snap)
    scanner._adapter.fetch = MagicMock(return_value=verified_snap)

    res = scanner.scan_product(p_id)

    assert res == verified_snap
    scanner._adapter.fast_fetch.assert_called_once()
    scanner._adapter.fetch.assert_called_once()


def test_scan_product_tier1_escalates_on_target_price_hit(config, db):
    """Chạm giá mong muốn với mức giảm nhỏ (<20%) vẫn phải qua Tier-2 xác thực (ADR 0060)."""
    from deal_hunter.models import Snapshot
    url = "https://shopee.vn/product-i.123.456"
    p_id = _add_product(db, url)
    db.set_target_price(p_id, 795000)
    db.save_snapshot(p_id, Snapshot(platform="shopee", item_key="123.456", url=url, name="Shopee Item", shop="Test Shop", price=800000, list_price=1000000, stock=True))

    scanner, _ = _make_scanner(config, db)
    fast_snap = Snapshot(platform="shopee", item_key="123.456", url=url, name="Shopee Item", shop="Test Shop", price=790000, list_price=1000000, stock=True)
    verified_snap = Snapshot(platform="shopee", item_key="123.456", url=url, name="Shopee Item", shop="Test Shop", price=790000, list_price=1000000, stock=True)
    scanner._adapter.fast_fetch = MagicMock(return_value=fast_snap)
    scanner._adapter.fetch = MagicMock(return_value=verified_snap)

    res = scanner.scan_product(p_id)

    assert res == verified_snap
    scanner._adapter.fetch.assert_called_once()


def test_scan_due_reads_dynamic_interval_from_db(config, db):
    from unittest.mock import patch
    scanner, _ = _make_scanner(config, db)
    
    db.set_setting("scan_interval_min", "10")
    scanner._last_tracked_scan_time = 1000.0
    
    with patch("time.time", return_value=1000.0 + 300.0): # 5 min passed < 10 min
        with patch.object(scanner, "scan_tracked_products") as mock_scan:
            scanner.scan_due()
            mock_scan.assert_not_called()

    with patch("time.time", return_value=1000.0 + 601.0): # 10.01 min passed >= 10 min
        with patch.object(scanner, "scan_tracked_products") as mock_scan:
            scanner.scan_due()
            mock_scan.assert_called_once()


def test_scan_due_rests_after_a_long_cycle(config, db):
    """ADR 0066: a cycle longer than the interval must not start the next one immediately."""
    from unittest.mock import patch
    scanner, _ = _make_scanner(config, db)
    db.set_setting("scan_interval_min", "10")
    clock = [1000.0]
    def slow_scan():
        clock[0] += 1800.0  # the cycle takes 30 min
        return {"ok": 0, "fail": 0}
    with patch("time.time", side_effect=lambda: clock[0]):
        with patch.object(scanner, "scan_tracked_products", side_effect=slow_scan) as mock_scan:
            scanner.scan_due()
            scanner.scan_due()  # straight after the 30-min cycle: still resting
            assert mock_scan.call_count == 1
            clock[0] += 61.0
            scanner.scan_due()
            assert mock_scan.call_count == 2


def test_adaptive_cadence_skips_far_products_two_cycles(config, db):
    """ADR 0066: far from target with a stable price -> every third cycle; within 10% -> every cycle."""
    from unittest.mock import patch
    pid = db.add_product_url("https://www.lazada.vn/products/far-i111.html", "lazada", "111", source="user")
    db.set_target_price(pid, 100_000.0)
    scanner, _ = _make_scanner(config, db, prices=[500_000.0] * 5)
    scanner.scan_product(pid)  # price known, far from target
    with patch.object(scanner, "_scan_platform", return_value=(0, 0)) as mock_platform:
        scanner.scan_tracked_products()
        scanner.scan_tracked_products()
        mock_platform.assert_not_called()
        scanner.scan_tracked_products()
        mock_platform.assert_called_once()
    db.set_target_price(pid, 480_000.0)  # within 10%: every cycle
    with patch.object(scanner, "_scan_platform", return_value=(0, 0)) as mock_platform:
        scanner.scan_tracked_products()
        mock_platform.assert_called_once()


def test_platform_pauses_after_three_blocks(config, db):
    """ADR 0067: three consecutive blocks pause the platform 30 min with one alert; a successful probe resumes it."""
    import time
    from unittest.mock import patch
    from deal_hunter.adapters.base import Blocked
    for i in (1, 2, 3, 4):
        db.add_product_url(f"https://www.lazada.vn/products/x-i{i}.html", "lazada", str(i), source="user")
    scanner, notifier = _make_scanner(config, db)
    good = scanner._adapter
    adapter = MagicMock(); adapter.fast_fetch.return_value = None; adapter.fetch.side_effect = Blocked("captcha")
    scanner._adapter = adapter
    with patch("time.sleep"):
        scanner.scan_tracked_products()
    assert adapter.fetch.call_count == 3
    assert notifier.alert_admin.call_count == 1
    assert "30 phút" in notifier.alert_admin.call_args[0][0]
    adapter.fetch.reset_mock()
    with patch("time.sleep"):
        scanner.scan_tracked_products()  # paused: nothing fetched, no new alert
    assert adapter.fetch.call_count == 0 and notifier.alert_admin.call_count == 1
    scanner._paused_until["lazada"] = time.time() - 1  # pause over: probe with one product
    with patch("time.sleep"):
        scanner.scan_tracked_products()
    assert adapter.fetch.call_count == 1 and notifier.alert_admin.call_count == 1  # blocked again: silent re-pause
    scanner._paused_until["lazada"] = time.time() - 1
    scanner._adapter = good
    with patch("time.sleep"):
        scanner.scan_tracked_products()
    assert notifier.alert_admin.call_count == 2
    assert "quét lại" in notifier.alert_admin.call_args[0][0]
    assert "lazada" not in scanner._paused_until


def test_fresh_cookies_end_the_pause_early(config, db):
    """ADR 0067: pasting cookies ends the rest; the next cycle probes at once instead of waiting 30 min."""
    import time
    from unittest.mock import patch
    from deal_hunter.adapters.base import Blocked
    for i in (1, 2, 3, 4):
        db.add_product_url(f"https://www.lazada.vn/products/x-i{i}.html", "lazada", str(i), source="user")
    scanner, notifier = _make_scanner(config, db)
    adapter = MagicMock(); adapter.fast_fetch.return_value = None; adapter.fetch.side_effect = Blocked("captcha")
    scanner._adapter = adapter
    with patch("time.sleep"):
        scanner.scan_tracked_products()  # 3 blocks -> paused 30 min
    adapter.fetch.reset_mock()
    scanner.end_pause("shopee")  # other platform: no effect
    scanner.end_pause("lazada")
    with patch("time.sleep"):
        scanner.scan_tracked_products()
    assert adapter.fetch.call_count == 1  # probed one product right away, silently re-paused
    assert notifier.alert_admin.call_count == 1
    assert scanner._paused_until["lazada"] > time.time() + 1700


def test_only_target_price_alerts_mode(config, db):
    """When only_target_price_alerts is True, suppress price drop and error alerts, only send target price alerts."""
    url = "https://shopee.vn/product-i.777.888"
    pid = db.add_product_url(url, "shopee", "777.888", source="user")
    db.set_target_price(pid, 100_000.0)

    # Scan 1: initial price 200,000
    scanner, notifier = _make_scanner(config, db, prices=[200_000.0])
    scanner.scan_product(pid)

    # Turn on only_target_price_alerts
    db.set_setting("only_target_price_alerts", "1")

    # Scan 2: price drops to 150,000 (above target 100k)
    s2, n2 = _make_scanner(config, db, prices=[150_000.0])
    s2._send_price_drop_alert = MagicMock()
    s2._send_target_alert = MagicMock()
    s2._handle_price_error = MagicMock()
    s2.scan_product(pid)

    s2._send_price_drop_alert.assert_not_called()
    s2._send_target_alert.assert_not_called()
    s2._handle_price_error.assert_not_called()

    # Scan 3: price drops to 90,000 (below target 100k)
    s3, n3 = _make_scanner(config, db, prices=[90_000.0])
    s3._send_price_drop_alert = MagicMock()
    s3._send_target_alert = MagicMock()
    s3._handle_price_error = MagicMock()
    s3.scan_product(pid)

    s3._send_target_alert.assert_called_once()
    s3._send_price_drop_alert.assert_not_called()
    s3._handle_price_error.assert_not_called()

    # Scan 4: Turn off only_target_price_alerts, price drops to 70k (no target set)
    pid2 = db.add_product_url("https://shopee.vn/product-i.999.000", "shopee", "999.000", source="user")
    s4, _ = _make_scanner(config, db, prices=[100_000.0])
    s4.scan_product(pid2)

    db.set_setting("only_target_price_alerts", "0")
    s5, _ = _make_scanner(config, db, prices=[70_000.0])
    s5._send_price_drop_alert = MagicMock()
    s5.scan_product(pid2)
    s5._send_price_drop_alert.assert_called_once()

