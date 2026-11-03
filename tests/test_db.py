"""Tests for db.py — uses :memory: SQLite, no filesystem."""
from deal_hunter.models import Snapshot


def _snapshot(price=100_000, list_price=150_000, item_key="111.222", platform="shopee", **kwargs):
    return Snapshot(
        platform=platform,
        item_key=item_key,
        url=f"https://shopee.vn/p-i.{item_key.replace('.', '.')}",
        name="Test Product",
        shop="Test Shop",
        price=price,
        list_price=list_price,
        stock=True,
        rating=4.5,
        sold=100,
        **kwargs,
    )


def test_upsert_product_returns_id(db):
    snap = _snapshot()
    pid = db.upsert_product_meta(snap)
    assert isinstance(pid, int) and pid > 0


def test_upsert_product_idempotent(db):
    snap = _snapshot()
    pid1 = db.upsert_product_meta(snap)
    pid2 = db.upsert_product_meta(snap)
    assert pid1 == pid2


def test_save_and_retrieve_price_history(db):
    snap = _snapshot(price=100_000)
    pid = db.upsert_product_meta(snap)
    db.save_snapshot(pid, snap)

    snap2 = _snapshot(price=80_000)
    db.save_snapshot(pid, snap2)

    history = db.get_price_history_30d(pid)
    assert len(history) == 2
    # newest first
    assert history[0] == 80_000
    assert history[1] == 100_000


def test_exclude_latest_removes_first_price(db):
    snap = _snapshot(price=100_000)
    pid = db.upsert_product_meta(snap)
    db.save_snapshot(pid, snap)
    db.save_snapshot(pid, _snapshot(price=90_000))
    db.save_snapshot(pid, _snapshot(price=80_000))

    history_full = db.get_price_history_30d(pid, exclude_latest=False)
    history_excl = db.get_price_history_30d(pid, exclude_latest=True)
    assert len(history_full) == 3
    assert len(history_excl) == 2
    assert history_full[0] not in history_excl or history_excl[0] != history_full[0]


def test_add_product_url_deduplicates(db):
    url = "https://shopee.vn/p-i.111.222"
    pid1 = db.add_product_url(url, "shopee", "111.222")
    pid2 = db.add_product_url(url, "shopee", "111.222")
    assert pid1 == pid2

    products = db.get_active_products()
    assert len(products) == 1


def test_alert_upsert_and_get(db):
    snap = _snapshot()
    pid = db.upsert_product_meta(snap)

    assert db.get_alert(pid) is None

    db.upsert_alert(pid, 80_000.0)
    row = db.get_alert(pid)
    assert row is not None
    assert row["last_price"] == 80_000.0

    # update
    db.upsert_alert(pid, 70_000.0)
    row2 = db.get_alert(pid)
    assert row2["last_price"] == 70_000.0


def test_scan_log(db):
    db.log_scan(ok=5, fail=1, msg="test")
    last = db.get_last_scan()
    assert last["ok"] == 5
    assert last["fail"] == 1
    assert last["msg"] == "test"


def test_get_active_products_only_active(db):
    snap = _snapshot()
    pid = db.upsert_product_meta(snap)
    assert len(db.get_active_products()) == 1

    db.conn.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
    db.conn.commit()
    assert len(db.get_active_products()) == 0


def test_category_and_campaign_persistence(db):
    snap = _snapshot()
    snap.category = "Thiết Bị Điện Tử > Bàn Phím"
    pid = db.upsert_product_meta(snap)
    db.save_snapshot(pid, snap, campaign="11.11 Mega Sale")

    products = db.get_products_with_latest_price()
    assert len(products) == 1
    assert products[0]["category"] == "Thiết Bị Điện Tử > Bàn Phím"
    assert products[0]["current_campaign"] == "11.11 Mega Sale"

    chart_data = db.get_price_history_for_chart(pid)
    assert len(chart_data) == 1
    assert chart_data[0]["campaign"] == "11.11 Mega Sale"


