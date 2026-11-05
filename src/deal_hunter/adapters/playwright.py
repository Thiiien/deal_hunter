"""
playwright.py — Shopee crawler using Playwright Persistent Context + NopeCHA extension.

This adapter is imported lazily (only when FETCH_MODE=playwright) to avoid
loading Playwright when running with mock or feed modes.
"""
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
from pathlib import Path
import re
import urllib.parse

from .base import BaseAdapter, Blocked, FetchError, ProductDelisted
from ..classifier import is_tmall_electronics
from ..models import Snapshot, VariantInfo

log = logging.getLogger(__name__)


try:
    from playwright_stealth import Stealth
    _STEALTH = Stealth()
except ImportError:
    _STEALTH = None


STEALTH_JS = """
try {
    delete Object.getPrototypeOf(navigator).webdriver;
} catch (e) {}
if (!window.chrome) {
    window.chrome = {};
}
if (!window.chrome.runtime) {
    window.chrome.runtime = {};
}
Object.defineProperty(navigator, 'languages', {
    get: () => ['vi-VN', 'vi', 'en-US', 'en'],
});
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        origQuery(parameters)
);
"""


def _setup_page(page):
    """Apply stealth evasions and abort only heavy external trackers."""
    if _STEALTH:
        try:
            _STEALTH.apply_stealth_sync(page)
        except Exception:
            pass

    def _route_filter(route):
        req = route.request
        # Do NOT abort Shopee's own images/fonts because that triggers anti-bot crawler checks
        if any(d in req.url for d in (
            "google-analytics.com", "googletagmanager.com", "facebook.net",
            "criteo.com", "criteo.net", "doubleclick.net", "tiktok.com",
            "branch.io", "adjust.com", "hotjar.com", "clarity.ms"
        )):
            route.abort()
        else:
            route.continue_()

    try:
        page.route("**/*", _route_filter)
    except Exception:
        pass



