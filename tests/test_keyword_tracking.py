import json
import pytest
from deal_hunter.classifier import (
    is_vietnam_location,
    is_foreign_location,
    is_keyword_relevant,
    detect_services_from_text,
    classify_product,
)
from deal_hunter.config import Config
from deal_hunter.db import DB
from deal_hunter.models import Snapshot
from deal_hunter.scanner import Scanner
from deal_hunter.adapters.mock import MockAdapter
from deal_hunter.notifier import Notifier
from deal_hunter.quota import QuotaMonitor
from deal_hunter.web import create_app


def test_location_classifiers():
    # Test all Vietnam locations from user image
    vn_test_locs = [
        "Thành phố Hồ Chí Minh", "Hà Nội", "Hải Phòng", "Tây Ninh", "Đà Nẵng",
        "Thái Nguyên", "Ninh Bình", "Vĩnh Long", "Đắk Lắk", "Nghệ An",
        "Quảng Ninh", "Hưng Yên", "Đồng Tháp", "Khánh Hòa", "Phú Thọ",
        "Bắc Ninh", "An Giang", "Việt Nam"
    ]
    for loc in vn_test_locs:
        assert is_vietnam_location(loc) is True, f"Failed for {loc}"
        assert is_foreign_location(loc) is False, f"Should not be foreign: {loc}"

    # Test foreign locations from user image
    foreign_test_locs = ["China", "Hong Kong", "South Korea", "Nước ngoài"]
    for loc in foreign_test_locs:
        assert is_foreign_location(loc) is True, f"Failed for {loc}"
        assert is_vietnam_location(loc) is False, f"Should not be VN: {loc}"


def test_keyword_relevance():
    assert is_keyword_relevant("chuột logitech g102", "Chuột chơi game Logitech G102 Lightsync RGB") is True
    assert is_keyword_relevant("chuột logitech", "Bàn phím cơ DareU EK87") is False


def test_detect_services():
    text = "Sản phẩm được áp dụng Freeship Extra, LazFlash giảm sâu và Voucher Max tích lũy"
    services = detect_services_from_text(text)
    assert "freeship" in services
    assert "lazflash" in services
    assert "voucher_max" in services


def test_classify_product():
    snap_vn = Snapshot(
        platform="lazada",
        item_key="12345",
        url="https://www.lazada.vn/products/pdp-i12345.html",
        name="Chuột Logitech G102 Lightsync",
        shop="Logitech Official Store",
        price=350000.0,
        list_price=450000.0,
        stock=True,
        origin="Việt Nam",
        ships_from="Hà Nội",
        shop_country="Việt Nam",
        services="freeship,lazmall",
    )

    snap_foreign = Snapshot(
        platform="shopee",
        item_key="99999",
        url="https://shopee.vn/p-i.9.9",
        name="Chuột Logitech G102 Lightsync",
        shop="Global Store",
        price=320000.0,
        list_price=420000.0,
        stock=True,
        origin="China",
        ships_from="China",
        shop_country="China",
    )

    # 1. Option 'vn': accepts VN, rejects foreign
    filters_vn = {
        "keyword": "chuột logitech",
        "origin_filter": "default",
        "ship_filter": "vn",
        "shop_filter": "any",
    }
    m, v, _ = classify_product(snap_vn, filters_vn)
    assert m is True and v == 1
    m, v, r = classify_product(snap_foreign, filters_vn)
    assert m is False and "Vận chuyển từ nước ngoài" in r

    # 2. Option 'foreign': accepts foreign, rejects VN
    filters_foreign = {
        "keyword": "chuột logitech",
        "origin_filter": "default",
        "ship_filter": "foreign",
        "shop_filter": "any",
    }
    m, v, _ = classify_product(snap_foreign, filters_foreign)
    assert m is True and v == 1
    m, v, r = classify_product(snap_vn, filters_foreign)
    assert m is False and "Vận chuyển từ Việt Nam" in r

    # 3. Option 'default': accepts both!
    filters_default = {
        "keyword": "chuột logitech",
        "origin_filter": "default",
        "ship_filter": "default",
        "shop_filter": "any",
    }
    m1, v1, _ = classify_product(snap_vn, filters_default)
    assert m1 is True and v1 == 1
    m2, v2, _ = classify_product(snap_foreign, filters_default)
    assert m2 is True and v2 == 1

    # 4. Fallback when ships_from is empty
    snap_fallback_vn = Snapshot(
        platform="lazada",
        item_key="777",
        url="https://www.lazada.vn/products/pdp-i777.html",
        name="Bàn phím cơ aula s98",
        shop="AULA Vietnam Store",
        price=500000.0,
        list_price=700000.0,
        stock=True,
        shop_country="Việt Nam",
        ships_from="",
    )
    m_fb_vn, _, _ = classify_product(snap_fallback_vn, {"keyword": "bàn phím cơ aula", "ship_filter": "vn"})
    assert m_fb_vn is True

    snap_fallback_foreign = Snapshot(
        platform="lazada",
        item_key="888",
        url="https://www.lazada.vn/products/pdp-i888.html",
        name="Bàn phím cơ aula s98",
        shop="AULA jingling Specialty Store - Cửa hàng nước ngoài",
        price=500000.0,
        list_price=700000.0,
        stock=True,
        shop_country="",
        ships_from="",
    )
    m_fb_fg, _, r_fg = classify_product(snap_fallback_foreign, {"keyword": "bàn phím cơ aula", "ship_filter": "vn"})
    assert m_fb_fg is False
    assert "Shop tại nước ngoài" in r_fg