def test_custom_campaign_table(db):
    from datetime import datetime
    db.conn.execute(
        "INSERT INTO campaigns(name, start_date, end_date) VALUES(?, ?, ?)",
        ("Sinh Nhật Shopee", "2026-10-10 00:00:00", "2026-10-20 23:59:59")
    )
    db.conn.commit()
    active = db.get_active_campaign_name(datetime(2026, 10, 15, 12, 0))
    assert active == "Sinh Nhật Shopee"


def test_target_price_db(db):
    snap = _snapshot()
    pid = db.upsert_product_meta(snap)
    db.upsert_alert(pid, 100_000)

    db.set_target_price(pid, 85_000.0)
    row = db.conn.execute("SELECT target_price FROM products WHERE id=?", (pid,)).fetchone()
    assert row[0] == 85_000.0
    # verify alerts cleared on target price update
    assert db.get_alert(pid) is None

    # Clear target price
    db.set_target_price(pid, None)
    row2 = db.conn.execute("SELECT target_price FROM products WHERE id=?", (pid,)).fetchone()
    assert row2[0] is None


def test_delete_product_db(db):
    snap = _snapshot()
    pid = db.upsert_product_meta(snap)
    db.save_snapshot(pid, snap)
    db.upsert_alert(pid, 100_000)

    assert len(db.get_active_products()) == 1
    assert len(db.get_price_history_30d(pid)) == 1

    db.delete_product(pid)
    assert len(db.get_active_products()) == 0
    assert len(db.get_price_history_30d(pid)) == 0
    assert db.get_alert(pid) is None


def test_delete_product_removes_variant_rows(db):
    """Foreign keys are not enforced, so children must be deleted explicitly."""
    from deal_hunter.models import VariantInfo
    snap = _snapshot()
    pid = db.upsert_product_meta(snap)
    db.upsert_variants(pid, [VariantInfo(variant_key="k1", name="Đỏ", price=100_000, stock_state="in")])
    with db._lock:
        assert db.conn.execute("SELECT COUNT(*) FROM variants WHERE product_id=?", (pid,)).fetchone()[0] == 1
    db.delete_product(pid)
    with db._lock:
        assert db.conn.execute("SELECT COUNT(*) FROM variants WHERE product_id=?", (pid,)).fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM variant_history").fetchone()[0] == 0


def test_scan_result_does_not_reactivate_product(db):
    """A late scan result (fast-verify timer) must not revive a product delisted meanwhile."""
    snap = _snapshot()
    pid = db.upsert_product_meta(snap)
    with db._lock:
        db.conn.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
        db.conn.commit()
    db.update_product_from_snapshot(pid, snap)
    assert db.get_product(pid)["active"] == 0


def test_out_of_stock_price_zero_is_not_a_price(db):
    """Out-of-stock rows (price 0) must not become the latest price or pollute the 30-day history."""
    pid = db.upsert_product_meta(_snapshot())
    db.save_snapshot(pid, _snapshot(price=100_000))
    out = _snapshot(price=0.0)
    out.stock = False
    db.save_snapshot(pid, out)
    assert db.get_latest_price(pid) == 100_000
    assert db.get_price_history_30d(pid) == [100_000]


def test_delete_products_bulk_db(db):
    snap1 = _snapshot(item_key="1.1")
    snap2 = _snapshot(item_key="2.2")
    pid1 = db.upsert_product_meta(snap1)
    pid2 = db.upsert_product_meta(snap2)
    assert len(db.get_active_products()) == 2

    db.delete_products([pid1, pid2])
    assert len(db.get_active_products()) == 0


def test_settings_db(db):
    assert db.get_setting("scan_interval_min", "60") == "60"
    db.set_setting("scan_interval_min", "15")
    assert db.get_setting("scan_interval_min") == "15"


