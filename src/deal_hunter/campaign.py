"""Sale campaign detection for major Vietnamese eCommerce platforms."""
from datetime import datetime, timedelta, timezone

# Vietnam timezone is UTC+7
VN_TZ = timezone(timedelta(hours=7))


def get_active_campaign(db=None, dt: datetime | None = None) -> str | None:
    """Return the active campaign name or None if no sale is active.

    Priority:
    1. Custom campaigns in DB (if DB provided).
    2. Mega Sale (double day): e.g. 11.11, runs from D-1 18:00 to D+1 23:59.
    3. Payday: 14th 18:00 - 16th 23:59 (Payday 15), 24th 18:00 - 26th 23:59 (Payday 25).
    4. Flash Sale: 0:00-1:59, 9:00-10:59, 12:00-13:59, 21:00-22:59 daily.
    """
    if dt is None:
        dt = datetime.now(VN_TZ)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)

    # 1. Custom DB campaign
    if db is not None and hasattr(db, "get_active_campaign_name"):
        custom = db.get_active_campaign_name(dt)
        if custom:
            return custom

    m = dt.month
    d = dt.day
    h = dt.hour

    # 2. Mega Sale: day m (e.g. 11 for Nov)
    # Starts (m-1) at 18:00 until (m+1) at 23:59
    if (d == m - 1 and h >= 18) or (d == m) or (d == m + 1 and h <= 23):
        return f"{m}.{m} Mega Sale"

    # 3. Payday Sale
    if (d == 14 and h >= 18) or (d == 15) or (d == 16 and h <= 23):
        return "Payday 15"
    if (d == 24 and h >= 18) or (d == 25) or (d == 26 and h <= 23):
        return "Payday 25"

    # 4. Flash Sale: 00:00-01:59, 09:00-10:59, 12:00-13:59, 21:00-22:59
    if h in (0, 1, 9, 10, 12, 13, 21, 22):
        return "Flash Sale"

    return None