def _ensure_nopecha_extension(ext_dir: Path) -> bool:
    """Ensure NopeCHA Chromium extension is unpacked and ready."""
    if (ext_dir / "manifest.json").exists():
        return True
    ext_dir.mkdir(parents=True, exist_ok=True)
    zip_url = "https://github.com/NopeCHALLC/nopecha-extension/releases/download/0.6.1/chromium.zip"
    zip_path = ext_dir.parent / "nopecha_v0.6.1.zip"
    try:
        import urllib.request
        import zipfile
        log.info("Downloading NopeCHA extension v0.6.1 from %s...", zip_url)
        urllib.request.urlretrieve(zip_url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(ext_dir)
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
        if (ext_dir / "manifest.json").exists():
            log.info("NopeCHA extension unpacked to %s", ext_dir)
            return True
        log.warning("manifest.json not found in unpacked NopeCHA extension at %s", ext_dir)
        return False
    except Exception as exc:
        log.warning("Failed to auto-download NopeCHA extension: %s", exc)
        return False


class PlaywrightAdapter(BaseAdapter):
    """Fetches Shopee product pages via a persistent Chromium session.

    All Playwright operations run on a dedicated single-threaded executor
    to prevent Playwright greenlet thread-switching errors across Flask,
    Telegram bot, and Scheduler threads.
    """

    def __init__(self, config):
        self._config = config
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pw-worker")
        self._pw = None
        self._ctx = None   # persistent browser context
        self._cdp_browser = None
        self._using_cdp = False
        self._item_locations: dict[str, str] = {}
        self._quota = None
        self._cookie_mtime: dict[str, float] = {}  # ADR 0067: cookie file state we loaded or wrote

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def _ensure_started(self):
        if self._ctx is not None:
            return
        from playwright.sync_api import sync_playwright  # lazy import

        profile_dir = Path(self._config.db_path).parent / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        cdp_url = getattr(self._config, "cdp_url", "") or os.getenv("CDP_URL", "")
        if cdp_url:
            candidates = []
            parsed = urllib.parse.urlparse(cdp_url)
            hostname = parsed.hostname or ""
            # If hostname is not an IP, resolve to IP first to avoid Chrome DevTools 500 error
            if hostname and hostname not in ("localhost", "127.0.0.1"):
                try:
                    import socket
                    resolved_ip = socket.gethostbyname(hostname)
                    port_str = f":{parsed.port}" if parsed.port else ""
                    candidates.append(f"{parsed.scheme}://{resolved_ip}{port_str}")
                except Exception:
                    pass
            candidates.append(cdp_url)
            if "host.docker.internal" in cdp_url:
                candidates.append(cdp_url.replace("host.docker.internal", "127.0.0.1"))
            for target_url in candidates:
                try:
                    if not self._pw:
                        self._pw = sync_playwright().start()
                    self._cdp_browser = self._pw.chromium.connect_over_cdp(target_url, timeout=3000)
                    if self._cdp_browser.contexts:
                        self._ctx = self._cdp_browser.contexts[0]
                    else:
                        self._ctx = self._cdp_browser.new_context(
                            viewport={"width": 1366, "height": 768},
                            locale="vi-VN",
                        )
                    self._using_cdp = True
                    log.info("🚀 Đã kết nối thành công tới Chrome thật qua CDP: %s", target_url)
                    self._load_saved_cookies(profile_dir.parent)
                    return
                except Exception as e:
                    log.debug("CDP connection failed for %s: %s", target_url, e)
            log.warning("⚠️ Không thể kết nối tới Chrome CDP tại %s. Tự động chuyển sang trình duyệt nội bộ.", cdp_url)
            self._using_cdp = False
            if hasattr(self, "_cdp_browser") and self._cdp_browser:
                try:
                    self._cdp_browser.close()
                except Exception:
                    pass
                self._cdp_browser = None
            if self._pw:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None

        for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            try:
                (profile_dir / lock).unlink(missing_ok=True)
            except OSError:
                pass
        ext_dir = Path(self._config.extensions_dir) / "nopecha"
        _ensure_nopecha_extension(ext_dir)

        args = [
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ]
        if (ext_dir / "manifest.json").exists():
            args.extend([
                f"--disable-extensions-except={ext_dir}",
                f"--load-extension={ext_dir}",
            ])

        from ..login import has_display
        use_gui = has_display()
        if use_gui and "--headless=new" not in args:
            args.insert(0, "--headless=new")

        if not self._pw:
            self._pw = sync_playwright().start()
        # In Docker / Linux without display, channel must be None and headless must be True
        channels = ("chrome", "msedge", None) if use_gui else (None,)
        for channel in channels:
            try:
                self._ctx = self._pw.chromium.launch_persistent_context(
                    str(profile_dir),
                    channel=channel,
                    headless=not use_gui,
                    args=args,
                    ignore_default_args=["--enable-automation"],
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768},
                    locale="vi-VN",
                )
                break
            except Exception:
                continue

        if not self._ctx:
            raise RuntimeError("Không thể khởi động trình duyệt Playwright.")

        self._ctx.add_init_script(STEALTH_JS)
        self._load_saved_cookies(profile_dir.parent)
        log.info("Playwright browser started (profile: %s)", profile_dir)

    def _load_saved_cookies(self, data_dir: Path):
        if not self._ctx:
            return
        for fname in ("cookies.json", "cookies_lazada.json"):
            cookie_file = data_dir / fname
            if not cookie_file.exists():
                continue
            try:
                mtime = cookie_file.stat().st_mtime
                if self._cookie_mtime.get(fname) == mtime:
                    continue  # unchanged since we loaded or wrote it: the live jar is at least as fresh
                cookies = json.loads(cookie_file.read_text(encoding="utf-8"))
                if isinstance(cookies, list) and cookies:
                    self._ctx.add_cookies(cookies)
                    self._cookie_mtime[fname] = mtime
                    log.info("Đã nạp %d cookies từ %s", len(cookies), cookie_file)
            except Exception as exc:
                log.warning("Không thể nạp cookies từ %s: %s", cookie_file, exc)

    def _persist_cookies(self, platform: str, data_dir: Path | None = None):
        """ADR 0067: write the live jar back so rotated tokens survive a restart; never overwrite a fresh login."""
        fname = "cookies_lazada.json" if platform == "lazada" else "cookies.json"
        path = (data_dir or Path(self._config.db_path).parent) / fname
        try:
            if path.exists() and path.stat().st_mtime != self._cookie_mtime.get(fname):
                return  # written by a re-login we have not loaded yet
            cookies = [c for c in self._ctx.cookies() if platform in str(c.get("domain", ""))]
            if not cookies:
                return
            path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")
            self._cookie_mtime[fname] = path.stat().st_mtime
        except Exception as exc:
            log.debug("Could not persist %s cookies: %s", platform, exc)

    def reload_cookies(self, data_dir: Path | None = None, timeout: float = 5.0):
        """Thread-safe method to reload saved cookies into the browser context."""
        if not self._ctx:
            return
        p = data_dir or Path(self._config.db_path).parent
        if "pw-worker" in (threading.current_thread().name or ""):
            return self._load_saved_cookies(p)
        if self._executor:
            try:
                return self._executor.submit(self._load_saved_cookies, p).result(timeout=timeout)
            except TimeoutError:
                log.warning("Playwright worker busy; cookie reload queued in background")
                return
            except Exception as exc:
                log.warning("Không thể nạp cookies vào trình duyệt: %s", exc)
                return
        return self._load_saved_cookies(p)

    def ensure_authenticated(self, platform: str = "all") -> bool:
        """Verify saved session for platform(s). Interactive login is only started from the dashboard or `login`."""
        from ..login import check_session_valid
        data_dir = str(Path(self._config.db_path).parent)

        if platform == "all":
            return check_session_valid(data_dir, "shopee") or check_session_valid(data_dir, "lazada")

        if check_session_valid(data_dir, platform=platform):
            return True
        log.warning("Chưa có cookies phiên đăng nhập hợp lệ cho %s.", platform)
        return False




    def close(self):
        try:
            self._executor.submit(self._close_sync).result(timeout=10)
        except Exception:
            pass

    def _close_sync(self):
        if hasattr(self, "_using_cdp") and self._using_cdp:
            # Do NOT call self._cdp_browser.close() as it terminates the user's running Chrome!
            if self._pw:
                try:
                    self._pw.stop()
                except Exception:
                    pass
            self._ctx = self._pw = self._cdp_browser = None
            self._using_cdp = False
            return

        if self._ctx:
            self._ctx.close()
        if self._pw:
            self._pw.stop()
        self._ctx = self._pw = None

    @staticmethod
    def _enable_resource_blocking(page, block_images: bool = False):
        """Abort external ad trackers (and page images when block_images). Never abort internal security scripts."""
        def _block_heavy(route):
            req = route.request
            if any(
                tk in req.url.lower() for tk in ("facebook.net", "google-analytics.com", "criteo.com", "doubleclick.net", "tiktok.com")
            ):
                try:
                    route.abort()
                except Exception:
                    pass
            elif req.resource_type == "media" or (block_images and req.resource_type == "image"):
                try:
                    route.abort()
                except Exception:
                    pass
            else:
                try:
                    route.continue_()
                except Exception:
                    pass

        try:
            page.route("**/*", _block_heavy)
        except Exception:
            pass

    def _try_drag_slider(self, page) -> bool:
        """Simulate human-like drag on Alibaba/Lazada NoCaptcha slider if present."""
        import random
        try:
            slider_btn = None
            target_scope = page
            for sel in ("#nc_1_n1z", "span.nc_iconfont.btn_slide", ".btn_slide", "[class*='btn_slide']"):
                loc = page.locator(sel)
                if loc.count() > 0:
                    try:
                        if loc.first.is_visible():
                            slider_btn = loc.first
                            break
                    except Exception:
                        pass

            if not slider_btn:
                for frame in page.frames:
                    for sel in ("#nc_1_n1z", "span.nc_iconfont.btn_slide", ".btn_slide", "[class*='btn_slide']"):
                        try:
                            loc = frame.locator(sel)
                            if loc.count() > 0 and loc.first.is_visible():
                                slider_btn = loc.first
                                target_scope = frame
                                break
                        except Exception:
                            pass
                    if slider_btn:
                        break

            if not slider_btn:
                return False

            box = slider_btn.bounding_box()
            if not box:
                return False

            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2
            drag_distance = 320.0
            try:
                track = target_scope.locator(".nc_scale, #nc_1_n1t, [class*='nc_scale']").first
                t_box = track.bounding_box()
                if t_box:
                    drag_distance = max(200.0, t_box["width"] - box["width"] + 10)
            except Exception:
                pass

            log.info("Found Lazada slider button, dragging %.1fpx...", drag_distance)
            page.mouse.move(start_x, start_y)
            page.wait_for_timeout(random.randint(100, 200))
            page.mouse.down()
            page.wait_for_timeout(random.randint(50, 100))

            steps = random.randint(15, 25)
            for i in range(steps):
                progress = (i + 1) / steps
                step_dist = drag_distance * (1 - (1 - progress) ** 2)
                page.mouse.move(start_x + step_dist, start_y + random.uniform(-2, 2))
                page.wait_for_timeout(random.randint(15, 30))

            page.mouse.up()
            page.wait_for_timeout(1000)

            cleared = bool(page.evaluate("""() => {
                const okEl = document.querySelector('.nc_ok, [class*="nc_ok"], #nc_1_n1z.nc_ok, .nc-lang-cnt');
                if (okEl && (okEl.innerText || '').match(/xác minh|passed|success|thành công/i)) return true;
                if (!document.querySelector('#nc_1_wrapper, .nc_wrapper, .btn_slide')) return true;
                return false;
            }"""))
            if cleared:
                log.info("Lazada slider drag successfully cleared!")
                return True
            return False
        except Exception as exc:
            log.debug("Lazada slider drag error: %s", exc)
            return False

    def _wait_for_captcha_solve(self, page, timeout_sec: int = 15) -> bool:
        """Wait for NopeCHA extension or slider drag to solve captcha challenge (up to timeout_sec)."""
        import time
        start_t = time.time()

        # 1. Try slider drag first if Alibaba slider is detected
        try:
            if self._try_drag_slider(page):
                page.wait_for_timeout(1500)
                if getattr(self, "_quota", None) is not None and hasattr(self._quota, "record_solve"):
                    self._quota.record_solve(1)
                return True
        except Exception:
            pass

        log.info("Waiting up to %ds for NopeCHA extension / challenge to clear...", timeout_sec)
        while time.time() - start_t < timeout_sec:
            try:
                page.wait_for_timeout(1000)
            except Exception:
                return False

            try:
                cur_url = page.url.lower()
            except Exception:
                cur_url = ""

            is_stuck_url = any(sig in cur_url for sig in (
                "/punish", "/verify/traffic", "/verify/captcha", "verify/slider", "acs.lazada.vn", "/buyer/login"
            ))

            has_slider = False
            try:
                has_slider = bool(page.evaluate("() => !!document.querySelector('#nc_1_wrapper, .nc_wrapper, .btn_slide, div[id*=\"nocaptcha\"], div[class*=\"captcha\"]')"))
            except Exception:
                pass

            if not is_stuck_url and not has_slider:
                log.info("Captcha cleared/solved in %.1fs", time.time() - start_t)
                if getattr(self, "_quota", None) is not None and hasattr(self._quota, "record_solve"):
                    self._quota.record_solve(1)
                return True

            if has_slider:
                try:
                    if self._try_drag_slider(page):
                        page.wait_for_timeout(1500)
                        if getattr(self, "_quota", None) is not None and hasattr(self._quota, "record_solve"):
                            self._quota.record_solve(1)
                        return True
                except Exception:
                    pass

        log.warning("Captcha challenge did not clear within %ds (current url: %s)", timeout_sec, getattr(page, "url", "unknown"))
        return False

    # ── Fetch ────────────────────────────────────────────────────────────────

    def fast_fetch(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot | None:
        """Lightweight API poller for Shopee and fast-path for tracked products (ADR 0060)."""
        platform = self.parse_platform(url)
        if platform == "shopee":
            try:
                return self._fast_fetch_shopee(url, target_sku=target_sku, is_tracked=is_tracked)
            except Exception as e:
                log.debug("Shopee fast_fetch failed: %s", e)
                return None
        return None

    def _fast_fetch_shopee(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot | None:
        import httpx
        m = re.search(r"/product/(\d+)/(\d+)", url)
        if not m:
            m = re.search(r"-i\.(\d+)\.(\d+)", url)
        if not m:
            return None
        shop_id, item_id = m.group(1), m.group(2)

        cookie_file = Path(self._config.db_path).parent / "cookies.json"
        cookies = {}
        if cookie_file.exists():
            try:
                for c in json.loads(cookie_file.read_text(encoding="utf-8")):
                    cookies[c["name"]] = c["value"]
            except Exception:
                pass

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://shopee.vn/",
            "Accept": "application/json",
        }
        api_url = f"https://shopee.vn/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}"
        resp = httpx.get(api_url, headers=headers, cookies=cookies, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data and ("item" in data["data"] or "models" in data["data"]):
                if "item" not in data["data"]:
                    data = {"data": {"item": data["data"]}}
                snap = self._parse_shopee(None, url, pdp_payload=data, target_sku=target_sku, is_tracked=is_tracked)
                if snap and snap.price is not None and snap.price > 0:
                    return snap
        return None

    def fetch(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
        snap = self._executor.submit(self._fetch_sync, url, target_sku, is_tracked).result()
        if snap is not None and snap.price and self.parse_platform(url) == "lazada":
            try:
                self._executor.submit(self._persist_cookies, "lazada").result(timeout=5)
            except Exception:
                pass
        return snap

    def _fetch_sync(self, url: str, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
        self._ensure_started()
        page = self._ctx.new_page()
        _setup_page(page)
        pdp_payload = {}
        lazada_payload = {}

        def _on_response(res):
            url_lower = res.url.lower()
            if any(ep in url_lower for ep in ("/pdp/get_pc", "/api/v4/item/get", "/api/v2/item/get")) and res.status == 200:
                try:
                    data = res.json()
                    if "data" in data and "item" not in data["data"] and ("itemid" in data["data"] or "models" in data["data"]):
                        data = {"data": {"item": data["data"]}}
                    pdp_payload.update(data)
                except Exception:
                    pass
            elif any(ep in url_lower for ep in ("mtop.lazada.item.detail", "mtop.global.detail", "getdetailinfo", "mtop.lazada.promotion", "tradeinfo")) and res.status == 200:
                try:
                    text = res.text()
                    if text.startswith("mtopjsonp") and "(" in text and text.endswith(")"):
                        text = text[text.find("(") + 1 : text.rfind(")")]
                    data = json.loads(text)
                    if isinstance(data, dict):
                        if "data" in data and isinstance(data["data"], dict) and "module" in data["data"]:
                            mod = data["data"]["module"]
                            if isinstance(mod, str):
                                try:
                                    mod = json.loads(mod)
                                except Exception:
                                    mod = {}
                            if isinstance(mod, dict):
                                lazada_payload.update(mod)
                        elif "data" in data and isinstance(data["data"], dict):
                            lazada_payload.update(data["data"])
                        else:
                            lazada_payload.update(data)
                except Exception:
                    pass

        platform = self.parse_platform(url)
        target_url = canonicalize_url(url)
        page.on("response", _on_response)

        # Route block heavy resources on Lazada (only in internal headless mode; never on real Chrome CDP)
        if platform == "lazada" and not getattr(self, "_using_cdp", False):
            self._enable_resource_blocking(page, getattr(self._config, "block_images", False))

        try:
            referer = "https://www.lazada.vn/" if platform == "lazada" else "https://shopee.vn/"
            page.goto(target_url, wait_until="domcontentloaded", timeout=30_000, referer=referer)

            # Fast check: delisted, deleted, 404, or redirect to home page
            current_url = page.url.lower()
            if (
                current_url.rstrip("/") in ("https://shopee.vn", "https://www.lazada.vn", "https://lazada.vn")
                and not any(k in url.lower() for k in ("shopee.vn/?", "lazada.vn/?"))
            ):
                raise ProductDelisted(f"Product redirected to homepage: {url}")

            try:
                page_text = page.locator("body").inner_text(timeout=1000).lower()
                page_title = (page.title() or "").lower()
                delist_sigs = (
                    "sản phẩm không tồn tại",
                    "sản phẩm này không tồn tại",
                    "xin lỗi! sản phẩm này không còn tồn tại",
                    "rất tiếc, sản phẩm này không tồn tại",
                    "trang bạn tìm kiếm không tồn tại",
                    "sản phẩm này đã bị xóa",
                    "sản phẩm này đã ngừng bán",
                    "sản phẩm này hiện không còn khả dụng",
                    "không còn tồn tại",
                    "opps! page not found",
                    "404 not found",
                )
                if any(sig in page_text for sig in delist_sigs) or any(sig in page_title for sig in delist_sigs):
                    raise ProductDelisted(f"Product delisted or not found at {url}")
            except ProductDelisted:
                raise
            except Exception:
                pass

            if platform == "lazada":
                page_url = page.url.lower()
                is_lzd_blocked = any(sig in page_url for sig in ("/punish", "login.lazada.vn", "member.lazada.vn", "verify/slider", "acs.lazada.vn"))
                
                # Check for punish iframe (reCAPTCHA / x5sec challenge on MTOP)
                has_punish = False
                try:
                    has_punish = bool(page.evaluate("() => !!document.querySelector('iframe[src*=\"punish\"]')"))
                except Exception:
                    pass

                # If redirected to challenge or login page:
                if is_lzd_blocked:
                    log.info("Lazada page redirected to challenge at %s, attempting solver...", page.url)
                    solved = self._wait_for_captcha_solve(page, timeout_sec=15)
                    if not solved:
                        self.reload_cookies()
                        page.goto(target_url, wait_until="domcontentloaded", timeout=20_000, referer=referer)
                        if any(sig in page.url.lower() for sig in ("/punish", "login.lazada.vn", "verify/slider")):
                            raise Blocked(f"Lazada session expired or slider captcha at {url} (redirected to {page.url})")

                if not lazada_payload:
                    page.wait_for_timeout(1000)
                # First priority: parse using loaded cookies!
                try:
                    snap = self._parse_lazada(page, url, lazada_payload=lazada_payload, is_punished=has_punish, target_sku=target_sku, is_tracked=is_tracked)
                    if snap and snap.price is not None and snap.price > 0:
                        return snap
                except Blocked:
                    # Captcha punish iframe prevented getting price -> attempt solve
                    log.info("Lazada DOM price not found due to punish challenge, attempting solver...")
                    solved = self._wait_for_captcha_solve(page, timeout_sec=15)
                    if solved:
                        page.wait_for_timeout(1000)
                        return self._parse_lazada(page, url, lazada_payload=lazada_payload, is_punished=False, target_sku=target_sku, is_tracked=is_tracked)
                    self.reload_cookies()
                    page.goto(target_url, wait_until="domcontentloaded", timeout=20_000, referer=referer)
                    page.wait_for_timeout(1000)
                    return self._parse_lazada(page, url, lazada_payload=lazada_payload, is_punished=True, target_sku=target_sku, is_tracked=is_tracked)

                return self._parse_lazada(page, url, lazada_payload=lazada_payload, is_punished=has_punish, target_sku=target_sku, is_tracked=is_tracked)

            for _ in range(65):
                if pdp_payload and "data" in pdp_payload and pdp_payload["data"].get("item"):
                    break
                page.wait_for_timeout(100)

            # If PDP payload was already captured with product details, return it
            if pdp_payload and "data" in pdp_payload and pdp_payload["data"].get("item"):
                return self._parse_shopee(page, url, pdp_payload=pdp_payload, target_sku=target_sku, is_tracked=is_tracked)

            if self._is_blocked(page, pdp_payload):
                solved = self._wait_for_captcha_solve(page, timeout_sec=15)
                if not solved:
                    self.reload_cookies()
                    page.goto(target_url, wait_until="domcontentloaded", timeout=20_000, referer=referer)
                    page.wait_for_timeout(1000)
                    if self._is_blocked(page):
                        raise Blocked(f"Platform blocked at {url}")

            return self._parse_shopee(page, url, pdp_payload=pdp_payload, target_sku=target_sku, is_tracked=is_tracked)

        except Blocked:
            raise
        except Exception as exc:
            raise FetchError(f"Playwright error for {url}: {exc}") from exc
        finally:
            page.close()

    def _is_blocked(self, page, pdp_payload: dict | None = None) -> bool:
        if pdp_payload and "data" in pdp_payload and pdp_payload["data"].get("item"):
            return False
        try:
            current_url = page.url.lower()
        except Exception:
            current_url = ""
        return any(sig in current_url for sig in ("/verify/traffic", "/verify/captcha", "/buyer/login"))

    def _parse_shopee(self, page, url: str, pdp_payload: dict | None = None, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
        name = ""
        price = None
        list_price = None
        stock = None
        rating = None
        sold = None
        category = ""
        voucher_code = ""
        voucher_discount = 0.0
        final_price = None
        candidate_shopee_vouchers = []
        origin = ""
        shop_country = ""
        ships_from = ""
        services = ""
        extracted_variants: list[VariantInfo] = []
        m_sku = re.search(r"[?&]modelid=(\d+)", url)
        sku_from_url = m_sku.group(1) if m_sku else ""
        desired_sku = str(target_sku).strip() if target_sku else ""

        # 1. Parse from intercepted pdp/get_pc API payload
        if pdp_payload and "data" in pdp_payload:
            item = pdp_payload["data"].get("item", {})
            name = item.get("title") or ""

            # Extract the lowest price among available in-stock models/variations
            models = item.get("models") or []
            for m in models:
                mid = str(m.get("modelid") or m.get("itemid") or "")
                m_name = (m.get("name") or "").strip()
                m_rp = m.get("price")
                m_price = (float(m_rp) / 100000.0 if float(m_rp) > 100000 else float(m_rp)) if m_rp is not None else None
                m_rl = m.get("price_before_discount")
                m_list = (float(m_rl) / 100000.0 if float(m_rl) > 100000 else float(m_rl)) if m_rl is not None and float(m_rl) > 0 else None
                m_stk = m.get("normal_stock") or m.get("stock") or 0
                m_state = "in" if m_stk > 0 else "out"
                extracted_variants.append(
                    VariantInfo(
                        variant_key=mid,
                        name=m_name or f"Phân loại {mid}",
                        price=m_price,
                        list_price=m_list,
                        stock_state=m_state,
                        stock_qty=m_stk,
                        stock_source="shopee_pdp_models",
                    )
                )

            in_stock_models = [
                m for m in models
                if (m.get("stock") or 0) > 0 and m.get("price") is not None
            ]
            target_match = None
            if in_stock_models:
                stock = True
                # User decision: always pick absolute lowest in-stock model across entire listing
                lowest_model = min(in_stock_models, key=lambda m: float(m["price"]))
                raw_price = lowest_model["price"]
                model_name = (lowest_model.get("name") or "").strip()
                if model_name:
                    clean_name = re.sub(r"\s*\([^)]*\)$", "", name).strip()
                    name = f"{clean_name} ({model_name})"
                sku_from_url = str(lowest_model.get("modelid") or lowest_model.get("itemid") or "")
            elif models:
                # Models list exists but all variations have 0 stock
                stock = False
                raw_price = item.get("price_min") or item.get("price")
            else:
                # No models list, inspect item-level stock indicators
                stk_val = item.get("stock")
                item_stat = str(item.get("item_status") or "").lower()
                stat_val = item.get("status")
                is_unavail = item.get("is_unavailable")
                stk_disp = str(item.get("stock_display") or "").lower()
                if (
                    stk_val == 0
                    or item_stat in ("out_of_stock", "deleted", "banned")
                    or stat_val in (2, 3)
                    or is_unavail is True
                    or "hết hàng" in stk_disp
                ):
                    stock = False
                elif stk_val is not None and stk_val > 0:
                    stock = True
                else:
                    stock = True if not is_unavail else False
                flash_info = item.get("flash_sale") or item.get("upcoming_flash_sale") or {}
                flash_p = flash_info.get("price") if (flash_info and isinstance(flash_info, dict)) else None
                raw_price = flash_p or item.get("price_min") or item.get("price")

            if raw_price is not None:
                # Shopee prices are multiplied by 100,000 in API
                rp = float(raw_price)
                price = rp / 100000.0 if rp > 100000 else rp

            # For single-option products (no models or 1 model): check if DOM visible sale price has a lower active promotion
            if not in_stock_models or len(in_stock_models) <= 1:
                dom_shopee_p = _extract_shopee_dom_price(page)
                if dom_shopee_p and 1_000 <= dom_shopee_p <= 1_000_000_000:
                    if price is None or dom_shopee_p < price:
                        price = dom_shopee_p

            # Extract list price matching the selected lowest model
            if in_stock_models and lowest_model and lowest_model.get("price_before_discount") and float(lowest_model["price_before_discount"]) > 0:
                raw_list = lowest_model["price_before_discount"]
            else:
                raw_list = item.get("price_before_discount") if not in_stock_models else None

            if raw_list is not None and float(raw_list) > 0:
                rl = float(raw_list)
                converted_list = rl / 100000.0 if rl > 100000 else rl
                if price is None or converted_list >= price:
                    list_price = converted_list
            rating = None if is_tracked else (item.get("item_rating") or {}).get("rating_star")
            sold = item.get("historical_sold")
            if stock is None:
                stock = True if (item.get("stock") or 0) > 0 else False

            cats = pdp_payload["data"].get("categories") or []
            if cats:
                category = " > ".join(c.get("display_name", "") for c in cats if c.get("display_name"))

            ships_from = item.get("shop_location") or ""
            for attr in (item.get("attributes") or []):
                aname = (attr.get("name") or "").lower()
                aval = str(attr.get("value") or "")
                if any(k in aname for k in ("xuất xứ", "origin")):
                    origin = aval
                elif any(k in aname for k in ("gửi từ", "nơi gửi", "vận chuyển từ")):
                    if not ships_from:
                        ships_from = aval
            shop_info = pdp_payload["data"].get("shop_info") or {}
            shop_country = str(shop_info.get("country") or shop_info.get("shop_location") or "")

            # Collect shop vouchers from pdp_payload
            raw_shop_vouchers = pdp_payload["data"].get("shop_vouchers") or []
            for sv in raw_shop_vouchers:
                if isinstance(sv, dict):
                    v_item = dict(sv)
                    v_item.setdefault("voucher_type", "shop")
                    candidate_shopee_vouchers.append(v_item)

        # 2. Fallback to DOM and embedded script parsing
        if not name or price is None:
            try:
                for script in page.locator("script").all_inner_texts():
                    if "initialState" in script and '"item"' in script:
                        import json
                        s_data = json.loads(script)
                        it_map = s_data.get("initialState", {}).get("item", {}).get("items", {})
                        for it in it_map.values():
                            if not name:
                                name = it.get("title") or ""
                            if price is None:
                                p_min = it.get("price_min") or it.get("price")
                                if p_min:
                                    pval = float(p_min)
                                    price = pval / 100000.0 if pval > 100000 else pval
                            break
            except Exception:
                pass

        if not name:
            for title_sel in ['[class*="page-product__title"]', 'h1', '[class*="title"]']:
                try:
                    loc = page.locator(title_sel)
                    if loc.count() > 0:
                        name = loc.first.inner_text(timeout=2_000).strip()
                        if name:
                            break
                except Exception:
                    continue

        if price is None:
            price_selectors = [
                '[class*="priceSectionPrice"]',
                '[class*="pqTWkA"]',
                '[class*="G27FPf"]',
                '[class*="_1k47d8"]',
                '[class*="IZPeQz"]',
                '.product-price',
            ]
            for p_sel in price_selectors:
                try:
                    loc = page.locator(p_sel)
                    if loc.count() > 0:
                        raw = loc.first.inner_text(timeout=2_000)
                        first_part = raw.split("-")[0]
                        m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d{4,})", first_part)
                        if m:
                            val = float(m.group(1).replace(".", ""))
                            if 1_000 <= val <= 1_000_000_000:
                                price = val
                                break
                except Exception:
                    continue

        if price is None:
            # Body text regex fallback: find first formatted price like 120.000₫ or ₫120.000
            try:
                body_text = page.locator("body").inner_text(timeout=2_000)
                m = re.search(r"(?:₫|đ)\s*(\d{1,3}(?:\.\d{3})+)|(\d{1,3}(?:\.\d{3})+)\s*(?:₫|đ)", body_text)
                if m:
                    match_str = m.group(1) or m.group(2)
                    val = float(match_str.replace(".", ""))
                    if 1_000 <= val <= 1_000_000_000:
                        price = val
            except Exception:
                pass

        if stock is None:
            try:
                is_shopee_out = page.evaluate("""() => {
                    const varBtns = Array.from(document.querySelectorAll('.product-variation, [class*="product-variation"]'));
                    if (varBtns.length > 0) {
                        const hasInStockVar = varBtns.some(b => 
                            !b.classList.contains('product-variation--disabled') && 
                            b.getAttribute('aria-disabled') !== 'true' && 
                            !b.disabled
                        );
                        if (hasInStockVar) return false;
                        return true;
                    }
                    const bodyTxt = (document.body ? document.body.innerText || '' : '').toLowerCase();
                    if (bodyTxt.includes('sản phẩm này hiện đã hết hàng') || bodyTxt.includes('đã hết hàng') || bodyTxt.includes('tạm thời hết hàng') || document.querySelector('.cart-sold-out, [class*="sold-out"]')) {
                        return true;
                    }
                    const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
                    const buyBtns = btns.filter(b => {
                        const t = (b.innerText || b.getAttribute('aria-label') || '').toLowerCase();
                        return t.includes('mua') || t.includes('giỏ hàng') || t.includes('hết hàng');
                    });
                    if (buyBtns.length > 0 && buyBtns.every(b => b.disabled || b.getAttribute('aria-disabled') === 'true' || b.classList.contains('btn--disabled') || (b.innerText || '').toLowerCase().includes('hết hàng'))) {
                        return true;
                    }
                    return false;
                }""")
                if is_shopee_out:
                    stock = False
                else:
                    stock = True
            except Exception:
                stock = True

        if price is None:
            if self._is_blocked(page, pdp_payload):
                raise Blocked(f"Platform blocked at {url}")
            if stock is False:
                price = 0.0
            else:
                raise FetchError(f"Cannot parse price at {url}")

        if not category:
            try:
                cat_items = page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('.page-product__breadcrumb a, [class*="breadcrumb"] a'));
                    return els.map(a => a.innerText.trim()).filter(t => t && t.toLowerCase() !== 'shopee');
                }""")
                if cat_items:
                    category = " > ".join(cat_items)
            except Exception:
                pass

        # Collect and stack DOM vouchers for Shopee (platform vouchers, live badges, tickets)
        if price is not None and price > 0:
            try:
                shopee_v_elements = page.evaluate("""() => {
                    const sel = [
                        '.voucher-ticket',
                        '[class*="voucher-badge"]',
                        '[class*="voucher-ticket"]',
                        '[class*="voucher"]',
                        '[aria-label*="voucher"]',
                        '[aria-label*="Mã giảm giá"]',
                        '.shopee-voucher-badge'
                    ];
                    const els = document.querySelectorAll(sel.join(', '));
                    return Array.from(els).map(e => (e.innerText || e.getAttribute('aria-label') || '').trim()).filter(Boolean);
                }""")
                for sv in shopee_v_elements:
                    parsed_v = _parse_lazada_voucher_text(sv)
                    if parsed_v:
                        if "LAZADA" in parsed_v.get("voucher_code", ""):
                            parsed_v["voucher_code"] = parsed_v["voucher_code"].replace("LAZADA", "SHOPEE")
                        candidate_shopee_vouchers.append(parsed_v)
            except Exception:
                pass

        if candidate_shopee_vouchers and price is not None and price > 0:
            v_code_s, v_disc_s = _find_best_voucher(price, candidate_shopee_vouchers, allow_stacking=True)
            if v_code_s and v_disc_s > 0:
                voucher_code = v_code_s
                voucher_discount = v_disc_s

        if price is not None:
            if voucher_discount > 0:
                final_price = max(0.0, round(price - voucher_discount, 2))
            else:
                final_price = price

        if not ships_from or not origin:
            try:
                body_txt = page.locator("body").inner_text() if page else ""
                if not origin:
                    m = re.search(r"(?:xuất xứ|origin)\s*[:\s]\s*([^\n\r,]+)", body_txt, re.IGNORECASE)
                    if m:
                        origin = m.group(1).strip()
                if not ships_from:
                    m = re.search(r"(?:gửi từ|nơi gửi hàng|vận chuyển từ)\s*[:\s]\s*([^\n\r,]+)", body_txt, re.IGNORECASE)
                    if m:
                        ships_from = m.group(1).strip()
            except Exception:
                pass

        canonical_url = page.url if page and page.url and ("-i." in page.url or "/product/" in page.url) else url
        if canonical_url and ("-i." in canonical_url or "/product/" in canonical_url):
            canonical_url = canonical_url.split("?")[0]
        if not ships_from:
            ships_from = self._item_locations.get(canonical_url) or self._item_locations.get(url) or ""
        return Snapshot(
            platform="shopee",
            item_key=self.parse_item_key(canonical_url),
            url=canonical_url,
            name=name,
            shop="",       # shortcut: add shop parsing when needed
            price=price,
            list_price=list_price,
            stock=stock,
            rating=rating,
            sold=sold,
            category=category,
            voucher_code=voucher_code,
            voucher_discount=voucher_discount,
            final_price=final_price,
            origin=origin,
            shop_country=shop_country,
            ships_from=ships_from,
            services=services,
            verified=1,
            variants=extracted_variants,
            sku_from_url=sku_from_url,
        )


    def _parse_lazada(self, page, url: str, lazada_payload: dict | None = None, is_punished: bool = False, target_sku: str | None = None, is_tracked: bool = False) -> Snapshot:
        import json
        import re

        name = ""
        price = None
        list_price = None
        stock = None
        rating = None
        sold = None
        category = ""
        voucher_code = ""
        voucher_discount = 0.0
        final_price = None
        is_subsidized_price = False
        origin = ""
        shop_country = ""
        ships_from = ""
        services = ""
        tracking = {}
        valid_skus = []
        extracted_variants: list[VariantInfo] = []
        m_sku = re.search(r"-s(\d+)\.html", url)
        sku_from_url = m_sku.group(1) if m_sku else ""
        desired_sku = str(target_sku).strip() if target_sku else ""

        # 1. Try extracting structured data from JSON-LD scripts
        jsonld_price = None
        try:
            for s in page.locator('script[type="application/ld+json"]').all_inner_texts():
                try:
                    data = json.loads(s)
                    if isinstance(data, dict) and data.get("@type") == "Product":
                        name = data.get("name") or name
                        offers = data.get("offers") or {}
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict):
                            p_val = offers.get("price")
                            if p_val:
                                jsonld_price = float(p_val)
                            avail = str(offers.get("availability") or "").lower()
                            if "outofstock" in avail or "soldout" in avail:
                                stock = False
                            elif "instock" in avail:
                                stock = True
                        if not is_tracked:
                            agg_rating = data.get("aggregateRating") or {}
                            if isinstance(agg_rating, dict):
                                r_val = agg_rating.get("ratingValue")
                                if r_val:
                                    rating = float(r_val)
                                s_val = agg_rating.get("reviewCount")
                                if s_val:
                                    sold = int(s_val)
                        if name and jsonld_price:
                            break
                except Exception:
                    pass
        except Exception:
            pass

        # 2. Extract and refine from window.__moduleData__ and lazada_payload (check for promotional/subsidized SKUs)
        try:
            mod_data = page.evaluate("""() => {
                if (window.__moduleData__ && window.__moduleData__.data) {
                    return window.__moduleData__.data;
                }
                if (window.__INITIAL_DATA__ && window.__INITIAL_DATA__.product) {
                    return window.__INITIAL_DATA__.product;
                }
                return null;
            }""")
            source_data = mod_data or lazada_payload or {}
            if source_data and isinstance(source_data, dict):
                root = source_data.get("root") or source_data
                fields = root.get("fields") or root.get("data", {}).get("fields") or {}
                if not name:
                    name = (fields.get("productTitle") or {}).get("title") or ""
                
                mod_skus = _find_sku_infos(mod_data)
                payload_skus = _find_sku_infos(lazada_payload)
                sku_infos = {}
                if mod_skus:
                    sku_infos.update(mod_skus)
                if payload_skus:
                    for sid, sinfo in payload_skus.items():
                        if sid in sku_infos and isinstance(sku_infos[sid], dict) and isinstance(sinfo, dict):
                            sku_infos[sid].update(sinfo)
                        else:
                            sku_infos[sid] = sinfo

                sku_name_map = _extract_sku_names(mod_data)
                if not sku_name_map:
                    sku_name_map = _extract_sku_names(lazada_payload)

                valid_skus = []
                unique_sku_ids = set()
                seen_sids = set()
                if sku_infos:
                    sku_stock_statuses = []
                    for sku_id, sinfo in sku_infos.items():
                        if isinstance(sinfo, dict):
                            actual_sid = str(sinfo.get("skuId") or sku_id)
                            unique_sku_ids.add(actual_sid)
                            if actual_sid in seen_sids:
                                continue
                            seen_sids.add(actual_sid)

                            raw_p = (
                                sinfo.get("coupon")
                                or sinfo.get("subsidyPrice")
                                or sinfo.get("promotionPrice")
                                or sinfo.get("cartPrice")
                                or sinfo.get("salePrice")
                                or sinfo.get("price")
                            )
                            p_val = _clean_price_val(raw_p)
                            raw_l = sinfo.get("originalPrice") or sinfo.get("listPrice")
                            if raw_l is None and isinstance(sinfo.get("price"), dict):
                                raw_l = sinfo["price"].get("originalPrice") or sinfo["price"].get("listPrice")
                            l_val = _clean_price_val(raw_l)
                            
                            op_dict = sinfo.get("operation") if isinstance(sinfo.get("operation"), dict) else {}
                            op_disable = op_dict.get("disable")
                            op_type = str(op_dict.get("type") or "").lower()
                            op_text = str(op_dict.get("text") or "").lower()
                            qty_val = sinfo.get("quantity")
                            stk_val = sinfo.get("stock")

                            is_out = False
                            if op_disable is True:
                                is_out = True
                            elif op_type == "wishlist" or any(k in op_text for k in ("yêu thích", "wishlist", "hết hàng", "out of stock")):
                                is_out = True
                            elif isinstance(qty_val, dict):
                                max_limit = qty_val.get("limit", {}).get("max", 0)
                                q_text = str(qty_val.get("text") or "").lower()
                                if max_limit <= 0 or "hết hàng" in q_text or "out of stock" in q_text:
                                    is_out = True
                            elif isinstance(stk_val, (int, float)) and stk_val <= 0:
                                is_out = True
                            elif isinstance(qty_val, (int, float)) and qty_val <= 0:
                                is_out = True

                            is_in_stock = not is_out
                            sku_stock_statuses.append(is_in_stock)

                            s_name = sinfo.get("name") or sinfo.get("model") or sku_name_map.get(actual_sid) or sku_name_map.get(str(sku_id)) or ""
                            stock_state = "out" if is_out else "in"
                            q_limit = qty_val.get("limit", {}).get("max") if isinstance(qty_val, dict) else (qty_val if isinstance(qty_val, int) else None)
                            extracted_variants.append(
                                VariantInfo(
                                    variant_key=actual_sid,
                                    name=s_name or f"Phân loại {actual_sid}",
                                    price=p_val,
                                    list_price=l_val,
                                    stock_state=stock_state,
                                    stock_qty=q_limit,
                                    stock_source="lazada_mtop_sku",
                                )
                            )
                            if p_val and is_in_stock:
                                is_sub = bool(sinfo.get("subsidyPrice") and p_val == _clean_price_val(sinfo.get("subsidyPrice")))
                                valid_skus.append((actual_sid, p_val, l_val, s_name, is_sub))

                    lowest_mtop_is_out = False
                    target_sku_is_out = False
                    if extracted_variants:
                        if desired_sku:
                            for ev in extracted_variants:
                                if str(ev.variant_key) == str(desired_sku) and ev.stock_state == "out":
                                    target_sku_is_out = True
                                    break
                        valid_priced = [ev for ev in extracted_variants if ev.price and ev.price > 0]
                        if valid_priced:
                            cheapest_ev = min(valid_priced, key=lambda x: x.price)
                            if cheapest_ev.stock_state == "out":
                                lowest_mtop_is_out = True

                    if any(sku_stock_statuses):
                        stock = True
                    elif sku_stock_statuses:
                        stock = False

                    if valid_skus:
                        if len(unique_sku_ids) > 1:
                            # Multi-option: always pick absolute lowest in-stock SKU across entire listing (PRESERVED)
                            best_sku = min(valid_skus, key=lambda x: x[1])
                            price = best_sku[1]
                            is_subsidized_price = best_sku[4]
                            if best_sku[2] and best_sku[2] > price:
                                list_price = best_sku[2]
                            elif list_price is not None and list_price < price:
                                list_price = None
                        else:
                            # Single-option product: check DOM visible sale price for any active promotion/discount
                            best_sku = valid_skus[0]
                            sku_p = best_sku[1]
                            is_subsidized_price = best_sku[4]
                            dom_p = _extract_lazada_dom_price(page)
                            if dom_p and 1_000 <= dom_p <= 1_000_000_000 and dom_p < sku_p:
                                price = dom_p
                                list_price = best_sku[2] if (best_sku[2] and best_sku[2] > dom_p) else sku_p
                            else:
                                price = sku_p
                                if best_sku[2] and best_sku[2] > price:
                                    list_price = best_sku[2]

                        best_var_name = best_sku[3].strip() if len(best_sku) > 3 and best_sku[3] else ""
                        if best_var_name:
                            clean_name = re.sub(r"\s*\([^)]*\)$", "", name).strip()
                            name = f"{clean_name} ({best_var_name})"
                    else:
                        all_skus = []
                        target_out_match = None
                        for sinfo in sku_infos.values():
                            if isinstance(sinfo, dict):
                                rp = _clean_price_val(sinfo.get("price") or sinfo.get("salePrice") or sinfo.get("promotionPrice"))
                                sid = str(sinfo.get("skuId") or "")
                                if rp:
                                    all_skus.append(rp)
                                    if desired_sku and sid == str(desired_sku):
                                        target_out_match = rp
                        if all_skus and price is None:
                            price = target_out_match or min(all_skus)

                # User decision (ADR 0054): do NOT use tracking.pdt_price as list_price (prevents fake 80-90% discount alerts)
                tracking = fields.get("tracking") or {}
        except Blocked:
            raise
        except Exception:
            pass

        # 2b. Detect TMALL TRỢ GIÁ / MOMCLUB / Trợ giá badges
        try:
            has_tmall_badge = page.evaluate("""() => {
                const badgeEls = document.querySelectorAll('[class*="badge"], [class*="tmall"], [class*="subsidy"], .pdp-mod-product-badge, img[src*="tmall"], [class*="momclub"]');
                for (const el of badgeEls) {
                    const t = (el.innerText || el.getAttribute('alt') || el.getAttribute('title') || '').toLowerCase();
                    if (t.includes('tmall') || t.includes('trợ giá') || t.includes('momclub') || t.includes('độc quyền')) return true;
                }
                return false;
            }""")
            if has_tmall_badge or any(k in name.lower() for k in ("tmall", "trợ giá", "momclub", "độc quyền")):
                badge_tag = "[MOMCLUB]" if "momclub" in name.lower() else "[TMALL TRỢ GIÁ]"
                if not any(b in name for b in ("[TMALL TRỢ GIÁ]", "[MOMCLUB]")):
                    name = f"{badge_tag} {name}"
        except Exception:
            pass

        # 3. DOM selectors fallback
        if not name:
            try:
                for sel in (".pdp-mod-product-badge-title", "h1.pdp-product-title", "h1", "title"):
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        t = loc.first.inner_text(timeout=1000).strip()
                        if t and len(t) > 3 and "lazada" not in t.lower():
                            name = t
                            break
            except Exception:
                pass

        if price is None:
            dom_p = _extract_lazada_dom_price(page)
            if dom_p and 1_000 <= dom_p <= 1_000_000_000:
                price = dom_p
            elif jsonld_price:
                price = jsonld_price

        if list_price is None:
            try:
                for sel in (
                    ".pdp-v2-product-price-content-originalPrice-amount",
                    ".pdp-v2-product-price-content-originalPrice",
                    "[class*='originalPrice']",
                    ".pdp-price_type_deleted",
                    ".origin-price",
                    ".pdp-price_color_gray",
                ):
                    loc = page.locator(sel)
                    if loc.count() > 0:
                        txt = loc.first.inner_text(timeout=1000)
                        m = re.search(r"(?:₫|đ)\s*([0-9.,]+)|([0-9.,]+)\s*(?:₫|đ)|(\d{1,3}(?:\.\d{3})+|\d{4,})", txt)
                        if m:
                            match_str = m.group(1) or m.group(2) or m.group(3)
                            val = float(match_str.replace(".", "").replace(",", ""))
                            if price is None or val >= price:
                                list_price = val
                                break
            except Exception:
                pass

        # List price remains None if no genuine strike-through price exists

        if price is None:
            try:
                body_text = page.locator("body").inner_text(timeout=2000)
                if "x5sec" in body_text or "bảo vệ tài khoản" in body_text or "trượt để xác minh" in body_text:
                    raise Blocked(f"Lazada blocked by captcha at {url}")
                m = re.search(r"(?:₫|đ)\s*(\d{1,3}(?:\.\d{3})+)|(\d{1,3}(?:\.\d{3})+)\s*(?:₫|đ)", body_text)
                if m:
                    match_str = m.group(1) or m.group(2)
                    val = float(match_str.replace(".", ""))
                    if 1_000 <= val <= 1_000_000_000:
                        price = val
            except Blocked:
                raise
            except Exception:
                pass
        if price is None and jsonld_price:
            price = jsonld_price

        # Stock check in DOM (DOM out-of-stock indicators take precedence over static JSON-LD)
        try:
            is_dom_out_of_stock = page.evaluate("""() => {
                const b = document.querySelector('.baxia-dialog-close, .next-dialog-close, [aria-label="Close"], button[class*="close"], span[class*="close"]');
                if (b && typeof b.click === 'function') b.click();
                const d = document.querySelector('.baxia-dialog');
                if (d) d.remove();

                const buyBtn = document.querySelector('.next-btn-buy, .pdp-button_theme_orange, [class*="add-to-cart"], [class*="buy-now"], .add-to-cart-buy-now-btn, button[class*="buy"]');
                if (buyBtn) {
                    const txt = (buyBtn.innerText || buyBtn.textContent || '').toLowerCase();
                    if (buyBtn.disabled || buyBtn.getAttribute('aria-disabled') === 'true' || buyBtn.classList.contains('next-btn-disabled') || txt.includes('hết hàng') || txt.includes('out of stock') || txt.includes('tạm hết') || txt.includes('yêu thích') || txt.includes('wishlist')) {
                        return true;
                    }
                }
                const bodyTxt = (document.body ? document.body.innerText || '' : '').toLowerCase();
                if (bodyTxt.includes('tạm thời hết hàng') || bodyTxt.includes('sản phẩm đã hết hàng') || bodyTxt.includes('ngừng kinh doanh') || bodyTxt.includes('mặt hàng này đã hết')) {
                    return true;
                }
                const selectedSwatch = document.querySelector('.sku-variable-img-wrap-selected, .sku-variable-item_selected, .selected');
                if (selectedSwatch) {
                    if (selectedSwatch.classList.contains('disabled') || selectedSwatch.classList.contains('sku-variable-item_disabled') || selectedSwatch.getAttribute('aria-disabled') === 'true') {
                        return true;
                    }
                }
                return false;
            }""")

            if is_dom_out_of_stock:
                stock = False

            swatch_info = []
            try:
                swatch_info = page.evaluate("""() => {
                    const list = [];
                    const elements = document.querySelectorAll('.sku-variable-img-wrap, .sku-variable-item, .sku-prop-content-item, [class*="sku-variable-img-wrap"]');
                    elements.forEach((el, idx) => {
                        const isSelected = el.classList.contains('sku-variable-img-wrap-selected') || el.classList.contains('sku-variable-item_selected') || el.classList.contains('selected');
                        const isDisabled = el.classList.contains('disabled') || el.classList.contains('sku-variable-item_disabled') || el.getAttribute('aria-disabled') === 'true';
                        const nameEl = el.querySelector('.sku-variable-img-name, .sku-name') || el;
                        const title = el.getAttribute('title') || el.getAttribute('data-title') || el.getAttribute('aria-label') || '';
                        const name = (title || nameEl.innerText || '').trim();
                        list.push({ index: idx, name: name, isSelected: isSelected, isDisabled: isDisabled });
                    });
                    return list.slice(0, 15);
                }""") or []
            except Exception:
                pass

            needs_swatch_probing = bool(
                is_dom_out_of_stock
                or target_sku_is_out
                or lowest_mtop_is_out
                or (not valid_skus and extracted_variants)
                or (len(swatch_info) > 1 and is_tracked)
                or (len(swatch_info) > 1 and not valid_skus)
            )

            if needs_swatch_probing and swatch_info and len(swatch_info) > 1:
                try:
                    probed_skus = []
                    for s in swatch_info:
                        if s.get("isDisabled"):
                            continue
                        idx = s["index"]
                        s_name = s["name"]

                        # Click swatch; returns the price text before the click so we can wait for it to change
                        prev_price = page.evaluate("""(idx) => {
                            const el = document.querySelector('.pdp-v2-product-price-content-salePrice-amount, .pdp-v2-product-price-content-salePrice, [class*="salePrice"], .pdp-price_type_normal, .pdp-price');
                            const before = el ? el.innerText : '';
                            const elements = document.querySelectorAll('.sku-variable-img-wrap, .sku-variable-item, .sku-prop-content-item, [class*="sku-variable-img-wrap"]');
                            if (elements[idx]) elements[idx].click();
                            return before;
                        }""", idx)
                        try:
                            # usually 150-250 ms; 500 ms cap keeps the old fixed wait as the worst case (same-price swatches)
                            page.wait_for_function("""(before) => {
                                const el = document.querySelector('.pdp-v2-product-price-content-salePrice-amount, .pdp-v2-product-price-content-salePrice, [class*="salePrice"], .pdp-price_type_normal, .pdp-price');
                                return (el ? el.innerText : '') !== before;
                            }""", arg=prev_price, timeout=500)
                        except Exception:
                            pass

                        probe_res = page.evaluate("""() => {
                            let price = null;
                            let listPrice = null;
                            let inStock = true;

                            for (const sel of [
                                '.pdp-v2-product-price-content-salePrice-amount',
                                '.pdp-v2-product-price-content-salePrice',
                                '[class*="salePrice"]',
                                '.pdp-price_type_normal',
                                '.pdp-price',
                                '[class*="pdp-price_type_normal"]'
                            ]) {
                                const el = document.querySelector(sel);
                                if (el && (el.innerText || '').trim()) {
                                    const text = el.innerText || '';
                                    const m = text.match(/(?:₫|đ)\\s*([0-9.,]+)|([0-9.,]+)\\s*(?:₫|đ)|(\\d{1,3}(?:\\.\\d{3})+|\\d{4,})/);
                                    if (m) {
                                        const rawNum = (m[1] || m[2] || m[3] || '').replace(/[.,]/g, '');
                                        if (rawNum && parseFloat(rawNum) >= 1000) { price = parseFloat(rawNum); break; }
                                    }
                                }
                            }

                            for (const sel of [
                                '.pdp-v2-product-price-content-originalPrice-amount',
                                '.pdp-v2-product-price-content-originalPrice',
                                '[class*="originalPrice"]',
                                '.pdp-price_type_deleted',
                                '.origin-price',
                                '.pdp-price_color_gray'
                            ]) {
                                const el = document.querySelector(sel);
                                if (el && (el.innerText || '').trim()) {
                                    const text = el.innerText || '';
                                    const m = text.match(/(?:₫|đ)\\s*([0-9.,]+)|([0-9.,]+)\\s*(?:₫|đ)|(\\d{1,3}(?:\\.\\d{3})+|\\d{4,})/);
                                    if (m) {
                                        const rawNum = (m[1] || m[2] || m[3] || '').replace(/[.,]/g, '');
                                        if (rawNum && parseFloat(rawNum) >= 1000) { listPrice = parseFloat(rawNum); break; }
                                    }
                                }
                            }

                            const buyBtn = document.querySelector('.next-btn-buy, .pdp-button_theme_orange, [class*="add-to-cart"], [class*="buy-now"], .add-to-cart-buy-now-btn, button[class*="buy"]');
                            const warningEl = document.querySelector('.quantity-content-warning, .pdp-mod-product-info-section [class*="out-of-stock"]');
                            if (warningEl && (warningEl.innerText || '').trim()) {
                                inStock = false;
                            }
                            if (buyBtn) {
                                const txt = (buyBtn.innerText || buyBtn.textContent || '').toLowerCase();
                                if (buyBtn.disabled || buyBtn.getAttribute('aria-disabled') === 'true' || buyBtn.classList.contains('next-btn-disabled') ||
                                    txt.includes('hết hàng') || txt.includes('out of stock') || txt.includes('tạm hết') || txt.includes('yêu thích') || txt.includes('wishlist')) {
                                    inStock = false;
                                }
                            }
                            const selectedSwatch = document.querySelector('.sku-variable-img-wrap-selected, .sku-variable-item_selected, .selected');
                            if (selectedSwatch && (selectedSwatch.classList.contains('disabled') || selectedSwatch.classList.contains('sku-variable-item_disabled') || selectedSwatch.getAttribute('aria-disabled') === 'true')) {
                                inStock = false;
                            }
                            return { price: price, listPrice: listPrice, inStock: inStock };
                        }""")

                        p_dom = probe_res.get("price")
                        l_dom = probe_res.get("listPrice")
                        stk_dom = probe_res.get("inStock")

                        if p_dom and 1_000 <= p_dom <= 1_000_000_000:
                            matched_var = None
                            for ev in extracted_variants:
                                if s_name and (s_name.lower() in ev.name.lower() or ev.name.lower() in s_name.lower()):
                                    matched_var = ev
                                    break
                            if matched_var:
                                matched_var.price = p_dom
                                if l_dom:
                                    matched_var.list_price = l_dom
                                matched_var.stock_state = "in" if stk_dom else "out"
                                matched_var.stock_source = "lazada_dom_swatch"
                            else:
                                extracted_variants.append(
                                    VariantInfo(
                                        variant_key=f"swatch_{idx}",
                                        name=s_name or f"Biến thể {idx+1}",
                                        price=p_dom,
                                        list_price=l_dom,
                                        stock_state="in" if stk_dom else "out",
                                        stock_source="lazada_dom_swatch",
                                    )
                                )

                            if stk_dom:
                                probed_skus.append((p_dom, l_dom, s_name or f"Biến thể {idx+1}", False))

                    if probed_skus:
                        best_probed = min(probed_skus, key=lambda x: x[0])
                        if price is None or best_probed[0] <= price:
                            price = best_probed[0]
                            if best_probed[1] and best_probed[1] > price:
                                list_price = best_probed[1]
                            stock = True
                            best_var_name = best_probed[2].strip() if len(best_probed) > 2 and best_probed[2] else ""
                            if best_var_name:
                                clean_name = re.sub(r"\s*\([^)]*\)$", "", name).strip()
                                name = f"{clean_name} ({best_var_name})"
                    elif is_dom_out_of_stock:
                        stock = False
                except Exception as e:
                    log.warning("Error probing swatches: %s", e)
            elif is_dom_out_of_stock:
                stock = False
            elif stock is None:
                stock = True
        except Exception:
            if stock is None:
                stock = True

        # If challenged by captcha and could not get valid in-stock price:
        if is_punished and (price is None or price <= 0):
            raise Blocked(f"Lazada session challenged by captcha punish iframe at {url}")

        # Ensure valid price or raise
        if price is None or price <= 0:
            if stock is False:
                price = 0.0
            else:
                is_challenge = False
                try:
                    page_url = page.url.lower()
                    if any(sig in page_url for sig in ("/punish", "login.lazada.vn", "member.lazada.vn", "verify/slider", "acs.lazada.vn")):
                        is_challenge = True
                    elif page.evaluate("() => !!document.querySelector('iframe[src*=\"punish\"], .btn_slide, #nc_1_wrapper, .punish')"):
                        is_challenge = True
                except Exception:
                    pass

                if not is_challenge and lazada_payload and isinstance(lazada_payload, dict):
                    ret_val = str(lazada_payload.get("ret", ""))
                    if any(err in ret_val for err in ("RGV587_ERROR", "FAIL_SYS_USER_VALIDATE", "FAIL_SYS_SESSION_EXPIRED")):
                        is_challenge = True

                if is_challenge:
                    raise Blocked(f"Lazada anti-bot challenge or expired session prevented reading price at {url}")

                raise FetchError(f"Cannot parse price for Lazada item at {url}")

        # Category in DOM
        if not category:
            try:
                crumbs = page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('.breadcrumb_item a, .pdp-breadcrumb a'));
                    return els.map(e => e.innerText.trim()).filter(t => t && t.toLowerCase() !== 'lazada');
                }""")
                if crumbs:
                    category = " > ".join(crumbs)
            except Exception:
                pass

        # Shop name from DOM
        shop = "Lazada Shop"
        try:
            shop_raw = page.evaluate("""() => {
                for (const sel of [
                    '.seller-info__name',
                    '[class*="seller-name"]',
                    '[class*="shop-name"]',
                    '.pdp-seller-info-name',
                ]) {
                    const el = document.querySelector(sel);
                    if (el) return (el.innerText || el.textContent || '').trim();
                }
                return '';
            }""")
            if shop_raw and isinstance(shop_raw, str) and shop_raw.strip():
                shop = shop_raw.strip()
        except Exception:
            pass

        # Voucher in DOM & Title
        candidate_vouchers = []
        try:
            v_elements = page.evaluate("""() => {
                const sel = [
                    '#module_promotion_tags',
                    '[class*="promotion-tag"]',
                    '.tag-name',
                    '[class*="voucher-ticket"]',
                    '[class*="voucher-item"]',
                    '[class*="voucher"]',
                    '[class*="coupon"]',
                    '[class*="discount-tag"]',
                    '.pdp-mod-voucher',
                    '[class*="lazada-coins"]',
                    '[class*="coin-tag"]',
                    '[class*="cashback"]',
                    '[class*="tag-content"]',
                ];
                const els = document.querySelectorAll(sel.join(', '));
                return Array.from(els).map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean);
            }""")
            for vt in v_elements:
                parsed = _parse_lazada_voucher_text(vt)
                if parsed:
                    candidate_vouchers.append(parsed)

            # Structured voucher data in window.__moduleData__ and lazada_payload
            try:
                raw_mod_vouchers = page.evaluate("""() => {
                    const md = window.__moduleData__ || {};
                    const fields = (md.data && md.data.root && md.data.root.fields) || (md.data && md.data.fields) || {};
                    const res = [];
                    const searchVouchers = (obj) => {
                        if (!obj || typeof obj !== 'object') return;
                        if (Array.isArray(obj)) {
                            obj.forEach(item => searchVouchers(item));
                        } else {
                            if (obj.voucherList && Array.isArray(obj.voucherList)) {
                                obj.voucherList.forEach(v => res.push(v));
                            } else if (obj.promotions && Array.isArray(obj.promotions)) {
                                obj.promotions.forEach(v => res.push(v));
                            } else if (obj.name || obj.title || obj.discountText || obj.amount) {
                                res.push(obj);
                            }
                            for (const k of ['voucher', 'promotions', 'bonusVoucher', 'tradeInfo', 'price']) {
                                if (obj[k]) searchVouchers(obj[k]);
                            }
                        }
                    };
                    searchVouchers(fields);
                    return res;
                }""")
                if isinstance(raw_mod_vouchers, list):
                    for mv in raw_mod_vouchers:
                        if isinstance(mv, dict):
                            v_txt = mv.get("name") or mv.get("title") or mv.get("discountText") or mv.get("voucherText") or ""
                            if v_txt:
                                parsed_mv = _parse_lazada_voucher_text(str(v_txt))
                                if parsed_mv:
                                    candidate_vouchers.append(parsed_mv)
            except Exception:
                pass

            if lazada_payload and isinstance(lazada_payload, dict):
                def _extract_payload_vouchers(obj):
                    if not obj or not isinstance(obj, (dict, list)):
                        return
                    if isinstance(obj, list):
                        for item in obj:
                            _extract_payload_vouchers(item)
                    elif isinstance(obj, dict):
                        v_txt = obj.get("name") or obj.get("title") or obj.get("discountText") or obj.get("voucherText") or ""
                        if v_txt:
                            parsed_pv = _parse_lazada_voucher_text(str(v_txt))
                            if parsed_pv:
                                candidate_vouchers.append(parsed_pv)
                        for val in obj.values():
                            if isinstance(val, (dict, list)):
                                _extract_payload_vouchers(val)
                _extract_payload_vouchers(lazada_payload)

            if name and isinstance(name, str) and any(k in name.lower() for k in ("voucher", "coupon", "mã giảm", "trợ giá")):
                m_tag = re.search(r"\[([^\]]+)\]|\(([^)]+)\)", name)
                tag_txt = (m_tag.group(1) or m_tag.group(2)) if m_tag else ""
                if tag_txt:
                    parsed_tag = _parse_lazada_voucher_text(tag_txt)
                    if parsed_tag:
                        candidate_vouchers.append(parsed_tag)

            if is_subsidized_price:
                # Price already reflects TMALL / MOMCLUB platform subsidy;
                # exclude platform subsidy vouchers to avoid double discount.
                candidate_vouchers = [
                    v for v in candidate_vouchers
                    if v.get("voucher_type") != "platform" or not any(k in str(v.get("voucher_code", "")) for k in ("TMALL", "SUBSIDY", "MOMCLUB"))
                ]
            v_code, v_disc = _find_best_voucher(price, candidate_vouchers)
            if v_code and v_disc > 0:
                voucher_code = v_code
                voucher_discount = v_disc
        except Exception:
            pass

        if price is not None and price > 0:
            if voucher_discount > 0:
                final_price = max(0.0, round(price - voucher_discount, 2))
            else:
                final_price = price
        elif stock is False:
            final_price = 0.0

        try:
            body_txt = page.locator("body").inner_text() if page else ""
            from ..classifier import detect_services_from_text
            detected = detect_services_from_text(body_txt)
            if detected:
                services = ",".join(detected)
            m_orig = re.search(r"(?:xuất xứ|origin)\s*[:\s]\s*([^\n\r,]+)", body_txt, re.IGNORECASE)
            if m_orig:
                origin = m_orig.group(1).strip()
            m_ship = re.search(r"(?:giao từ|gửi từ|nơi gửi hàng|vận chuyển từ)\s*[:\s]\s*([^\n\r,]+)", body_txt, re.IGNORECASE)
            if m_ship:
                ships_from = m_ship.group(1).strip()
            elif "giao từ nước ngoài" in body_txt.lower() or "overseas" in body_txt.lower():
                ships_from = "Nước ngoài"
        except Exception:
            pass

        canonical_url = page.url if page and page.url and "lazada.vn" in page.url else url
        if canonical_url and "/products/" in canonical_url and "-i" in canonical_url:
            canonical_url = canonical_url.split("?")[0]

        if not ships_from:
            ships_from = self._item_locations.get(canonical_url) or self._item_locations.get(url) or ""
        if not ships_from:
            body_lower = body_txt.lower() if body_txt else ""
            shop_lower = shop.lower() if shop else ""
            if any(k in shop_lower for k in ("cửa hàng nước ngoài", "quốc tế", "overseas", "global")) or any(k in body_lower for k in ("cửa hàng nước ngoài", "giao từ nước ngoài", "overseas")):
                ships_from = "Nước ngoài"
            elif any(k in body_lower for k in ("hàng nội địa", "nhà cung cấp địa phương")) or (isinstance(lazada_payload, dict) and "hàng nội địa" in str(lazada_payload).lower()):
                ships_from = "Việt Nam"
            elif isinstance(lazada_payload, dict):
                tracking_core = (lazada_payload.get("root", {}).get("fields", {}).get("tracking", {}).get("core") or {})
                if tracking_core.get("country") == "VN":
                    ships_from = "Việt Nam"

        return Snapshot(
            platform="lazada",
            item_key=self.parse_item_key(canonical_url),
            url=canonical_url,
            name=name or f"Sản phẩm Lazada #{self.parse_item_key(canonical_url)}",
            shop=shop,
            price=price,
            list_price=list_price,
            stock=stock,
            rating=rating,
            sold=sold,
            category=category,
            voucher_code=voucher_code,
            voucher_discount=voucher_discount,
            final_price=final_price,
            origin=origin,
            shop_country=shop_country,
            ships_from=ships_from,
            services=services,
            verified=1,
            variants=extracted_variants,
            sku_from_url=sku_from_url,
        )


    def search(self, keyword: str, limit: int = 5, platform: str = "all", filters: dict | None = None) -> list[str]:
        return self._executor.submit(self._search_sync, keyword, limit, platform, filters).result()

    def _search_sync(self, keyword: str, limit: int = 5, platform: str = "all", filters: dict | None = None) -> list[str]:
        from urllib.parse import quote_plus
        shopee_found: list[str] = []
        lazada_found: list[str] = []

        def _add(url: str):
            clean = url.split("?")[0].strip()
            is_shopee = clean.startswith("https://shopee.vn/") and ("-i." in clean or "/product/" in clean)
            is_lazada = "lazada.vn/products/" in clean and "-i" in clean and ".html" in clean
            if is_shopee and clean not in shopee_found:
                shopee_found.append(clean)
            elif is_lazada and clean not in lazada_found:
                lazada_found.append(clean)

        # 1. Primary: Direct Playwright search
        # 1a. Shopee direct search
        if platform in ("shopee", "all"):
            try:
                self._ensure_started()
                page = self._ctx.new_page()
                _setup_page(page)
                try:
                    search_payload = []
                    def on_resp(r):
                        if "api/v4/search/search_items" in r.url and r.status == 200:
                            try:
                                search_payload.append(r.json())
                            except Exception:
                                pass

                    page.on("response", on_resp)
                    url = f"https://shopee.vn/search?keyword={quote_plus(keyword)}&sortBy=sales"
                    if filters:
                        if filters.get("origin_filter") == "vn" or filters.get("ship_filter") == "vn":
                            url += "&locations=-1"
                        elif filters.get("origin_filter") == "foreign" or filters.get("ship_filter") == "foreign":
                            url += "&locations=-2"
                        if filters.get("shop_filter") == "official":
                            url += "&officialMall=true"
                    page.goto(url, wait_until="domcontentloaded", timeout=15_000)

                    for _ in range(25):
                        if search_payload:
                            break
                        page.wait_for_timeout(100)

                    if not search_payload:
                        page.wait_for_timeout(500)

                    dom_links = page.evaluate(
                        """() => Array.from(document.querySelectorAll('a'))
                            .map(a => a.href || '')
                            .filter(h => h.includes('-i.') || h.includes('/product/'))"""
                    )

                    from ..classifier import is_vietnam_location, is_foreign_location
                    if search_payload:
                        items = search_payload[0].get("items") or []
                        for it in items:
                            sid = it.get("shopid") or (it.get("item_basic") or {}).get("shopid")
                            iid = it.get("itemid") or (it.get("item_basic") or {}).get("itemid")
                            shop_loc = (it.get("item_basic") or {}).get("shop_location") or it.get("shop_location") or ""
                            if filters:
                                sf = filters.get("ship_filter") or filters.get("origin_filter")
                                if sf == "vn" and shop_loc and is_foreign_location(shop_loc):
                                    continue
                                elif sf == "foreign" and shop_loc and is_vietnam_location(shop_loc):
                                    continue
                            if sid and iid:
                                pat = f"-i.{sid}.{iid}"
                                pat2 = f"/{sid}/{iid}"
                                matched = next((dl for dl in dom_links if pat in dl or pat2 in dl), None)
                                target_url = matched if matched else f"https://shopee.vn/product/{sid}/{iid}"
                                if shop_loc:
                                    self._item_locations[target_url.split("?")[0]] = shop_loc
                                _add(target_url)
                                if len(shopee_found) >= limit:
                                    break

                    if len(shopee_found) < limit and not self._is_blocked(page):
                        for dl in dom_links:
                            _add(dl)
                            if len(shopee_found) >= limit:
                                break
                finally:
                    page.close()
            except Exception as exc:
                log.warning("Playwright Shopee search failed for %s: %s", keyword, exc)

        # 1b. Lazada direct search
        if platform in ("lazada", "all"):
            try:
                self._ensure_started()
                page = self._ctx.new_page()
                _setup_page(page)
                self._enable_resource_blocking(page, getattr(self._config, "block_images", False))
                try:
                    url = f"https://www.lazada.vn/catalog/?q={quote_plus(keyword)}"
                    if filters and filters.get("shop_filter") == "official":
                        url += "&service=lazmall"
                    page.goto(url, wait_until="domcontentloaded", timeout=15_000, referer="https://www.lazada.vn/")
                    page.wait_for_timeout(2000)
                    from ..classifier import is_vietnam_location, is_foreign_location
                    lzd_cards = page.evaluate("""() => {
                        const results = [];
                        const seen = new Set();
                        const cards = document.querySelectorAll('[data-qa-locator="product-item"], div[class*="itemCard"], div[class*="card-container"], div[data-item-id]');
                        cards.forEach(c => {
                            const a = c.querySelector("a[href*='/products/']");
                            if (a && a.href) {
                                let clean = a.href.split('?')[0];
                                if (clean && clean.includes('-i') && clean.endsWith('.html') && !seen.has(clean)) {
                                    seen.add(clean);
                                    results.push({
                                        url: clean,
                                        text: c.innerText || ""
                                    });
                                }
                            }
                        });
                        if (results.length === 0) {
                            document.querySelectorAll("a[href*='/products/']").forEach(a => {
                                let clean = (a.href || "").split('?')[0];
                                if (clean && clean.includes('-i') && clean.endsWith('.html') && !seen.has(clean)) {
                                    seen.add(clean);
                                    results.push({ url: clean, text: "" });
                                }
                            });
                        }
                        return results;
                    }""")
                    for card in lzd_cards:
                        c_url = card.get("url") or ""
                        c_text = card.get("text") or ""
                        c_loc = ""
                        lines = [ln.strip() for ln in c_text.replace("|", "\n").splitlines() if ln.strip()]
                        for ln in reversed(lines):
                            if is_vietnam_location(ln) or is_foreign_location(ln):
                                c_loc = ln
                                break

                        if filters:
                            sf = filters.get("ship_filter") or filters.get("origin_filter")
                            if sf == "vn":
                                if is_foreign_location(c_loc) or (c_loc and not is_vietnam_location(c_loc)):
                                    continue
                            elif sf == "foreign":
                                if is_vietnam_location(c_loc) or (c_loc and not is_foreign_location(c_loc)):
                                    continue

                        if c_loc:
                            self._item_locations[c_url] = c_loc
                        _add(c_url)
                        if len(lazada_found) >= limit:
                            break
                finally:
                    page.close()
            except Exception as exc:
                log.warning("Playwright Lazada search failed for %s: %s", keyword, exc)

        def _combine_results() -> list[str]:
            if platform == "shopee":
                return shopee_found[:limit]
            if platform == "lazada":
                return lazada_found[:limit]
            interleaved = []
            for i in range(max(len(shopee_found), len(lazada_found))):
                if i < len(shopee_found):
                    interleaved.append(shopee_found[i])
                if i < len(lazada_found):
                    interleaved.append(lazada_found[i])
            return interleaved

        combined = _combine_results()
        if combined and (platform != "all" or (shopee_found and lazada_found) or len(combined) >= limit):
            return combined[:limit * 2 if platform == "all" else limit]

        # 2. Search engine fallback (Bing + DuckDuckGo)
        import base64
        import re
        import unicodedata
        import urllib.parse
        import urllib.request

        def _remove_accents(s: str) -> str:
            nfkd = unicodedata.normalize("NFKD", s)
            return "".join(c for c in nfkd if not unicodedata.combining(c)).replace("đ", "d").replace("Đ", "D")

        def _decode_bing_u(u_val: str) -> str | None:
            if u_val.startswith("a1"):
                u_val = u_val[2:]
            padded = u_val + "=" * ((4 - len(u_val) % 4) % 4)
            padded = padded.replace("-", "+").replace("_", "/")
            try:
                return base64.b64decode(padded).decode("utf-8", errors="ignore")
            except Exception:
                return None

        norm = _remove_accents(keyword).strip()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        queries = []
        if platform in ("shopee", "all") and not shopee_found:
            queries.extend([f"site:shopee.vn/-i. {norm}", f"site:shopee.vn {norm}"])
        if platform in ("lazada", "all") and not lazada_found:
            queries.extend([f"site:lazada.vn/products/ {norm}", f"site:lazada.vn {norm}"])

        for q in queries:
            bing_url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(q)}"
            try:
                req = urllib.request.Request(bing_url, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    html_text = resp.read().decode("utf-8", errors="ignore")
                    for u in re.findall(r"[?&](?:amp;)?u=(a1[A-Za-z0-9_-]+)", html_text):
                        target = _decode_bing_u(u)
                        if target:
                            _add(target)
            except Exception:
                pass

        ddg_queries = []
        if platform in ("shopee", "all") and not shopee_found:
            ddg_queries.append(f"site:shopee.vn {norm}")
        if platform in ("lazada", "all") and not lazada_found:
            ddg_queries.append(f"site:lazada.vn {norm}")

        for dq in ddg_queries:
            ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(dq)}"
            try:
                req = urllib.request.Request(ddg_url, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    html_text = resp.read().decode("utf-8", errors="ignore")
                    for link_target in re.findall(r"uddg=([^&]+)", html_text):
                        _add(urllib.parse.unquote(link_target))
            except Exception:
                pass

        return _combine_results()[:limit * 2 if platform == "all" else limit]


    def crawl_flash_sale(self, limit: int = 30, platform: str = "shopee") -> list[Snapshot]:
        if platform == "lazada":
            return self.crawl_lazada_flash_sale(limit)
        if platform == "all":
            shopee_snaps = self._executor.submit(self._crawl_flash_sale_sync, limit).result()
            lazada_snaps = self._executor.submit(self._crawl_lazada_flash_sale_sync, limit).result()
            return (shopee_snaps + lazada_snaps)[:limit * 2]
        return self._executor.submit(self._crawl_flash_sale_sync, limit).result()

    def crawl_lazada_flash_sale(self, limit: int = 30) -> list[Snapshot]:
        return self._executor.submit(self._crawl_lazada_flash_sale_sync, limit).result()

    def crawl_tmall_subsidy(self, limit: int = 30, min_price: float = 0.0, max_price: float = float("inf")) -> list[Snapshot]:
        return self._executor.submit(self._crawl_tmall_sync, limit, min_price, max_price).result()

    def _crawl_lazada_flash_sale_sync(self, limit: int = 30) -> list[Snapshot]:
        self._ensure_started()
        page = self._ctx.new_page()
        _setup_page(page)
        self._enable_resource_blocking(page, getattr(self._config, "block_images", False))
        items_raw = []

        def on_resp(res):
            u = res.url.lower()
            if any(k in u for k in ("mtop.lazada", "flashsale", "channel/vn", "getitems", "upr-router")) and res.status == 200:
                try:
                    data = res.json()
                    d = data.get("data") if isinstance(data, dict) else {}
                    if isinstance(d, dict):
                        candidates = d.get("items") or d.get("itemList") or d.get("products") or []
                        if isinstance(candidates, list) and candidates:
                            items_raw.extend(candidates)
                except Exception:
                    pass

        page.on("response", on_resp)
        dom_cards = []
        try:
            page.goto("https://www.lazada.vn/flash-sale/", wait_until="domcontentloaded", timeout=25_000, referer="https://www.lazada.vn/")
            if any(sig in page.url.lower() for sig in ("/punish", "login.lazada.vn", "verify/slider")):
                if not self._wait_for_captcha_solve(page, timeout_sec=15):
                    log.warning("Lazada flash sale blocked by captcha at %s", page.url)
                    return []

            for _ in range(25):
                if len(items_raw) >= limit:
                    break
                page.wait_for_timeout(150)

            # Scroll multiple increments to trigger lazy-loaded flash sale cards
            for _ in range(3):
                try:
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(600)
                except Exception:
                    pass

            dom_cards = page.evaluate("""() => {
                const results = [];
                const links = document.querySelectorAll("a[href*='/products/']");
                const seen = new Set();
                for (const a of links) {
                    let href = a.getAttribute("href") || "";
                    if (href.startsWith("//")) href = "https:" + href;
                    if (!href.startsWith("http")) continue;
                    const cleanUrl = href.split("?")[0];
                    if (seen.has(cleanUrl)) continue;
                    seen.add(cleanUrl);

                    const card = a.closest(".card, [class*='card'], [class*='item'], div") || a;
                    const text = card.innerText || "";
                    if (/đã bán hết|hết hàng|sold out/i.test(text)) continue;

                    results.push({
                        rawUrl: href,
                        cleanUrl: cleanUrl,
                        title: a.getAttribute("title") || "",
                        text: text
                    });
                }
                return results;
            }""")
        except Exception as exc:
            log.warning("Lỗi cào flash sale Lazada: %s", exc)
        finally:
            page.close()

        snapshots = []
        seen_keys = set()

        for it in items_raw:
            if len(snapshots) >= limit:
                break
            if not isinstance(it, dict):
                continue
            sold_percent = it.get("soldPercentage") or it.get("sold_percentage") or 0
            if sold_percent >= 100 or it.get("isSoldOut") or it.get("status") in ("sold_out", "ended"):
                continue
            name = it.get("title") or it.get("name") or ""
            raw_url = it.get("itemUrl") or it.get("productUrl") or it.get("url") or ""
            if raw_url.startswith("//"):
                raw_url = "https:" + raw_url
            if not raw_url and it.get("itemId"):
                raw_url = f"https://www.lazada.vn/products/item-i{it['itemId']}.html"
            if not raw_url or not name:
                continue

            item_key = self.parse_item_key(raw_url)
            if not item_key or item_key in seen_keys:
                continue
            seen_keys.add(item_key)

            price = it.get("salePrice") or it.get("price") or it.get("promoPrice")
            list_price = it.get("originalPrice") or it.get("listPrice")
            if isinstance(price, str):
                price = float(re.sub(r"[^\d.]", "", price.replace(".", "").replace(",", ".")) or 0)
            if isinstance(list_price, str):
                list_price = float(re.sub(r"[^\d.]", "", list_price.replace(".", "").replace(",", ".")) or 0)

            rating = it.get("ratingScore") or it.get("rating")
            sold = it.get("sold") or it.get("orders")

            snapshots.append(Snapshot(
                platform="lazada",
                item_key=item_key,
                url=raw_url,
                name=name,
                shop=it.get("shopName") or "",
                price=float(price) if price else None,
                list_price=float(list_price) if list_price else None,
                stock=True,
                rating=float(rating) if rating else None,
                sold=int(sold) if sold else None,
                category=_infer_category(name),
            ))

        if len(snapshots) < limit and dom_cards:
            for card in dom_cards:
                if len(snapshots) >= limit:
                    break
                clean_url = card.get("cleanUrl") or ""
                raw_url = card.get("rawUrl") or ""
                item_key = self.parse_item_key(clean_url)
                if not item_key or item_key in seen_keys:
                    continue

                text = card.get("text") or ""
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                title = card.get("title") or (lines[0] if lines else "")
                if not title or len(title) < 5:
                    continue

                # Remove title from text to avoid parsing title grams (1400g, 48 hộp) as price
                non_title_text = text.replace(title, "")

                info = {}
                try:
                    parsed = urllib.parse.urlparse(raw_url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    ct_raw = qs.get("clickTrackInfo", [None])[0]
                    if ct_raw:
                        for part in ct_raw.split(";"):
                            if ":" in part:
                                k, v = part.split(":", 1)
                                info[k.strip()] = v.strip()
                except Exception:
                    pass

                price = float(info.get("fs_item_discount_price") or info.get("promo_price") or 0) or None
                list_price = float(info.get("fs_item_price") or 0) or None
                sold = int(info.get("fs_item_sold_cnt") or 0) or None

                if price is None:
                    amounts = []
                    # Strictly require currency symbol ₫ / đ
                    for m in re.finditer(
                        r"(?:₫|đ)\s*([0-9]{1,3}(?:\.[0-9]{3})+|[0-9]{4,})|([0-9]{1,3}(?:\.[0-9]{3})+|[0-9]{4,})\s*(?:\|\s*)?(?:₫|đ)",
                        non_title_text,
                    ):
                        val_str = (m.group(1) or m.group(2)).replace(".", "")
                        try:
                            val = float(val_str)
                            if 1000 <= val <= 1_000_000_000:
                                amounts.append(val)
                        except ValueError:
                            pass
                    price = amounts[0] if amounts else None
                    if len(amounts) > 1 and amounts[1] > (price or 0):
                        list_price = amounts[1]

                # Extract % discount (e.g. -51%, -17%, 25% Off) and infer list_price if missing
                m_disc = re.search(r"[-–—]?\s*([1-9][0-9]?)\s*%\s*(?:off|giảm)?", non_title_text, re.IGNORECASE)
                if m_disc:
                    try:
                        pct = float(m_disc.group(1))
                        if price and (not list_price or list_price <= price):
                            list_price = round(price / (1.0 - (pct / 100.0)), -3)
                    except Exception:
                        pass

                # Extract reviews / sold count (e.g. (1665), (2160), Đã bán 500)
                if not sold:
                    m_sold = re.search(r"\(([0-9]+)\)|(?:đã bán|sold)\s*([0-9.,]+(?:\s*[kK])?)", non_title_text, re.IGNORECASE)
                    if m_sold:
                        raw_cnt = m_sold.group(1) or m_sold.group(2)
                        if "k" in raw_cnt.lower():
                            sold = int(float(raw_cnt.lower().replace("k", "").replace(",", ".")) * 1000)
                        else:
                            sold = int(raw_cnt.replace(".", ""))

                if not price or price < 1000:
                    continue

                seen_keys.add(item_key)
                snapshots.append(Snapshot(
                    platform="lazada",
                    item_key=item_key,
                    url=clean_url,
                    name=title,
                    shop="",
                    price=price,
                    list_price=list_price,
                    stock=True,
                    rating=4.8 if (sold and sold > 50) else None,
                    sold=sold,
                    category=_infer_category(title),
                ))

        if len(snapshots) < limit:
            for s in self._crawl_tmall_sync(limit - len(snapshots)):
                if s.item_key not in seen_keys:
                    seen_keys.add(s.item_key)
                    snapshots.append(s)

        return snapshots[:limit]

    def _crawl_tmall_sync(self, limit: int = 30, min_price: float = 0.0, max_price: float = float("inf")) -> list[Snapshot]:
        self._ensure_started()
        snapshots: list[Snapshot] = []
        seen_keys: set[str] = set()

        try:
            sub_page = self._ctx.new_page()
            _setup_page(sub_page)
            self._enable_resource_blocking(sub_page)
            try:
                sub_page.goto(
                    "https://www.lazada.vn/wow/gcp/lazada/channel/vn/affiliate/hFa6ZXcrph",  # ADR 0070: personalised feed, bot sees its own account's recommendations
                    wait_until="domcontentloaded",
                    timeout=25_000,
                    referer="https://www.lazada.vn/",
                )
                if any(sig in sub_page.url.lower() for sig in ("/punish", "login.lazada.vn", "verify/slider")):
                    if not self._wait_for_captcha_solve(sub_page, timeout_sec=15):
                        log.warning("LazTmall Affiliate channel blocked by captcha at %s", sub_page.url)
                        return []

                try:  # the feed arrives by XHR after domcontentloaded; without this wait the card list is empty
                    sub_page.wait_for_selector("a[href*='/products/']", timeout=12_000)
                except Exception:
                    log.warning("LazTmall Affiliate: no product cards within 12 s at %s", sub_page.url)
                # Scroll down in increments to trigger lazy-loaded campaign cards
                for _ in range(4):
                    try:
                        sub_page.evaluate("window.scrollBy(0, 1500)")
                        sub_page.wait_for_timeout(800)
                    except Exception:
                        pass

                tmall_cards = sub_page.evaluate("""() => {
                    const results = [];
                    const seen = new Set();
                    const aEls = document.querySelectorAll("a[href*='/products/']");
                    for (const a of aEls) {
                        let h = a.getAttribute("href") || "";
                        if (h.startsWith("//")) h = "https:" + h;
                        let clean = h.split("?")[0];
                        if (clean && clean.includes("-i") && clean.endsWith(".html") && !seen.has(clean)) {
                            seen.add(clean);
                            const card = a.closest(".card, [class*='card'], [class*='item'], div") || a;
                            const titleEl = a.querySelector("[class*='productItemTitle'], [class*='title']") || a;
                            const title = titleEl.innerText || a.getAttribute("title") || "";
                            const priceEl = card.querySelector(".lzdPriceDiscountPCV2, .PriceDiscount, [class*='PriceDiscount'], [class*='priceDiscount']");
                            const origEl = card.querySelector(".lzdPriceOriginPCV2, .PriceOrigin, [class*='PriceOrigin'], [class*='originPrice']");
                            results.push({
                                url: clean,
                                title: title,
                                text: card.innerText || "",
                                priceStr: priceEl ? priceEl.innerText : "",
                                origStr: origEl ? origEl.innerText : "",
                            });
                        }
                    }
                    return results;
                }""")

                for tc in tmall_cards:
                    if len(snapshots) >= limit:
                        break
                    c_url = tc.get("url") or tc.get("cleanUrl") or tc.get("rawUrl") or ""
                    if not c_url:
                        continue
                    k = self.parse_item_key(c_url)
                    if not k or k in seen_keys:
                        continue

                    # Extract title
                    raw_title = tc.get("title") or ""
                    if not raw_title or len(raw_title) < 5:
                        lines = [l.strip() for l in (tc.get("text") or "").split("\n") if l.strip()]
                        for l in lines:
                            if len(l) > 10 and not any(ch in l for ch in ("₫", "đ", "%", "Đã bán")):
                                raw_title = l
                                break
                    if not raw_title:
                        continue

                    # 2-layer category filter: only allow Electronics & Accessories
                    is_elec, cat = is_tmall_electronics(raw_title)
                    if not is_elec:
                        continue

                    # Extract price
                    price = None
                    p_str = tc.get("priceStr") or ""
                    if p_str:
                        p_match = re.search(r"([0-9.,]+)", p_str)
                        if p_match:
                            try:
                                price = float(p_match.group(1).replace(".", "").replace(",", ""))
                            except ValueError:
                                pass

                    if price is None:
                        c_text = tc.get("text") or ""
                        p_match = re.search(r"(?:₫|đ)\s*([0-9.,]+)|([0-9.,]+)\s*(?:₫|đ)", c_text)
                        if p_match:
                            try:
                                price = float((p_match.group(1) or p_match.group(2)).replace(".", "").replace(",", ""))
                            except ValueError:
                                pass

                    if price is None or price < 1000:
                        continue
                    if not (min_price <= price <= max_price):
                        continue

                    # Extract list price
                    list_price = None
                    orig_str = tc.get("origStr") or ""
                    if orig_str:
                        orig_match = re.search(r"([0-9.,]+)", orig_str)
                        if orig_match:
                            try:
                                list_price = float(orig_match.group(1).replace(".", "").replace(",", ""))
                            except ValueError:
                                pass
                    if not list_price or list_price <= price:
                        list_price = round(price * 1.5, -3)

                    seen_keys.add(k)
                    display_title = raw_title if raw_title.startswith("[TMALL TRỢ GIÁ]") else f"[TMALL TRỢ GIÁ] {raw_title}"
                    snapshots.append(Snapshot(
                        platform="lazada",
                        item_key=k,
                        url=c_url,
                        name=display_title,
                        shop="LazMall Tmall",
                        price=price,
                        list_price=list_price,
                        stock=True,
                        rating=None,
                        category=cat,
                    ))
                log.info("LazTmall Affiliate: %d cards on page, %d electronics in price range", len(tmall_cards), len(snapshots))
            finally:
                sub_page.close()
        except Exception as e:
            log.warning("LazTmall Affiliate crawl error: %s", e)

        return snapshots[:limit]


    def _crawl_flash_sale_sync(self, limit: int = 30) -> list[Snapshot]:
        self._ensure_started()
        page = self._ctx.new_page()
        _setup_page(page)
        items_raw = []

        def on_resp(res):
            if "flash_sale_batch_get_items" in res.url and res.status == 200:
                try:
                    items_raw.extend(res.json().get("data", {}).get("items", []))
                except Exception:
                    pass

        page.on("response", on_resp)
        try:
            page.goto("https://shopee.vn/flash_sale", wait_until="domcontentloaded", timeout=20_000)
            for _ in range(35):
                if len(items_raw) >= limit:
                    break
                page.wait_for_timeout(150)

            if len(items_raw) < limit:
                try:
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
        except Exception as exc:
            log.warning("Lỗi cào flash sale Shopee: %s", exc)
        finally:
            page.close()

        snapshots = []
        for it in items_raw[:limit]:
            sid = it.get("shopid")
            iid = it.get("itemid")
            if not sid or not iid:
                continue

            # Skip sold-out / out-of-stock flash sale items
            stk = it.get("stock")
            stk_status = it.get("stock_status")
            is_sold_out = it.get("is_sold_out")
            promo_stk = it.get("promo_stock")
            stat = it.get("status")
            if is_sold_out or stk == 0 or stk_status == 2 or (promo_stk is not None and promo_stk == 0) or stat in (2, 3):
                continue

            name = it.get("name") or it.get("promo_name") or ""
            raw_p = it.get("price")
            raw_l = it.get("price_before_discount")
            price = (raw_p / 100000.0) if raw_p and raw_p > 100000 else raw_p
            list_price = (raw_l / 100000.0) if raw_l and raw_l > 100000 else raw_l
            rating = (it.get("item_rating") or {}).get("rating_star")
            sold = it.get("historical_sold")

            cat = _infer_category(name)
            url = f"https://shopee.vn/product/{sid}/{iid}"
            snapshots.append(Snapshot(
                platform="shopee",
                item_key=f"{sid}.{iid}",
                url=url,
                name=name,
                shop="",
                price=price,
                list_price=list_price,
                stock=True,
                rating=rating,
                sold=sold,
                category=cat,
            ))
        return snapshots


def _infer_category(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ("bàn phím", "chuột", "laptop", "macbook", "máy tính", "ram", "ssd", "màn hình", "pc", "vga", "cpu")):
        return "Máy Tính & Laptop"
    if any(k in t for k in ("iphone", "samsung", "xiaomi", "điện thoại", "ốp", "cường lực", "sạc", "cáp", "tai nghe", "type-c", "ipad", "pin dự phòng")):
        return "Điện Thoại & Phụ Kiện"
    if any(k in t for k in ("nồi", "chảo", "nồi chiên", "bếp", "quạt", "máy xay", "máy hút bụi", "ấm", "bình giữ nhiệt", "đèn", "lọc không khí", "kệ", "dao")):
        return "Thiết Bị Gia Dụng"
    if any(k in t for k in ("bao cao su", "kem", "son", "serum", "sữa rửa mặt", "dầu gội", "nước hoa", "dưỡng", "mặt nạ", "chống nắng", "sữa tắm")):
        return "Sức Khỏe & Sắc Đẹp"
    if any(k in t for k in ("áo", "quần", "váy", "đầm", "giày", "dép", "balo", "túi", "mũ", "ví", "thắt lưng", "đồng hồ", "tất", "vớ")):
        return "Thời Trang & Phụ Kiện"
    if any(k in t for k in ("loa", "tivi", "camera", "máy ảnh", "flycam", "mic", "headphone")):
        return "Thiết Bị Điện Tử"
    return "Đời Sống & Tiêu Dùng"


def _clean_price_val(raw_val) -> float | None:
    """Robustly parse numeric price from raw types (float, int, dict, or formatted strings like '357.735 ₫')."""
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)):
        v = float(raw_val)
        return v if 1_000 <= v <= 1_000_000_000 else None
    if isinstance(raw_val, dict):
        if "coupon" in raw_val and isinstance(raw_val["coupon"], dict):
            c_val = raw_val["coupon"].get("priceNumber") or raw_val["coupon"].get("value")
            if c_val is not None:
                c_num = _clean_price_val(c_val)
                if c_num is not None:
                    return c_num
            c_text = raw_val["coupon"].get("priceText") or raw_val["coupon"].get("text")
            if c_text:
                c_num = _clean_price_val(c_text)
                if c_num is not None:
                    return c_num
        for k in ("value", "amount", "price", "salePrice", "promotionPrice", "subsidyPrice"):
            if k in raw_val:
                res = _clean_price_val(raw_val[k])
                if res is not None:
                    return res
        return None
    s = str(raw_val).strip()
    if not s:
        return None
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})+|\d{4,})", s)
    if m:
        try:
            cleaned = m.group(1).replace(".", "").replace(",", "")
            v = float(cleaned)
            if 1_000 <= v <= 1_000_000_000:
                return v
        except Exception:
            pass
    return None