def test_voucher_persistence_db(db):
    snap = _snapshot(voucher_code="TESTVOUCHER", voucher_discount=15_000.0, final_price=85_000.0)
    pid = db.upsert_product_meta(snap)
    db.save_snapshot(pid, snap)

    prods = db.get_products_with_latest_price()
    assert len(prods) == 1
    p = dict(prods[0])
    assert p["current_voucher_code"] == "TESTVOUCHER"
    assert p["current_voucher_discount"] == 15_000.0
    assert p["current_final_price"] == 85_000.0


def test_final_price_zero_not_reverted_to_price(db):
    snap = _snapshot(voucher_code="FREE_VOUCHER", voucher_discount=100_000.0, final_price=0.0)
    pid = db.upsert_product_meta(snap)
    db.save_snapshot(pid, snap)

    row = db.conn.execute("SELECT final_price FROM price_history WHERE product_id=?", (pid,)).fetchone()
    assert row["final_price"] == 0.0


def test_update_product_from_snapshot_canonical_and_merge(db):
    # Initial placeholder from short link
    pid1 = db.add_product_url("https://s.lazada.vn/s.Abc", "lazada", "hash_md5_123", source="user")
    assert pid1 > 0

    # Snapshot with canonical URL & item_key
    snap = Snapshot(
        platform="lazada",
        item_key="999.888",
        url="https://www.lazada.vn/products/tai-nghe-i999-s888.html",
        name="Tai Nghe Bluetooth",
        shop="Lazada Shop",
        price=200_000,
        list_price=300_000,
        stock=True,
        rating=4.8,
        sold=50,
    )
    target_pid = db.update_product_from_snapshot(pid1, snap)
    assert target_pid == pid1
    p = db.get_product(pid1)
    assert p["item_key"] == "999.888"
    assert p["url"] == "https://www.lazada.vn/products/tai-nghe-i999-s888.html"
    assert p["name"] == "Tai Nghe Bluetooth"

    # Merge scenario: second placeholder for same canonical item
    pid2 = db.add_product_url("https://s.lazada.vn/s.Xyz", "lazada", "hash_md5_456", source="user")
    db.save_snapshot(pid2, snap)
    merged_pid = db.update_product_from_snapshot(pid2, snap)
    assert merged_pid == pid1
    # pid2 deleted, price history moved to pid1
    assert db.get_product(pid2) is None
    assert len(db.get_price_history_30d(pid1)) >= 1


def test_get_active_products_priority(db):
    p_flash = db.add_product_url("https://shopee.vn/p1", "shopee", "k1", source="flash_sale")
    p_user = db.add_product_url("https://shopee.vn/p2", "shopee", "k2", source="user")

    active = db.get_active_products()
    ids = [row["id"] for row in active if row["platform"] == "shopee"]
    assert ids.index(p_user) < ids.index(p_flash)


def test_purge_junk_flash_sales(db):
    # 1. User product below 500k: MUST NOT be purged
    p_user = db.add_product_url("https://shopee.vn/p-user", "shopee", "u1", source="user")
    db.save_snapshot(p_user, _snapshot(price=80_000, list_price=100_000))

    # 2. Flash sale junk item below 500k: MUST be purged
    p_junk = db.add_product_url("https://shopee.vn/p-junk", "shopee", "j1", source="flash_sale")
    db.save_snapshot(p_junk, _snapshot(price=50_000, list_price=120_000))

    # 3. Flash sale high value deal (800k list price): MUST NOT be purged
    p_deal = db.add_product_url("https://shopee.vn/p-deal", "shopee", "d1", source="flash_sale")
    db.save_snapshot(p_deal, _snapshot(price=350_000, list_price=800_000))

    deleted = db.purge_junk_flash_sales(500_000)
    assert deleted == 1
    assert db.get_product(p_junk) is None
    assert db.get_product(p_user) is not None
    assert db.get_product(p_deal) is not None


