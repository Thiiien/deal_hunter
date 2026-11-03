"""Tests for Alerter, AffiliateLinker, QuotaMonitor, Web, and Bot."""
from unittest.mock import MagicMock, patch

from deal_hunter.affiliate import AffiliateLinker
from deal_hunter.alerter import Alerter
from deal_hunter.bot import create_bot, _parse_admin_id
from deal_hunter.config import Config
from deal_hunter.notifier import Notifier
from deal_hunter.quota import QuotaMonitor
from deal_hunter.web import create_app


# ── AffiliateLinker ──────────────────────────────────────────────────────────

def test_affiliate_linker():
    cfg = Config(aff_shopee="https://aff.link?to={url}&p=shopee", aff_lazada="https://laz.link?to={raw}")
    linker = AffiliateLinker(cfg)
    assert linker.build("shopee", "https://shopee.vn/p-1") == "https://aff.link?to=https%3A%2F%2Fshopee.vn%2Fp-1&p=shopee"
    assert linker.build("lazada", "https://lazada.vn/p-2") == "https://laz.link?to=https://lazada.vn/p-2"
    assert linker.build("unknown", "https://other.com/p-3") == "https://other.com/p-3"


# ── Alerter ──────────────────────────────────────────────────────────────────

def test_alerter_logic(db):
    alerter = Alerter(db)
    pid = 1

    # First alert should trigger
    assert alerter.should_alert(pid, 100_000) is True
    alerter.record(pid, 100_000)

    # Immediately after, same price -> False
    assert alerter.should_alert(pid, 100_000) is False

    # Small drop < 5% -> False
    assert alerter.should_alert(pid, 96_000) is False

    # Drop >= 5% (100k -> 94k is 6% drop) -> True
    assert alerter.should_alert(pid, 94_000) is True

    # After recording new price, 94k -> False
    alerter.record(pid, 94_000)
    assert alerter.should_alert(pid, 94_000) is False

    # Backdated alert in DB (>= 24h ago) -> True
    db.conn.execute("UPDATE alerts SET sent_at = datetime('now', '-25 hours') WHERE product_id = ?", (pid,))
    db.conn.commit()
    assert alerter.should_alert(pid, 94_000) is True


# ── QuotaMonitor ─────────────────────────────────────────────────────────────

def test_quota_monitor_no_key():
    cfg = Config(nopecha_api_key="")
    notifier = MagicMock()
    qm = QuotaMonitor(cfg, notifier)
    assert qm.check() is None
    assert qm.is_exhausted is False


def test_quota_monitor_free_tier(db):
    cfg = Config(nopecha_api_key="")
    notifier = MagicMock()
    qm = QuotaMonitor(cfg, notifier, db=db)
    assert qm.get_daily_solves() == 0
    assert qm.get_remaining_credits() == 10
    assert qm.is_exhausted is False

    qm.record_solve(5)
    assert qm.get_daily_solves() == 5
    assert qm.get_remaining_credits() == 5
    assert qm.is_exhausted is False

    qm.record_solve(5)
    assert qm.get_daily_solves() == 10
    assert qm.get_remaining_credits() == 0
    assert qm.is_exhausted is True
    # QuotaMonitor does not spam alert_admin; alerts are reserved for genuine crawler failures
    assert notifier.alert_admin.call_count == 0


@patch("deal_hunter.quota.httpx.get")
def test_quota_monitor_exhausted(mock_get):
    cfg = Config(nopecha_api_key="test-key")
    notifier = MagicMock()
    qm = QuotaMonitor(cfg, notifier)

    mock_get.return_value = MagicMock(json=lambda: {"data": {"credit": 0}})
    assert qm.check() == 0
    assert qm.is_exhausted is True
    notifier.alert_admin.assert_not_called()

    # Reset
    qm.reset()
    assert qm.is_exhausted is False