def canonicalize_url(url: str) -> str:
    """Strip SKU / model parameters from Lazada and Shopee URLs to target the base product."""
    if not url:
        return url
    if "lazada.vn" in url and "-i" in url:
        return re.sub(r"(-i\d+)-s\d+(\.html|\?)", r"\1\2", url)
    if "shopee.vn" in url:
        cleaned = re.sub(r"[?&]modelid=\d+", "", url)
        if "?" not in cleaned and "&" in cleaned:
            cleaned = cleaned.replace("&", "?", 1)
        return cleaned.rstrip("?")
    return url


_canonicalize_lazada_url = canonicalize_url


def _find_sku_infos(obj) -> dict:
    """Recursively search for skuInfos dictionary across known Lazada data paths."""
    if not isinstance(obj, dict):
        return {}
    if "skuInfos" in obj and isinstance(obj["skuInfos"], dict) and obj["skuInfos"]:
        return obj["skuInfos"]
    for k in ("skuGalleries", "tradeInfo", "skuBase", "root", "fields", "data", "moduleData"):
        if k in obj and isinstance(obj[k], dict):
            res = _find_sku_infos(obj[k])
            if res:
                return res
    return {}


def _extract_sku_names(obj) -> dict[str, str]:
    """Extract mapping of skuId -> variation title from Lazada skuBase structure."""
    if not isinstance(obj, dict):
        return {}
    val_map: dict[str, str] = {}
    sku_name_map: dict[str, str] = {}

    def _walk(node):
        if not isinstance(node, dict):
            return
        if "properties" in node and isinstance(node["properties"], list):
            for prop in node["properties"]:
                if isinstance(prop, dict) and "values" in prop and isinstance(prop["values"], list):
                    pid = str(prop.get("pid") or "")
                    for val in prop["values"]:
                        if isinstance(val, dict):
                            vid = str(val.get("vid") or "")
                            vname = str(val.get("name") or "").strip()
                            if pid and vid and vname:
                                val_map[f"{pid}:{vid}"] = vname
        if "skus" in node and isinstance(node["skus"], list):
            for sku in node["skus"]:
                if isinstance(sku, dict):
                    sid = str(sku.get("skuId") or sku.get("id") or "")
                    path = str(sku.get("propPath") or "")
                    parts = []
                    if path:
                        for token in path.split(";"):
                            if token in val_map:
                                parts.append(val_map[token])
                    name = " - ".join(parts) if parts else str(sku.get("name") or "")
                    if sid and name:
                        sku_name_map[sid] = name
        for k, v in node.items():
            if isinstance(v, dict):
                _walk(v)
            elif isinstance(v, list) and k in ("skuBase", "productOption"):
                for item in v:
                    if isinstance(item, dict):
                        _walk(item)

    _walk(obj)
    return sku_name_map