def test_price_anomalies_crud(db):
    pid = db.add_product_url("https://shopee.vn/laptop", "shopee", "lap1")
    aid = db.create_anomaly(
        product_id=pid,
        platform="shopee",
        item_key="lap1",
        name="Laptop Asus ROG",
        url="https://shopee.vn/laptop",
        price=2_000_000,
        baseline=20_000_000,
        baseline_type="list_price",
        discount=0.90,
        stage="confirming",
        admin_message_id=12345,
    )
    assert aid > 0

    anom = db.get_anomaly(aid)
    assert anom is not None
    assert anom["price"] == 2_000_000
    assert anom["baseline"] == 20_000_000
    assert anom["discount"] == 0.90
    assert anom["stage"] == "confirming"
    assert anom["admin_message_id"] == 12345

    # Check recent anomaly
    recent = db.get_recent_anomaly_for_product(pid, hours=1)
    assert recent is not None
    assert recent["id"] == aid

    # Update stage to confirmed
    db.update_anomaly_stage(aid, "confirmed")
    anom2 = db.get_anomaly(aid)
    assert anom2["stage"] == "confirmed"
    assert anom2["confirmed_at"] is not None

    # Update stage to rejected with reason
    db.update_anomaly_stage(aid, "rejected", reject_reason="price_fixed")
    anom3 = db.get_anomaly(aid)
    assert anom3["stage"] == "rejected"
    assert anom3["reject_reason"] == "price_fixed"

    # List anomalies
    anomalies = db.get_anomalies(limit=10)
    assert len(anomalies) >= 1


def test_upsert_variants_and_delta_tracking(db):
    from deal_hunter.models import VariantInfo

    pid = db.add_product_url("https://lazada.vn/products/f75-i123.html", "lazada", "123")
    v1 = VariantInfo(variant_key="sku_blue", name="F75 Glacier Blue", price=1623000.0, list_price=2000000.0, stock_state="in", stock_qty=5)
    v2 = VariantInfo(variant_key="sku_white", name="F75 White Snow", price=1153000.0, list_price=2000000.0, stock_state="out", stock_qty=0)

    # 1. Upsert with initial_sku_key="sku_blue"
    db.upsert_variants(pid, [v1, v2], initial_sku_key="sku_blue")

    variants = db.get_product_variants(pid)
    assert len(variants) == 2
    var_map = {v["variant_key"]: v for v in variants}
    assert var_map["sku_blue"]["price"] == 1623000.0
    assert var_map["sku_blue"]["stock_state"] == "in"
    assert var_map["sku_white"]["price"] == 1153000.0
    assert var_map["sku_white"]["stock_state"] == "out"

    # Product main_variant_id should be sku_blue
    prod = db.get_product(pid)
    assert prod["main_variant_id"] == var_map["sku_blue"]["id"]

    # Check variant_history row count
    hist_count_1 = db.conn.execute("SELECT count(*) FROM variant_history").fetchone()[0]
    assert hist_count_1 == 2

    # 2. Second upsert with IDENTICAL values: Delta tracking MUST NOT insert new rows
    db.upsert_variants(pid, [v1, v2])
    hist_count_2 = db.conn.execute("SELECT count(*) FROM variant_history").fetchone()[0]
    assert hist_count_2 == 2, "Delta tracking failed: identical values must not insert new history row"

    # 3. Third upsert with changed price for sku_blue: MUST insert exactly 1 new history row
    v1_changed = VariantInfo(variant_key="sku_blue", name="F75 Glacier Blue", price=1550000.0, list_price=2000000.0, stock_state="in", stock_qty=3)
    db.upsert_variants(pid, [v1_changed, v2])
    hist_count_3 = db.conn.execute("SELECT count(*) FROM variant_history").fetchone()[0]
    assert hist_count_3 == 3, "Delta tracking failed: changed price must insert exactly 1 new row"

    # Verify latest price
    updated_variants = db.get_product_variants(pid)
    up_map = {v["variant_key"]: v for v in updated_variants}
    assert up_map["sku_blue"]["price"] == 1550000.0


