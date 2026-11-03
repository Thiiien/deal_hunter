"""
detector.py — Pure functions only. No DB, no config globals, no side effects.

Scanner calls these functions; it owns DB access and passes data in.
This makes the entire detection algorithm testable with plain Python lists.
"""
from statistics import median

from .models import DealStatus, DetectionResult

MIN_HISTORY_POINTS = 3  # need ≥3 historical prices (≥4 total scans) before concluding


def detect(
    current_price: float,
    history: list[float],  # prior prices in 30-day window, NOT including current
    list_price: float | None,
    in_stock: bool | None,
    rating: float | None,
    min_discount: float,   # fraction, e.g. 0.30 for 30%
    min_rating: float,
) -> DetectionResult:
    """Classify a product snapshot as a deal, fake discount, or normal price.

    Args:
        current_price: price recorded in the current scan
        history:       previous prices in the last 30 days (excluding current)
        list_price:    shop-published "original" price (may be inflated)
        in_stock:      True/False/None(unknown)
        rating:        shop rating or None
        min_discount:  minimum required discount vs 30-day median to call a deal
        min_rating:    minimum required rating to call a deal

    Returns:
        DetectionResult with status and computed metrics
    """
    disc_list = _disc(current_price, list_price)

    if len(history) < MIN_HISTORY_POINTS:
        return DetectionResult(
            status=DealStatus.INSUFFICIENT_HISTORY,
            disc_hist=None,
            disc_list=disc_list,
            median_30d=None,
        )

    med = median(history)
    disc_hist = _disc(current_price, med)

    stock_ok = in_stock is None or in_stock
    rating_ok = rating is None or rating >= min_rating

    if disc_hist is not None and disc_hist >= min_discount and stock_ok and rating_ok:
        return DetectionResult(DealStatus.REAL_DEAL, disc_hist, disc_list, med)

    # Price looks like a big discount vs list_price, but history says otherwise →
    # shop inflated the list_price ("giá gốc ảo")
    if disc_list is not None and disc_list >= min_discount and (
        disc_hist is None or disc_hist < min_discount
    ):
        return DetectionResult(DealStatus.FAKE_LIST_PRICE, disc_hist, disc_list, med)

    return DetectionResult(DealStatus.NORMAL, disc_hist, disc_list, med)


def _disc(current: float, reference: float | None) -> float | None:
    """Discount ratio: 1 - current/reference, or None if reference is invalid."""
    if reference and reference > 0:
        return 1.0 - current / reference
    return None


ACCESSORY_KEYWORDS = (
    "ốp", "case", "bao da", "miếng dán", "kính cường lực",
    "móc khóa", "đặt cọc", "cọc", "pre-order", "combo", "set", "chân đế",
    "giá đỡ", "đầu sạc", "củ sạc", "adapter",
    # Specific cable & strap accessories (avoid bare 'dây' which matches 'không dây' / 'có dây')
    "dây sạc", "dây cáp", "cáp xoắn", "dây đeo", "dây nguồn", "dây nối", "dây thay thế", "dây đồng hồ",
    "cáp sạc", "cáp type-c", "cáp type c", "cáp usb", "cáp hdmi", "cáp chuyển", "cáp",
    # Mechanical keyboard & gaming mouse accessories
    "keycap", "key cap", "nút phím", "switch lẻ", "hộp switch", "pack switch",
    "set switch", "túi switch", "chỉ switch", "puller", "kẹp nhổ", "nhổ keycap",
    "nhổ switch", "lube", "mỡ bôi trơn", "cọ lube",
    "pad chuột", "lót chuột", "bàn di chuột", "miếng lót", "feet", "skates",
    "miếng dán feet", "kê tay", "đệm kê tay", "wrist rest", "núm xoay", "núm phím",
    "túi đựng", "hộp đựng", "bao đựng", "vỏ case", "sticker", "decal",
)


MAIN_DEVICE_CUES = (
    "sạc nhanh", "bộ sạc", "củ sạc", "pin sạc", "sạc dự phòng",
    "tai nghe", "bàn phím", "chuột", "máy", "loa", "laptop",
    "màn hình", "vga", "gpu", "pin", "router", "ổ cứng", "ssd",
)

BUNDLE_CUES = (
    "bao gồm cáp", "kèm cáp", "tặng cáp", "+ cáp", "kèm dây", "tặng dây", "+ dây",
    "bao gồm dây", "kèm sạc", "tặng kèm", "kèm theo",
)


def is_accessory_or_fake(name: str, price: float = 0, baseline: float = 0) -> bool:
    """Return True if product name indicates an accessory, deposit or fake price anomaly."""
    if not name:
        return False
    lower = name.lower()
    import re
    for kw in ACCESSORY_KEYWORDS:
        if re.search(r'(?i)(?:\b|_)' + re.escape(kw) + r'(?:\b|_)', lower):
            # If item is priced substantially (>= 25% of baseline) and is a bundle or mentions a main device cue
            if baseline > 0 and price >= 0.25 * baseline:
                if any(cue in lower for cue in BUNDLE_CUES):
                    continue
                if any(cue in lower for cue in MAIN_DEVICE_CUES) and not re.match(
                    r'^(?:cáp|dây cáp|dây sạc|ốp|miếng dán|kính cường lực)\b', lower.strip()
                ):
                    continue
            return True

    # If item is priced at < 20% of baseline (i.e. > 80% discount vs main product)
    # and has single-unit/accessory cues (e.g. "lẻ", "1 chiếc", "1 cái", "phụ kiện")
    if baseline > 0 and 0 < price < 0.20 * baseline:
        accessory_cues = ("lẻ", "1 chiếc", "1 cái", "phụ kiện", "dùng thử", "hàng thử", "sample")
        for cue in accessory_cues:
            if re.search(r'(?i)(?:\b|_)' + re.escape(cue) + r'(?:\b|_)', lower):
                return True

    return False


def check_price_error(
    current_price: float,
    baseline: float,
    name: str,
    min_error_discount: float = 0.65,
) -> tuple[bool, float]:
    """Check if product snapshot exhibits a severe price error anomaly. Returns (is_error, discount_ratio)."""
    if not current_price or current_price < 1000 or not baseline or baseline <= 0:
        return False, 0.0
    if current_price >= baseline:
        return False, 0.0
    disc = (baseline - current_price) / baseline
    if disc < min_error_discount:
        return False, disc
    if is_accessory_or_fake(name, current_price, baseline):
        return False, disc
    return True, disc