def _extract_lazada_dom_price(page) -> float | None:
    """Extract visible promotional or sale price directly from Lazada DOM elements."""
    if not page:
        return None
    try:
        for sel in (
            ".pdp-v2-product-price-content-salePrice-amount",
            "[class*='salePrice-amount']",
            ".pdp-v2-product-price-content-salePrice",
            "[class*='salePrice']",
            ".pdp-mod-product-price-v2",
            ".pdp-v2-product-price-content",
            "[class*='pdp-v2-product-price']",
            ".pdp-price_color_orange",
            ".pdp-price",
            ".notranslate.pdp-price",
            "[class*='pdp-price']",
        ):
            loc = page.locator(sel)
            if loc.count() > 0:
                txt = loc.first.inner_text(timeout=1000)
                m = re.search(r"(?:₫|đ)\s*([0-9.,]+)|([0-9.,]+)\s*(?:₫|đ)|(\d{1,3}(?:\.\d{3})+|\d{4,})", txt)
                if m:
                    match_str = m.group(1) or m.group(2) or m.group(3)
                    val = float(match_str.replace(".", "").replace(",", ""))
                    if 1_000 <= val <= 1_000_000_000:
                        return val
    except Exception:
        pass
    return None


def _extract_shopee_dom_price(page) -> float | None:
    """Extract visible promotional or sale price directly from Shopee DOM elements."""
    if not page:
        return None
    try:
        price_selectors = [
            '[class*="priceSectionPrice"]',
            '[class*="pqTWkA"]',
            '[class*="G27FPf"]',
            '[class*="_1k47d8"]',
            '[class*="IZPeQz"]',
            '.product-price',
        ]
        for p_sel in price_selectors:
            loc = page.locator(p_sel)
            if loc.count() > 0:
                raw = loc.first.inner_text(timeout=1000)
                first_part = raw.split("-")[0]
                m = re.search(r"(\d{1,3}(?:\.\d{3})+|\d{4,})", first_part)
                if m:
                    val = float(m.group(1).replace(".", ""))
                    if 1_000 <= val <= 1_000_000_000:
                        return val
    except Exception:
        pass
    return None