def test_main_variant_auto_assignment_and_override(db):
    from deal_hunter.models import VariantInfo

    pid = db.add_product_url("https://shopee.vn/keyboard-i.1.2", "shopee", "1.2")
    # sku1 is cheaper but out of stock, sku2 is in stock
    v1 = VariantInfo(variant_key="m1", name="Switch Red (Out)", price=500000.0, stock_state="out")
    v2 = VariantInfo(variant_key="m2", name="Switch Blue (In)", price=600000.0, stock_state="in")

    # Without initial_sku_key, lowest in-stock variant (v2) should be picked as main_variant
    db.upsert_variants(pid, [v1, v2])
    prod = db.get_product(pid)
    variants = db.get_product_variants(pid)
    v2_row = next(v for v in variants if v["variant_key"] == "m2")
    assert prod["main_variant_id"] == v2_row["id"]

    # Manual override via set_main_variant
    v1_row = next(v for v in variants if v["variant_key"] == "m1")
    db.set_main_variant(pid, v1_row["id"])
    prod_updated = db.get_product(pid)
    assert prod_updated["main_variant_id"] == v1_row["id"]


def test_variant_state_machine_flow(db):
    from deal_hunter.models import VariantInfo, Snapshot

    pid = db.add_product_url("https://shopee.vn/keyboard-i.10.20", "shopee", "10.20")
    v_main = VariantInfo(variant_key="k_red", name="Bàn phím F75 Switch Đỏ", price=500000.0, list_price=700000.0, stock_state="in", stock_qty=5)
    v_alt = VariantInfo(variant_key="k_blue", name="Bàn phím F75 Switch Xanh", price=550000.0, list_price=700000.0, stock_state="in", stock_qty=3)
    v_acc = VariantInfo(variant_key="k_acc", name="Cáp lò xo type C", price=45000.0, list_price=100000.0, stock_state="in", stock_qty=10)
    v_exp = VariantInfo(variant_key="k_gold", name="Bàn phím F75 Mạ Vàng", price=800000.0, list_price=900000.0, stock_state="in", stock_qty=1)

    snap = Snapshot(
        platform="shopee", item_key="10.20", url="https://shopee.vn/keyboard-i.10.20",
        name="Bàn phím cơ F75", shop="Shop A", price=500000.0, list_price=700000.0, stock=5,
        variants=[v_main, v_alt, v_acc, v_exp], sku_from_url="k_red"
    )
    db.save_snapshot(pid, snap)

    # Main variant initially in stock
    res = db.evaluate_variant_state(pid)
    assert res["action"] == "in_stock"

    # Step 1: Main variant goes out of stock -> First scan (NGHI HẾT)
    v_main_out = VariantInfo(variant_key="k_red", name="Bàn phím F75 Switch Đỏ", price=500000.0, list_price=700000.0, stock_state="out", stock_qty=0)
    db.upsert_variants(pid, [v_main_out, v_alt, v_acc, v_exp])
    res_step1 = db.evaluate_variant_state(pid)
    assert res_step1["action"] == "suspect_out"
    active_ev = db.get_active_fallback_event(pid)
    assert active_ev is not None
    assert active_ev["state"] == "suspect_out"

    # Step 2: Second scan confirms out of stock (HẾT HÀNG -> Fallback Variant Applied)
    res_step2 = db.evaluate_variant_state(pid)
    assert res_step2["action"] == "fallback_applied"
    assert res_step2["price"] == 550000.0
    active_ev2 = db.get_active_fallback_event(pid)
    assert active_ev2["state"] == "active"
    # k_blue (550k) selected: k_acc is accessory, k_gold (800k) exceeds 500k + 20% (600k)
    assert active_ev2["chosen_variant_id"] is not None

    # Step 3: Main variant restocked -> Resolved (HOÀN NGUYÊN)
    db.upsert_variants(pid, [v_main, v_alt, v_acc, v_exp])
    res_step3 = db.evaluate_variant_state(pid)
    assert res_step3["action"] == "resolved"
    assert res_step3["outcome"] == "main_restocked"
    assert db.get_active_fallback_event(pid) is None