def test_db_keywords_and_rejection_cache(tmp_path):
    db_file = tmp_path / "test_keywords.db"
    db = DB(str(db_file))

    # Add keyword
    filters = {"origin_filter": "vn", "ship_filter": "vn", "services": ["freeship"]}
    kid = db.add_or_update_keyword("chuột logitech", filters)
    assert kid > 0

    kws = db.get_keywords()
    assert len(kws) == 1
    assert kws[0]["keyword"] == "chuột logitech"

    # Toggle active
    db.set_keyword_active(kid, False)
    assert len(db.get_keywords(active_only=True)) == 0
    db.set_keyword_active(kid, True)
    assert len(db.get_keywords(active_only=True)) == 1

    # Rejection cache
    assert db.is_item_rejected("shopee", "item_123", kid) is False
    db.record_rejected_item("shopee", "item_123", kid, reason="Xuất xứ không đạt")
    assert db.is_item_rejected("shopee", "item_123", kid) is True

    # Clear cache
    db.clear_rejected_items(kid)
    assert db.is_item_rejected("shopee", "item_123", kid) is False

    # Upsert product meta & link to keyword
    snap = Snapshot(
        platform="lazada",
        item_key="lzd_999",
        url="https://www.lazada.vn/products/item-i999.html",
        name="Bàn phím cơ Akko",
        shop="Akko Store",
        price=800000.0,
        list_price=1000000.0,
        stock=True,
        origin="Việt Nam",
        ships_from="Hồ Chí Minh",
        services="lazmall,freeship",
        verified=1,
    )
    pid = db.upsert_product_meta(snap)
    db.save_snapshot(pid, snap, campaign="keyword")
    db.link_keyword_product(kid, pid, verified=1)

    matched = db.get_keyword_products(kid)
    assert len(matched) == 1
    assert matched[0]["name"] == "Bàn phím cơ Akko"
    assert matched[0]["ships_from"] == "Hồ Chí Minh"
    assert matched[0]["match_verified"] == 1


def test_scanner_keyword_search(tmp_path):
    db_file = tmp_path / "scanner_kw.db"
    db = DB(str(db_file))
    config = Config(db_path=str(db_file), fetch_mode="mock", keyword_result_limit=2)
    adapter = MockAdapter()
    notifier = Notifier(config)
    quota = QuotaMonitor(config, notifier)
    scanner = Scanner(config, adapter, db, notifier, quota)

    kid = db.add_or_update_keyword("mock product", {
        "origin_filter": "any",
        "ship_filter": "any",
        "shop_filter": "any",
        "services": [],
        "max_results": 2,
    })

    summary = scanner.run_keyword_search(kid)
    assert summary["keywords_count"] == 1
    assert summary["scanned"] >= 1

    kw_item = db.get_keyword(kid)
    assert kw_item["last_run"] is not None


def test_web_keyword_apis(tmp_path):
    db_file = tmp_path / "web_kw.db"
    db = DB(str(db_file))
    config = Config(db_path=str(db_file), fetch_mode="mock")
    adapter = MockAdapter()
    notifier = Notifier(config)
    quota = QuotaMonitor(config, notifier)
    scanner = Scanner(config, adapter, db, notifier, quota)
    app = create_app(config, db, scanner)
    client = app.test_client()

    # 1. Add keyword
    res = client.post("/api/keywords", json={
        "keyword": "tai nghe sony",
        "origin_filter": "vn",
        "ship_filter": "vn",
    })
    assert res.status_code == 200
    data = res.get_json()
    kid = data["id"]
    assert kid > 0

    # 2. Get keywords
    res = client.get("/api/keywords")
    assert res.status_code == 200
    kws = res.get_json()
    assert len(kws) == 1
    assert kws[0]["keyword"] == "tai nghe sony"

    # 3. Toggle keyword
    res = client.post(f"/api/keywords/{kid}/toggle", json={"active": False})
    assert res.status_code == 200

    # 4. Clear cache
    res = client.post(f"/api/keywords/{kid}/clear-cache")
    assert res.status_code == 200

    # 5. Get keyword products (initially empty)
    res = client.get("/api/keyword-products")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)

    # 6. Delete keyword
    res = client.delete(f"/api/keywords/{kid}")
    assert res.status_code == 200
    res = client.get("/api/keywords")
    assert len(res.get_json()) == 0


def test_bot_keyword_commands(tmp_path):
    from unittest.mock import MagicMock, patch
    from deal_hunter.bot import create_bot

    db_file = tmp_path / "bot_kw.db"
    db = DB(str(db_file))
    cfg = Config(telegram_token="123456:fake_token", admin_chat_id="12345")
    scanner = MagicMock()
    notifier = MagicMock()
    quota = MagicMock()

    bot = create_bot(cfg, db, scanner, notifier, quota)
    bot.threaded = False

    # Test /tukhoa
    msg_kw = MagicMock(content_type="text", text="/tukhoa chuột logitech g102")
    msg_kw.from_user.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_kw])
        assert mock_reply.call_count == 1
        assert "Đã lưu từ khóa theo dõi" in mock_reply.call_args[0][1]

    # Check keyword was added to DB
    kws = db.get_keywords()
    assert len(kws) == 1
    assert kws[0]["keyword"] == "chuột logitech g102"

    # Test /dstukhoa
    msg_list = MagicMock(content_type="text", text="/dstukhoa")
    msg_list.from_user.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_list])
        assert mock_reply.call_count == 1
        assert "DANH SÁCH TỪ KHÓA" in mock_reply.call_args[0][1]
        assert "chuột logitech g102" in mock_reply.call_args[0][1]