def _parse_lazada_voucher_text(text: str) -> dict | None:
    """Parse voucher details (percentage/amount, min_spend, discount_cap, voucher_type) from text."""
    if not isinstance(text, str):
        return None
    t = text.strip()
    t_lower = t.lower()
    if not t or ("quà tặng" in t_lower and not any(k in t_lower for k in ("giảm", "%", "trợ giá"))):
        return None
    if any(k in t_lower for k in ("vận chuyển", "freeship", "phí ship", "tiết kiệm phí", "combo", "mua kèm")):
        return None
    if re.search(r"mua\s+\d+\s+(?:giảm|tặng|được)", t_lower):
        return None

    DISCOUNT_KEYWORDS = (
        "giảm", "giam", "off", "voucher", "mã", "coupon",
        "hoàn", "hoan", "xu", "coin", "trợ giá", "tro gia",
        "ưu đãi", "uu dai", "tích lũy", "tich luy", "sale",
        "discount", "cashback", "subsidy", "momclub"
    )
    if not any(k in t_lower for k in DISCOUNT_KEYWORDS):
        return None

    # Determine voucher type: coins/cashback vs platform vs shop
    if any(k in t_lower for k in ("xu", "coin")):
        v_type = "coins"
        prefix = "COIN"
    elif any(k in t_lower for k in ("hoàn", "cashback")):
        v_type = "coins"
        prefix = "CASHBACK"
    elif any(k in t_lower for k in ("momclub", "mom club")):
        v_type = "platform"
        prefix = "MOMCLUB"
    elif any(k in t_lower for k in ("trợ giá", "subsidy", "tmall", "siêu trợ giá", "độc quyền")):
        v_type = "platform"
        prefix = "TMALL_SUBSIDY"
    elif any(k in t_lower for k in ("tích lũy", "bonus")):
        v_type = "platform"
        prefix = "BONUS"
    elif any(k in t_lower for k in ("shopee", "mã sàn", "voucher sàn")):
        v_type = "platform"
        prefix = "SHOPEE"
    elif any(k in t_lower for k in ("lazada", "lazmall")):
        v_type = "platform"
        prefix = "LAZADA"
    else:
        v_type = "shop"
        prefix = "LAZADA"

    # Check min spend (e.g. đơn từ 300k, mua từ 199.000₫, đơn tối thiểu 200k, đơn hàng từ 1.000.000₫, cho đơn từ 500k)
    min_spend = 0.0
    m_min = re.search(
        r"(?:đơn\s*(?:hàng\s*)?(?:từ|tối thiểu)|mua\s*từ|từ\s*đơn|cho\s*đơn\s*(?:hàng\s*)?(?:từ|tối thiểu)?|áp\s*dụng\s*(?:cho\s*đơn\s*)?từ)\s*(\d{1,3}(?:\.\d{3})+|\d+)\s*(k|₫|đ)?",
        t,
        re.IGNORECASE,
    )
    if m_min:
        num = m_min.group(1).replace(".", "")
        unit = (m_min.group(2) or "").lower()
        is_k = unit == "k" or "k" in t_lower[m_min.start():m_min.end() + 2]
        min_spend = float(num) * 1000 if is_k else float(num)

    # Check discount cap (e.g. tối đa 30k, max 50k)
    discount_cap = 0.0
    m_cap = re.search(r"(?:giảm\s*)?(?:tối đa|max)\s*(\d{1,3}(?:\.\d{3})+|\d+)\s*(k|₫|đ)?", t, re.IGNORECASE)
    if m_cap:
        num = m_cap.group(1).replace(".", "")
        unit = (m_cap.group(2) or "").lower()
        is_k = unit == "k" or "k" in t_lower[m_cap.start():m_cap.end() + 2]
        discount_cap = float(num) * 1000 if is_k else float(num)

    # Check percentage discount (e.g. 25% Giảm, Giảm 15%, Giảm thêm 5% qua Xu, Hoàn tiền MAX 10%, Trợ giá 50%, Giảm 96%)
    m_pct = re.search(r"(\d{1,2})\s*%", t)
    if m_pct:
        pct = float(m_pct.group(1))
        if 1 <= pct <= 99:
            return {
                "voucher_code": f"{prefix}_{int(pct)}PCT",
                "voucher_type": v_type,
                "discount_percentage": pct,
                "discount_cap": discount_cap,
                "min_spend": min_spend,
            }

    # Check fixed value discount (requires explicit discount/promotion keywords)
    m_fix = re.search(
        r"(?:giảm|voucher|hoàn|tích lũy|ưu đãi|coupon|trợ giá|momclub)\s*(?:thêm\s*)?(\d{1,3}(?:\.\d{3})+|\d+)\s*(k|₫|đ)?",
        t,
        re.IGNORECASE,
    )
    if not m_fix and any(k in t_lower for k in ("voucher", "mã giảm", "coupon", "ưu đãi", "giảm", "hoàn", "trợ giá")):
        m_fix = re.search(r"(?:₫|đ)\s*(\d{1,3}(?:\.\d{3})+|\d+)\s*(k)?", t, re.IGNORECASE)
    if m_fix:
        num_str = m_fix.group(1).replace(".", "")
        unit = (m_fix.group(2) or "").lower()
        is_k = unit == "k" or "k" in t.lower()[m_fix.start():m_fix.end()]
        val = float(num_str) * 1000 if is_k else float(num_str)
        if 1_000 <= val <= 50_000_000:
            return {
                "voucher_code": f"{prefix}_{int(val // 1000)}K" if val >= 1000 else f"VOUCHER_{prefix}",
                "voucher_type": v_type,
                "discount_value": val,
                "discount_cap": 0.0,
                "min_spend": min_spend,
            }

    return None


