"""Unit tests for login utilities, session validation, and pre-flight checks."""
import json
from unittest.mock import MagicMock

from deal_hunter.login import check_session_valid, has_display, is_logged_in
from deal_hunter.notifier import Notifier
from deal_hunter.quota import QuotaMonitor
from deal_hunter.scanner import Scanner


def test_has_display():
    # Should return a boolean
    assert isinstance(has_display(), bool)


def test_check_session_valid_no_file(tmp_path):
    assert check_session_valid(str(tmp_path)) is False


def test_check_session_valid_empty_file(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text("[]", encoding="utf-8")
    assert check_session_valid(str(tmp_path)) is False


def test_check_session_valid_with_auth_cookie(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookies = [
        {"name": "SPC_EC", "value": "secret123", "domain": ".shopee.vn"},
        {"name": "_ga", "value": "ga123", "domain": ".shopee.vn"},
    ]
    cookie_file.write_text(json.dumps(cookies), encoding="utf-8")
    assert check_session_valid(str(tmp_path)) is True


def test_is_logged_in_detects_auth_cookie():
    cookies = [{"name": "SPC_EC", "value": "val"}]
    assert is_logged_in(cookies, "https://shopee.vn/buyer/login") is True
    cookies_st = [{"name": "SPC_ST", "value": "val"}]
    assert is_logged_in(cookies_st, "https://shopee.vn/buyer/login") is True


def test_is_logged_in_rejects_guest_cookies():
    # Regular guest cookies without auth tokens should NOT be considered logged in
    cookies = [{"name": f"cookie_{i}", "value": "val"} for i in range(18)]
    assert is_logged_in(cookies, "https://shopee.vn/") is False


def test_scanner_preflight_check_blocks_when_unauthenticated(config, db):
    adapter = MagicMock()
    adapter.ensure_authenticated.return_value = False
    notifier = MagicMock(spec=Notifier)
    quota = MagicMock(spec=QuotaMonitor)
    quota.is_exhausted = False
    quota.check.return_value = 50

    scanner = Scanner(config, adapter, db, notifier, quota)
    result = scanner.scan_all()
    assert result["msg"] == "auth_required"
    notifier.alert_admin.assert_called_once()


def test_check_session_valid_lazada(tmp_path):
    cookie_file = tmp_path / "cookies_lazada.json"
    assert check_session_valid(str(tmp_path), platform="lazada") is False
    cookies = [
        {"name": "lzd_sid", "value": "sid123", "domain": ".lazada.vn"},
        {"name": "t", "value": "t123", "domain": ".lazada.vn"},
    ]
    cookie_file.write_text(json.dumps(cookies), encoding="utf-8")
    assert check_session_valid(str(tmp_path), platform="lazada") is True


def test_scanner_platform_isolated_auth(config, db):
    """If Shopee is valid but Lazada cookie is expired, Lazada fails isolated while Shopee proceeds."""
    from deal_hunter.models import Snapshot
    db.add_product_url("https://shopee.vn/p-i.1.2", "shopee", "1.2")
    db.add_product_url("https://www.lazada.vn/products/p-i3.html", "lazada", "3")

    adapter = MagicMock()
    # Overall check passes
    adapter.ensure_authenticated.side_effect = lambda platform="all": True if platform in ("all", "shopee") else False
    adapter.fetch.return_value = Snapshot(
        platform="shopee", item_key="1.2", url="https://shopee.vn/p-i.1.2",
        name="Shopee Product", shop="Shop Official", price=100000, list_price=120000, stock=True,
    )
    notifier = MagicMock(spec=Notifier)
    quota = MagicMock(spec=QuotaMonitor)
    quota.is_exhausted = False
    quota.check.return_value = 50

    scanner = Scanner(config, adapter, db, notifier, quota)
    res = scanner.scan_all()
    # 1 Shopee ok, 1 Lazada failed due to isolated auth check
    assert res["ok"] == 1
    assert res["fail"] == 1
    # Alert sent specifically for Lazada
    notifier.alert_admin.assert_called_once()
    assert "Lazada" in notifier.alert_admin.call_args[0][0]
    assert "cookies_lazada.json" in notifier.alert_admin.call_args[0][0]
    # same missing cookie on the next cycle: logged, not re-sent (6h cooldown)
    scanner.scan_all()
    notifier.alert_admin.assert_called_once()


def test_interactive_login_writes_platform_cookie_file(tmp_path, monkeypatch):
    """Lazada login must land in cookies_lazada.json, the file check_session_valid reads."""
    import json
    from unittest.mock import MagicMock
    from deal_hunter import login as login_mod
    cookies = [{"name": "lzd_sid", "domain": ".lazada.vn"}, {"name": "t", "domain": ".lazada.vn"}, {"name": "cna", "domain": ".lazada.vn"}]
    page = MagicMock(); page.is_closed.return_value = False; page.url = "https://www.lazada.vn/"
    ctx = MagicMock(); ctx.cookies.return_value = cookies; ctx.new_page.return_value = page
    browser = MagicMock(); browser.new_context.return_value = ctx
    pw = MagicMock(); pw.chromium.launch.return_value = browser
    cm = MagicMock(); cm.__enter__ = lambda s: pw; cm.__exit__ = lambda s, *a: False
    monkeypatch.setattr(login_mod, "sync_playwright", lambda: cm)
    assert login_mod.interactive_login("lazada", data_dir=str(tmp_path), timeout_sec=5)
    assert json.loads((tmp_path / "cookies_lazada.json").read_text(encoding="utf-8")) == cookies
    assert login_mod.check_session_valid(str(tmp_path), "lazada")