@patch("deal_hunter.quota.httpx.get")
def test_quota_monitor_warning_threshold(mock_get):
    cfg = Config(nopecha_api_key="test-key")
    notifier = MagicMock()
    qm = QuotaMonitor(cfg, notifier)

    mock_get.return_value = MagicMock(json=lambda: {"data": {"credit": 5}})
    assert qm.check() == 5
    assert qm.is_exhausted is False
    notifier.alert_admin.assert_not_called()



# ── Notifier ─────────────────────────────────────────────────────────────────

@patch("deal_hunter.notifier.httpx.post")
def test_notifier_calls(mock_post):
    cfg = Config(telegram_token="dummy-tok", admin_chat_id="111", telegram_channel_id="@channel")
    n = Notifier(cfg)
    n.alert_admin("Hello admin")
    mock_post.assert_called_once()
    assert mock_post.call_args[1]["json"]["chat_id"] == "111"

    n.broadcast_deal("Hello channel", reply_markup={"inline_keyboard": []})
    assert mock_post.call_count == 2
    assert mock_post.call_args[1]["json"]["chat_id"] == "@channel"


# ── Web App ──────────────────────────────────────────────────────────────────

def test_web_routes(config, db):
    scanner = MagicMock()
    app = create_app(config, db, scanner)
    client = app.test_client()

    # Dashboard page
    r = client.get("/")
    assert r.status_code == 200
    assert b"Deal Hunter" in r.data

    # Summary
    r = client.get("/api/summary")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_products"] == 0
    assert "shopee_count" in data
    assert "lazada_count" in data

    # Add product Shopee
    r = client.post("/api/products", json={"url": "https://shopee.vn/p-i.10.20"})
    assert r.status_code == 200
    pdata = r.get_json()
    assert pdata["id"] == 1
    assert pdata["platform"] == "shopee"

    # Add product Lazada
    r = client.post("/api/products", json={"url": "https://www.lazada.vn/products/tai-nghe-i123-s456.html"})
    assert r.status_code == 200
    pdata2 = r.get_json()
    assert pdata2["id"] == 2
    assert pdata2["platform"] == "lazada"

    # List products
    r = client.get("/api/products")
    assert r.status_code == 200
    prods = r.get_json()
    assert len(prods) == 2
    assert "top_category" in prods[0]
    assert "discount_percent" in prods[0]
    assert "is_deep_deal" in prods[0]

    # Product history
    r = client.get("/api/products/1/history")
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)

    # Search by keyword
    scanner.discover_keyword.return_value = [10, 11]
    r = client.post("/api/search", json={"keyword": "chuot logitech", "limit": 2, "platform": "lazada"})
    assert r.status_code == 200
    assert r.get_json()["added_count"] == 2
    assert r.get_json()["platform"] == "lazada"
    scanner.discover_keyword.assert_called_with("chuot logitech", limit=2, lowest_only=True, platform="lazada")

    # Scan trigger
    r = client.post("/api/scan")
    assert r.status_code == 200
    assert r.get_json()["status"] == "started"

    # Set target price
    r = client.patch("/api/products/1/target_price", json={"target_price": 50000})
    assert r.status_code == 200
    assert r.get_json()["target_price"] == 50000.0

    # Get settings
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "scan_interval_min" in r.get_json()
    assert "deal_min_original_price" in r.get_json()
    assert "only_target_price_alerts" in r.get_json()

    # Update settings
    r = client.post("/api/settings", json={"scan_interval_min": 15, "deal_min_original_price": 600000.0, "only_target_price_alerts": True})
    assert r.status_code == 200
    assert r.get_json()["scan_interval_min"] == 15
    assert r.get_json()["deal_min_original_price"] == 600000.0
    assert r.get_json()["only_target_price_alerts"] is True
    assert config.scan_interval_min == 15
    assert config.deal_min_original_price == 600000.0
    assert config.only_target_price_alerts is True
    assert db.get_setting("only_target_price_alerts") == "1"

    # Delete product
    r = client.delete("/api/products/1")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"
    assert len(db.get_active_products()) == 1

    r = client.delete("/api/products/2")
    assert r.status_code == 200
    assert len(db.get_active_products()) == 0

    # Bulk delete products
    p1 = db.add_product_url("https://shopee.vn/p-i.1.1", "shopee", "1.1")
    p2 = db.add_product_url("https://shopee.vn/p-i.2.2", "shopee", "2.2")
    assert len(db.get_active_products()) == 2
    r = client.post("/api/products/bulk-delete", json={"ids": [p1, p2]})
    assert r.status_code == 200
    assert r.get_json()["deleted_count"] == 2
    assert len(db.get_active_products()) == 0

    # Crawl megasale trigger
    r = client.post("/api/crawl-megasale", json={"limit": 10, "platform": "lazada"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "started"
    assert "Lazada" in r.get_json()["msg"]

    # Purge junk flash sale products
    from deal_hunter.models import Snapshot
    p_junk = db.add_product_url("https://shopee.vn/p-junk", "shopee", "j9", source="flash_sale")
    db.save_snapshot(p_junk, Snapshot(platform="shopee", item_key="j9", url="https://shopee.vn/p-junk", name="Junk", shop="S", price=40_000, list_price=80_000, stock=True))
    p_good = db.add_product_url("https://shopee.vn/p-good", "shopee", "g9", source="flash_sale")
    db.save_snapshot(p_good, Snapshot(platform="shopee", item_key="g9", url="https://shopee.vn/p-good", name="Good", shop="S", price=300_000, list_price=700_000, stock=True))

    r = client.post("/api/products/purge-junk", json={"min_price": 500000})
    assert r.status_code == 200
    assert r.get_json()["deleted_count"] == 1
    assert db.get_product(p_junk) is None
    assert db.get_product(p_good) is not None

    # Anomalies endpoints
    aid = db.create_anomaly(
        product_id=p_good,
        platform="shopee",
        item_key="g9",
        name="Good",
        url="https://shopee.vn/p-good",
        price=100_000,
        baseline=1_000_000,
        baseline_type="list_price",
        discount=0.90,
    )
    r = client.get("/api/anomalies")
    assert r.status_code == 200
    assert len(r.get_json()) >= 1

    r = client.post(f"/api/anomalies/{aid}/publish")
    assert r.status_code == 200
    assert r.get_json()["stage"] == "published"

    r = client.post(f"/api/anomalies/{aid}/dismiss")
    assert r.status_code == 200
    assert r.get_json()["stage"] == "rejected"

    r = client.post("/api/scan-price-errors")
    assert r.status_code == 200
    assert r.get_json()["status"] == "started"



# ── Bot ──────────────────────────────────────────────────────────────────────

def test_bot_admin_guard(config, db):
    cfg = Config(telegram_token="123456:fake_token", admin_chat_id="12345")
    scanner = MagicMock()
    notifier = MagicMock()
    quota = MagicMock()

    bot = create_bot(cfg, db, scanner, notifier, quota)
    bot.threaded = False
    assert _parse_admin_id("12345") == 12345
    assert _parse_admin_id("invalid") == 0

    # Create dummy message from unauthorized user
    fake_msg_unauth = MagicMock(content_type="text", text="/status")
    fake_msg_unauth.from_user.id = 99999

    # Create dummy message from admin
    fake_msg_admin = MagicMock(content_type="text", text="/status")
    fake_msg_admin.from_user.id = 12345

    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([fake_msg_unauth])
        mock_reply.assert_not_called()

        bot.process_new_messages([fake_msg_admin])
        mock_reply.assert_called_once()

    # Test /timkiem
    fake_msg_search = MagicMock(content_type="text", text="/timkiem ban phim")
    fake_msg_search.from_user.id = 12345
    scanner.discover_keyword.return_value = [1, 2]
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([fake_msg_search])
        assert mock_reply.call_count == 2

    # Test /theodoi instant scan
    fake_msg_theodoi = MagicMock(content_type="text", text="/theodoi https://s.lazada.vn/s.Abc")
    fake_msg_theodoi.from_user.id = 12345
    fake_msg_theodoi.chat.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        mock_wait = MagicMock()
        mock_wait.message_id = 777
        mock_reply.return_value = mock_wait
        with patch.object(bot, "edit_message_text") as mock_edit:
            bot.process_new_messages([fake_msg_theodoi])
            mock_reply.assert_called_once()
            assert "Đang quét" in mock_reply.call_args[0][1]


def test_bot_list_command(config, db):
    from deal_hunter.models import Snapshot

    cfg = Config(telegram_token="123456:fake_token", admin_chat_id="12345")
    scanner = MagicMock()
    notifier = MagicMock()
    quota = MagicMock()

    bot = create_bot(cfg, db, scanner, notifier, quota)
    bot.threaded = False

    fake_msg = MagicMock(content_type="text", text="/list")
    fake_msg.from_user.id = 12345
    fake_msg.chat.id = 12345

    # 1. Empty state
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([fake_msg])
        mock_reply.assert_called_once()
        assert "chưa theo dõi sản phẩm nào" in mock_reply.call_args[0][1]

    # 2. Add 6 tracked products (source='user') and 1 keyword product (source='keyword')
    for i in range(1, 7):
        pid = db.add_product_url(f"https://shopee.vn/p-{i}", "shopee", f"item_{i}", source="user")
        snap = Snapshot(
            platform="shopee",
            item_key=f"item_{i}",
            url=f"https://shopee.vn/p-{i}",
            name=f"Sản phẩm {i}",
            shop="Shop Test",
            price=100_000.0 * i,
            list_price=120_000.0 * i,
            stock=True,
            voucher_code="GIAM10K" if i == 1 else "",
            voucher_discount=10_000.0 if i == 1 else 0.0,
            final_price=90_000.0 if i == 1 else 100_000.0 * i,
        )
        db.update_product_from_snapshot(pid, snap)
        db.save_snapshot(pid, snap)

    # Add keyword product (should NOT be included in /list)
    kw_pid = db.add_product_url("https://shopee.vn/p-kw", "shopee", "item_kw", source="keyword")
    kw_snap = Snapshot(
        platform="shopee", item_key="item_kw", url="https://shopee.vn/p-kw",
        name="Keyword Item", shop="KW Shop", price=50_000, list_price=80_000, stock=True,
    )
    db.update_product_from_snapshot(kw_pid, kw_snap)
    db.save_snapshot(kw_pid, kw_snap)

    # 3. Call /list (Page 1): 6 items, page_size 5 -> 1 header + 5 product cards + 1 nav message = 7 messages
    with patch.object(bot, "send_message") as mock_send:
        bot.process_new_messages([fake_msg])
        assert mock_send.call_count == 7
        header_text = mock_send.call_args_list[0][0][1]
        assert "SẢN PHẨM THEO DÕI (1/2)" in header_text
        assert "Tổng: <b>6</b> sản phẩm" in header_text

        # Check product card 1 (item 6)
        card1_text = mock_send.call_args_list[1][0][1]
        card1_markup = mock_send.call_args_list[1][1]["reply_markup"]
        assert "Sản phẩm 6" in card1_text
        assert "#" in card1_text
        assert card1_markup is not None
        assert card1_markup.keyboard[0][0].text == "🎯 Đặt giá"
        assert card1_markup.keyboard[0][1].text == "🗑️ Xóa"

        # Check navigation message (last message)
        nav_text = mock_send.call_args_list[6][0][1]
        nav_markup = mock_send.call_args_list[6][1]["reply_markup"]
        assert "Điều hướng trang" in nav_text
        assert any(btn.callback_data == "listpage_2" for row in nav_markup.keyboard for btn in row)

    # 4. Call /list 2 (Page 2): 1 header + 1 product card + 1 nav message = 3 messages
    fake_msg_p2 = MagicMock(content_type="text", text="/list 2")
    fake_msg_p2.from_user.id = 12345
    fake_msg_p2.chat.id = 12345
    with patch.object(bot, "send_message") as mock_send:
        bot.process_new_messages([fake_msg_p2])
        assert mock_send.call_count == 3
        p2_header = mock_send.call_args_list[0][0][1]
        p2_card = mock_send.call_args_list[1][0][1]
        assert "SẢN PHẨM THEO DÕI (2/2)" in p2_header
        assert "Sản phẩm 1" in p2_card
        assert "Voucher: <code>GIAM10K</code>" in p2_card


def test_bot_setgia_and_xoa_commands(config, db):
    cfg = Config(telegram_token="123456:fake_token", admin_chat_id="12345")
    scanner = MagicMock()
    notifier = MagicMock()
    quota = MagicMock()

    bot = create_bot(cfg, db, scanner, notifier, quota)
    bot.threaded = False

    pid = db.add_product_url("https://shopee.vn/p-test", "shopee", "item_test", source="user")

    # 1. /setgia by ID
    msg_setgia = MagicMock(content_type="text", text=f"/setgia {pid} 850k")
    msg_setgia.from_user.id = 12345
    msg_setgia.chat.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_setgia])
        mock_reply.assert_called_once()
        assert "Đã đặt giá mong muốn" in mock_reply.call_args[0][1]
        assert "850,000₫" in mock_reply.call_args[0][1]
    p = db.get_product(pid)
    assert p["target_price"] == 850_000.0

    # 2. /xoa by URL
    msg_xoa = MagicMock(content_type="text", text="/xoa https://shopee.vn/p-test")
    msg_xoa.from_user.id = 12345
    msg_xoa.chat.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_xoa])
        mock_reply.assert_called_once()
        assert "Đã xóa sản phẩm" in mock_reply.call_args[0][1]
    assert db.get_product(pid) is None


