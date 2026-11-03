"""Interactive and automated login utility to capture and persist session cookies for Deal Hunter."""
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("deal_hunter.login")

PLATFORMS = {
    "shopee": {
        "name": "Shopee",
        "login_url": "https://shopee.vn/buyer/login",
        "domain": ".shopee.vn",
    },
    "lazada": {
        "name": "Lazada",
        "login_url": "https://member.lazada.vn/user/login",
        "domain": ".lazada.vn",
    },
}

AUTH_COOKIE_NAMES = {"SPC_EC", "SPC_U", "SPC_ST", "shopee_token", "lzd_sid", "user_credentials"}


def has_display() -> bool:
    """Return True if a GUI desktop display is available to open browser windows."""
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def check_session_valid(data_dir: str = "data", platform: str = "shopee") -> bool:
    """Check if saved cookies exist and contain valid session tokens."""
    fname = "cookies_lazada.json" if platform == "lazada" else "cookies.json"
    cookie_file = Path(data_dir) / fname
    if not cookie_file.exists():
        return False
    try:
        data = json.loads(cookie_file.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not data:
            return False
        names = {c.get("name") for c in data if isinstance(c, dict)}
        if platform == "lazada":
            lazada_auth = {"lzd_sid", "t", "x5sec", "user_credentials", "cna", "_tb_token_"}
            return bool(names & lazada_auth) or len(names) >= 3
        # Shopee requires SPC_EC for real authenticated API access
        return "SPC_EC" in names or bool(names & (AUTH_COOKIE_NAMES - {"SPC_U"}))
    except Exception:
        return False


def is_logged_in(cookies: list[dict], current_url: str = "") -> bool:
    """Return True only if genuine session authentication tokens are present."""
    names = {c.get("name") for c in cookies if isinstance(c, dict)}
    if "lazada" in current_url.lower() or any(".lazada." in str(c.get("domain", "")) for c in cookies):
        lazada_auth = {"lzd_sid", "t", "x5sec", "user_credentials", "cna", "_tb_token_"}
        return bool(names & lazada_auth) or len(names) >= 3
    # For Shopee, SPC_EC or SPC_ST is the mandatory auth token (SPC_U is just user ID)
    if "shopee" in current_url.lower() or any(".shopee." in str(c.get("domain", "")) for c in cookies):
        return "SPC_EC" in names or "SPC_ST" in names
    return bool(names & AUTH_COOKIE_NAMES)


def interactive_login(
    platform_name: str = "shopee",
    data_dir: str = "data",
    timeout_sec: int = 180,
) -> bool:
    """Open headful browser for login, auto-detect when done, and save cookies."""
    target = PLATFORMS.get(platform_name.lower())
    if not target:
        log.error("Sàn không được hỗ trợ: %s", platform_name)
        return False

    out_dir = Path(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cookie_file = out_dir / "cookies.json"
    state_file = out_dir / "storage_state.json"

    print("=" * 64)
    print(f"🔑 DEAL HUNTER — TỰ ĐỘNG ĐĂNG NHẬP SÀN {target['name'].upper()}")
    print("=" * 64)
    print(f"Đang mở trình duyệt Chrome tới: {target['login_url']}")
    print("👉 Hãy quét mã QR trên điện thoại hoặc nhập tài khoản/mật khẩu + OTP.")
    print("👉 Sau khi bạn đăng nhập thành công, hệ thống sẽ TỰ ĐỘNG nhận diện,")
    print("   lưu cookies và TỰ ĐỘNG đóng trình duyệt mà không cần bấm phím nào!")
    print(f"⏳ Thời gian chờ tối đa: {timeout_sec} giây...")
    print("=" * 64)

    with sync_playwright() as pw:
        browser = None
        for channel in ("chrome", "msedge", None):
            try:
                browser = pw.chromium.launch(
                    headless=False,
                    channel=channel,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                break
            except Exception:
                continue

        if not browser:
            log.error("Không thể khởi động trình duyệt có giao diện.")
            return False

        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="vi-VN",
        )
        page = ctx.new_page()
        try:
            page.goto(target["login_url"])
        except Exception as exc:
            log.warning("Không thể mở trang đăng nhập: %s", exc)
            ctx.close()
            browser.close()
            return False

        start_time = time.time()
        logged_in = False
        while time.time() - start_time < timeout_sec:
            try:
                if page.is_closed():
                    break
                cur_url = page.url
                cookies = ctx.cookies()
                if is_logged_in(cookies, cur_url):
                    # Settle for 1.5s to ensure complete session tokens
                    page.wait_for_timeout(1500)
                    cookies = ctx.cookies()
                    cookie_file.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")
                    ctx.storage_state(path=str(state_file))
                    print(f"\n🎉 ĐÃ TỰ ĐỘNG NHẬN DIỆN ĐĂNG NHẬP THÀNH CÔNG! ĐÃ LƯU {len(cookies)} COOKIES.")
                    print(f"📁 Cookies đã lưu vào: {cookie_file}")
                    logged_in = True
                    break
                page.wait_for_timeout(1000)
            except Exception:
                break

        if not logged_in:
            try:
                cookies = ctx.cookies()
                if is_logged_in(cookies):
                    cookie_file.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")
                    ctx.storage_state(path=str(state_file))
                    print(f"\n🎉 ĐÃ LƯU {len(cookies)} COOKIES XÁC THỰC THÀNH CÔNG.")
                    print(f"📁 Cookies đã lưu vào: {cookie_file}")
                    logged_in = True
            except Exception:
                pass

        try:
            ctx.close()
            browser.close()
        except Exception:
            pass

    if not logged_in:
        print("\n⚠️ Đăng nhập chưa hoàn tất (chưa tìm thấy token SPC_EC / SPC_U) hoặc cửa sổ đã bị đóng.")
    return logged_in


def import_cookies(source_file: str, data_dir: str = "data") -> Path:
    src = Path(source_file)
    if not src.exists():
        print(f"❌ Không tìm thấy file: {source_file}")
        sys.exit(1)

    out_dir = Path(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "cookies.json"

    raw = src.read_text(encoding="utf-8")
    data = json.loads(raw)
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Đã import cookies từ {src} -> {dest}")
    return dest


def main():
    parser = argparse.ArgumentParser(description="Đăng nhập tài khoản sàn TMĐT và lưu cookies cho Deal Hunter")
    parser.add_argument("platform", nargs="?", default="shopee", help="Tên sàn (shopee / lazada). Mặc định: shopee")
    parser.add_argument("--import-file", "-i", help="Đường dẫn file JSON cookies có sẵn để import")
    parser.add_argument("--data-dir", "-d", default="data", help="Thư mục lưu trữ cookies (mặc định: data)")
    parser.add_argument("--timeout", "-t", type=int, default=180, help="Thời gian chờ tối đa (giây). Mặc định: 180")
    args = parser.parse_args()

    if args.import_file:
        import_cookies(args.import_file, data_dir=args.data_dir)
    else:
        success = interactive_login(platform_name=args.platform, data_dir=args.data_dir, timeout_sec=args.timeout)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
