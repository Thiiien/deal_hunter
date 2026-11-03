from datetime import datetime
import logging

import httpx

from .config import Config
from .notifier import Notifier

log = logging.getLogger(__name__)

_NOPECHA_STATUS_URL = "https://api.nopecha.com/status"
_DEFAULT_FREE_DAILY_LIMIT = 10  # 10 free solves/day for NopeCHA extension free tier


class QuotaMonitor:
    """Checks NopeCHA credit balance and activates circuit-breaker when exhausted."""

    def __init__(self, config: Config, notifier: Notifier, db=None):
        self._key = config.nopecha_api_key
        self._notifier = notifier
        self._db = db
        self._exhausted = False
        self._free_limit = _DEFAULT_FREE_DAILY_LIMIT
        self._mem_solves = 0
        self._mem_date = datetime.now().strftime("%Y-%m-%d")

    @property
    def is_exhausted(self) -> bool:
        return self._exhausted

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def get_daily_solves(self) -> int:
        today = self._today()
        if self._db is not None:
            try:
                val = self._db.get_setting(f"captcha_solves_{today}")
                if val and str(val).strip():
                    return int(val)
            except Exception as exc:
                log.warning("Failed to get daily captcha count from DB: %s", exc)
        if self._mem_date != today:
            self._mem_date = today
            self._mem_solves = 0
        return self._mem_solves

    def record_solve(self, count: int = 1) -> int:
        """Record successful captcha solve."""
        today = self._today()
        new_count = self.get_daily_solves() + count
        if self._db is not None:
            try:
                self._db.set_setting(f"captcha_solves_{today}", str(new_count))
            except Exception as exc:
                log.warning("Failed to record daily captcha count in DB: %s", exc)
        if self._mem_date != today:
            self._mem_date = today
        self._mem_solves = new_count
        log.info("Recorded captcha solve today: %d (free limit: %d)", new_count, self._free_limit)
        if not self._key and new_count >= self._free_limit:
            self._exhausted = True
        return new_count

    def get_remaining_credits(self) -> int:
        """Returns remaining credits (API credits or remaining free daily quota)."""
        if self._key:
            res = self.check()
            return res if res is not None else 0
        solves = self.get_daily_solves()
        return max(0, self._free_limit - solves)

    def check(self) -> int | None:
        """Query NopeCHA API. Returns remaining credits or None if key not set."""
        if not self._key:
            rem = self.get_remaining_credits()
            if rem == 0:
                self._exhausted = True
            return None
        try:
            resp = httpx.get(_NOPECHA_STATUS_URL, params={"key": self._key}, timeout=10)
            credits_left = resp.json().get("data", {}).get("credit", 0)
        except Exception as exc:
            log.warning("NopeCHA status check failed: %s", exc)
            return None

        if credits_left == 0:
            self._exhausted = True

        log.info("NopeCHA credits remaining: %d", credits_left)
        return credits_left

    def mark_exhausted(self):
        """Call when a captcha solve fails mid-scan (quota ran out between checks)."""
        self._exhausted = True
        log.info("NopeCHA quota marked as exhausted")

    def reset(self):
        """Call at the start of a new day or after admin confirms recharge."""
        self._exhausted = False