def _find_best_voucher(price: float | None, vouchers: list[dict], allow_stacking: bool = True) -> tuple[str, float]:
    """Find the highest discount vouchers applicable for the given item price.
    Supports voucher stacking across distinct categories (shop, platform, coins).
    """
    if not price or not vouchers:
        return "", 0.0

    # Group vouchers by category to select the best voucher in each category
    best_by_cat: dict[str, tuple[str, float]] = {}

    for v in vouchers:
        code = v.get("voucher_code")
        if not code:
            continue
        v_type = v.get("voucher_type")
        if not v_type:
            c_upper = str(code).upper()
            if any(k in c_upper for k in ("COIN", "XU", "CASHBACK", "HOAN")):
                v_type = "coins"
            elif any(k in c_upper for k in ("BONUS", "TICH_LUY", "PLATFORM", "LAZADA", "SHOPEE", "TMALL", "MOMCLUB")):
                v_type = "platform"
            else:
                v_type = "shop"

        if v_type == "coins":
            continue  # coins/cashback come back after purchase, they do not lower the price paid

        is_vnd = v.get("is_vnd") or str(code).startswith(("LAZADA", "SHOPEE", "COIN", "CASHBACK", "BONUS", "SHOP", "TITLE", "TMALL", "MOMCLUB"))
        raw_min = float(v.get("min_spend") or 0.0)
        min_spend = raw_min if is_vnd or raw_min < 100_000_000 else raw_min / 100000.0

        if price >= min_spend:
            disc = 0.0
            if v.get("discount_percentage"):
                pct = float(v["discount_percentage"]) / 100.0
                disc = price * pct
                if v.get("discount_cap") and float(v["discount_cap"]) > 0:
                    raw_cap = float(v["discount_cap"])
                    cap = raw_cap if is_vnd or raw_cap < 100_000_000 else raw_cap / 100000.0
                    disc = min(disc, cap)
            elif v.get("discount_value") and float(v["discount_value"]) > 0:
                raw_val = float(v["discount_value"])
                disc = raw_val if is_vnd or raw_val < 100_000_000 else raw_val / 100000.0

            if disc > 0:
                _, cur_best_disc = best_by_cat.get(v_type, ("", 0.0))
                if disc > cur_best_disc:
                    best_by_cat[v_type] = (str(code), disc)

    if not best_by_cat:
        return "", 0.0

    if not allow_stacking or len(best_by_cat) == 1:
        single_best = max(best_by_cat.values(), key=lambda item: item[1])
        return single_best[0], round(single_best[1], 2)

    # Deduplicate identical voucher codes across categories before stacking
    seen_codes = set()
    unique_items = []
    for item in best_by_cat.values():
        if item[0] not in seen_codes:
            seen_codes.add(item[0])
            unique_items.append(item)

    stacked_codes = [item[0] for item in unique_items]
    total_disc = sum(item[1] for item in unique_items)
    total_disc = min(total_disc, price)
    return " + ".join(stacked_codes), round(total_disc, 2)
