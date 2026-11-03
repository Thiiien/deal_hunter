from datetime import datetime, timezone

from .db import DB

_RESEND_HOURS = 24
_RESEND_DROP = 0.05   # resend if price drops ≥5% below last alert price


class Alerter:
    """Decides whether to send a deal alert and records it to prevent duplicates."""

    def __init__(self, db: DB):
        self._db = db

    def should_alert(self, product_id: int, current_price: float) -> bool:
        row = self._db.get_alert(product_id)
        if row is None:
            return True
        last_price, sent_at_str = row["last_price"], row["sent_at"]
        sent_at = datetime.fromisoformat(sent_at_str).replace(tzinfo=timezone.utc)
        hours_since = (datetime.now(timezone.utc) - sent_at).total_seconds() / 3600
        if hours_since >= _RESEND_HOURS:
            return True
        if last_price > 0 and (last_price - current_price) / last_price >= _RESEND_DROP:
            return True
        return False

    def record(self, product_id: int, price: float):
        self._db.upsert_alert(product_id, price)
