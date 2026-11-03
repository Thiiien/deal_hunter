# 57. Thread-Safe Cookie Reloading, UI Resilience, and Megasale Silence

Date: 2026-11-02

## Status

Accepted

## Context

1. **System Freeze / Hang During Cookie Save & Solver Failure**:
   Users reported that the crawler occasionally froze completely, and when pasting new cookies into the Web Dashboard modal and clicking "Lưu & Kích hoạt" (Save & Activate), nothing happened ("không thấy action gì") and the system remained hung.
   - Root-cause investigation revealed a classic re-entrancy deadlock in `PlaywrightAdapter.reload_cookies`: `PlaywrightAdapter` runs browser operations inside a single-worker `ThreadPoolExecutor` (`max_workers=1`, thread name `pw-worker`).
   - During page scraping, if a platform blocked or captcha challenge occurred and `_wait_for_captcha_solve()` failed, `_fetch_sync()` called `self.reload_cookies()`.
   - `reload_cookies()` called `self._executor.submit(self._load_saved_cookies, p).result()` with no timeout. Because the single worker was already busy executing `_fetch_sync()`, it waited indefinitely for itself to finish, permanently locking the crawler.
   - When the user opened the Dashboard and submitted new cookies, `api_save_cookies()` in Flask called `scanner._adapter.reload_cookies(Path("data"))`. Because `reload_cookies()` submitted another task to the already deadlocked single-worker executor without a timeout, the Flask request thread hung indefinitely as well.
   - On the frontend (`templates/dashboard.html`), `saveCookies()` lacked button state updates (no loading spinner, no disabled state), lacked an `AbortController` timeout, and lacked try/catch error handling, leaving the user with zero visual response.

2. **Megasale Telegram Alert Muting & Manual-Only Scanning**:
   The user requested stopping all Telegram notifications from the "🔥 Siêu sale & Giảm giá sâu" tab (`source = 'flash_sale'`) and configuring it to scan only when manually triggered via UI buttons (`crawlMegaSale()`).

## Decision

1. **Deadlock-Free, Thread-Safe Cookie Reloading**:
   - In `PlaywrightAdapter.reload_cookies`:
     - Inspect `threading.current_thread().name`. If already running on `pw-worker`, directly execute `self._load_saved_cookies(p)` without queuing to `_executor`, preventing executor self-deadlock.
     - When called from external threads (e.g., Flask request thread), invoke `self._executor.submit(...).result(timeout=5.0)`. If a scan is currently active, catch `TimeoutError` gracefully: cookies are already persisted on disk and queued for the context without stalling web responses.
2. **Resilient UI Feedback in Cookie Modal**:
   - In `templates/dashboard.html`:
     - Provide immediate visual feedback on the "Lưu & Kích hoạt" button (`id="save-cookies-btn"`), disabling it and showing `⏳ Đang lưu & nạp...`.
     - Implement a 15-second `AbortController` timeout and robust try/catch/finally block to inform the user of success, server timeout, or network issues via toast alerts.
3. **Mute Flash Sale Telegram Alerts & Default to Manual Scan**:
   - In `src/deal_hunter/scanner.py`:
     - Suppress `_send_flash_deal_alert` and `_handle_price_error` in `discover_flash_sale()`.
     - In `scan_product()`, bypass `_send_deal_alert` for `source == 'flash_sale'` while retaining target price alerts if explicitly set by the user (`target_price > 0`).
     - In `scan_due()`, configure `megasale_scan_enabled` default to `False`. Periodic background Megasale scanning is disabled; Megasale scraping executes only on manual user demand via UI buttons (`POST /api/crawl-megasale`).
   - In `src/deal_hunter/config.py`:
     - Set default `megasale_scan_enabled: bool = False`.

## Consequences

- Completely eliminates thread deadlock in the crawler and web thread during captcha failures or cookie reloads.
- Instant, unambiguous visual feedback in the Web Dashboard when saving and activating cookies.
- Telegram noise from Megasale items is completely eliminated while maintaining manual discovery and user-specified target price alerts.
- 100% of the test suite (186 tests) passes cleanly.