def test_bot_theodoi_interactive_flow_and_help(config, db):
    from unittest.mock import MagicMock, patch

    cfg = Config(telegram_token="123456:fake_token", admin_chat_id="12345")
    scanner = MagicMock()
    notifier = MagicMock()
    quota = MagicMock()

    bot = create_bot(cfg, db, scanner, notifier, quota)
    bot.threaded = False

    # 1. /theodoi with no args shows 2 buttons
    msg_td_empty = MagicMock(content_type="text", text="/theodoi")
    msg_td_empty.from_user.id = 12345
    msg_td_empty.chat.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_td_empty])
        mock_reply.assert_called_once()
        text = mock_reply.call_args[0][1]
        markup = mock_reply.call_args[1]["reply_markup"]
        assert "Nhập Link Sản Phẩm" in markup.keyboard[0][0].text
        assert "Đặt Giá Mong Muốn" in markup.keyboard[1][0].text

    # 2. Callback td_link
    call_link = MagicMock()
    call_link.from_user.id = 12345
    call_link.message.chat.id = 12345
    call_link.data = "td_link"
    with patch.object(bot, "send_message") as mock_send:
        bot.process_new_callback_query([call_link])
        mock_send.assert_called_once()
        assert "gửi link sản phẩm" in mock_send.call_args[0][1]

    # 3. Plain URL message adds product
    msg_url = MagicMock(content_type="text", text="https://shopee.vn/p-interactive")
    msg_url.from_user.id = 12345
    msg_url.chat.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_url])
        mock_reply.assert_called_once()
        assert "Đang quét" in mock_reply.call_args[0][1]
    p = db.get_product_by_ref("https://shopee.vn/p-interactive")
    assert p is not None
    pid = p["id"]

    # 4. Callback td_price automatically targets the last added product
    call_price = MagicMock()
    call_price.from_user.id = 12345
    call_price.message.chat.id = 12345
    call_price.data = "td_price"
    with patch.object(bot, "send_message") as mock_send:
        bot.process_new_callback_query([call_price])
        mock_send.assert_called_once()
        assert f"#{pid}" in mock_send.call_args[0][1]

    # 5. Plain text price input sets target price
    msg_price = MagicMock(content_type="text", text="650k")
    msg_price.from_user.id = 12345
    msg_price.chat.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_price])
        mock_reply.assert_called_once()
        assert "Đã đặt giá mong muốn" in mock_reply.call_args[0][1]
        assert "650,000₫" in mock_reply.call_args[0][1]
    p_updated = db.get_product(pid)
    assert p_updated["target_price"] == 650_000.0

    # 6. Callback del_<pid> switches markup to in-place confirmation buttons
    call_del = MagicMock()
    call_del.from_user.id = 12345
    call_del.message.chat.id = 12345
    call_del.message.message_id = 999
    call_del.data = f"del_{pid}"
    with patch.object(bot, "edit_message_reply_markup") as mock_edit_markup:
        bot.process_new_callback_query([call_del])
        mock_edit_markup.assert_called_once()
        conf_markup = mock_edit_markup.call_args[1]["reply_markup"]
        assert conf_markup.keyboard[0][0].text == "⚠️ Xác nhận xóa"
        assert conf_markup.keyboard[0][1].text == "❌ Hủy"

    # 7. Callback cancel_del_<pid> restores original buttons
    call_cancel = MagicMock()
    call_cancel.from_user.id = 12345
    call_cancel.message.chat.id = 12345
    call_cancel.message.message_id = 999
    call_cancel.data = f"cancel_del_{pid}"
    with patch.object(bot, "edit_message_reply_markup") as mock_edit_markup:
        bot.process_new_callback_query([call_cancel])
        mock_edit_markup.assert_called_once()
        restored_markup = mock_edit_markup.call_args[1]["reply_markup"]
        assert restored_markup.keyboard[0][0].text == "🎯 Đặt giá"
        assert restored_markup.keyboard[0][1].text == "🗑️ Xóa"

    # 8. Callback confirmdel_<pid> deletes from database and edits message text
    call_confirm = MagicMock()
    call_confirm.from_user.id = 12345
    call_confirm.message.chat.id = 12345
    call_confirm.message.message_id = 999
    call_confirm.data = f"confirmdel_{pid}"
    with patch.object(bot, "edit_message_text") as mock_edit_text:
        bot.process_new_callback_query([call_confirm])
        mock_edit_text.assert_called_once()
        assert "Đã xóa sản phẩm" in mock_edit_text.call_args[0][0]
    assert db.get_product(pid) is None

    # 9. /help displays guide
    msg_help = MagicMock(content_type="text", text="/help")
    msg_help.from_user.id = 12345
    msg_help.chat.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_help])
        mock_reply.assert_called_once()
        assert "/theodoi" in mock_reply.call_args[0][1]
        assert "/setgia" in mock_reply.call_args[0][1]
        assert "/xoa" in mock_reply.call_args[0][1]
        assert "/list" in mock_reply.call_args[0][1]

    # 10. /menu displays quick dashboard buttons
    msg_menu = MagicMock(content_type="text", text="/menu")
    msg_menu.from_user.id = 12345
    msg_menu.chat.id = 12345
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_messages([msg_menu])
        mock_reply.assert_called_once()
        assert "BẢNG ĐIỀU KHIỂN NHANH" in mock_reply.call_args[0][1]
        markup = mock_reply.call_args[1]["reply_markup"]
        btn_texts = [btn.text for row in markup.keyboard for btn in row]
        assert "📦 Danh sách" in btn_texts
        assert "⚡ Quét ngay" in btn_texts

    # 11. Callback btn_status executes cmd_status
    call_btn = MagicMock()
    call_btn.from_user.id = 12345
    call_btn.message.chat.id = 12345
    call_btn.message.message_id = 1000
    call_btn.data = "btn_status"
    with patch.object(bot, "reply_to") as mock_reply:
        bot.process_new_callback_query([call_btn])
        mock_reply.assert_called_once()
        assert "Deal Hunter Status" in mock_reply.call_args[0][1]




