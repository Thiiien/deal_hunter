"""classifier.py — Pure functions for keyword tracking product evaluation and filtering.

No database dependencies, fully unit-testable.
"""
import re
from typing import Any

VN_LOCATIONS = {
    "việt nam", "vietnam", "vn", "trong nước",
    "hà nội", "ha noi", "hồ chí minh", "ho chi minh", "tp.hcm", "tphcm",
    "thành phố hồ chí minh", "thanh pho ho chi minh",
    "sài gòn", "sai gon", "đà nẵng", "da nang", "hải phòng", "hai phong",
    "cần thơ", "can tho", "bình dương", "binh duong", "đồng nai", "dong nai",
    "bắc ninh", "bac ninh", "quảng ninh", "quang ninh", "thừa thiên huế",
    "huế", "hue", "khánh hòa", "nha trang", "lâm đồng", "đà lạt", "da lat",
    "nghệ an", "vinh", "thanh hóa", "thanh hoa", "nam định", "nam dinh",
    "hải dương", "hai duong", "thái nguyên", "thai nguyen", "vĩnh phúc",
    "vinh phuc", "hưng yên", "hung yen", "bà rịa", "vũng tàu", "vung tau",
    "long an", "tiền giang", "bến tre", "an giang", "kiên giang", "phú quốc",
    "phu quoc", "tây ninh", "bình định", "quy nhơn", "quy nhon", "gia lai",
    "pleiku", "đắk lắk", "dak lak", "đắc lắc", "buôn ma thuột", "bình thuận", "phan thiết",
    "ninh bình", "ninh binh", "vĩnh long", "vinh long", "đồng tháp", "dong thap", "phú thọ", "phu tho"
}

FOREIGN_LOCATIONS = {
    "nước ngoài", "quốc tế", "international", "overseas", "cross-border",
    "trung quốc", "china", "hồng kông", "hong kong", "nhật bản", "japan",
    "hàn quốc", "korea", "south korea", "đài loan", "taiwan", "mỹ", "usa", "thái lan",
    "thailand", "singapore", "malaysia", "indonesia"
}

LAZADA_SERVICES = {
    "sale_cuoi_thang": ("sale cuối tháng", "sale cuoi thang"),
    "lazflash": ("lazflash", "flash sale", "chớp nhoáng"),
    "bundle": ("bundle & save", "bundle and save", "combo tiết kiệm"),
    "fbl": ("xử lý đơn hàng bởi lazada", "fulfilled by lazada", "fbl"),
    "hoa_toc": ("giao hỏa tốc", "hỏa tốc", "instant delivery"),
    "voucher_max": ("voucher max", "voucher tích lũy"),
    "lazmall": ("lazmall", "chính hãng"),
    "tmall": ("tmall", "tmall trợ giá"),
    "mua3": ("mua 3 giảm 20%", "mua 3", "mua 3 giam 20%"),
    "giao_trong_ngay": ("giao trong ngày", "giao trong ngay", "same day delivery"),
    "giao_nhanh_24h": ("giao nhanh 24h", "giao nhanh 24 giờ", "24h delivery"),
    "cod": ("thanh toán khi nhận hàng", "cod", "nhận hàng thanh toán"),
    "freeship": ("freeship", "miễn phí vận chuyển", "free shipping"),
    "xu": ("hoàn xu", "nhận xu", "lazcoins", "xu", "đổi xu"),
}


def is_vietnam_location(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    return any(loc in t for loc in VN_LOCATIONS)


def is_foreign_location(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    return any(loc in t for loc in FOREIGN_LOCATIONS)


def is_keyword_relevant(keyword: str, product_name: str) -> bool:
    """Ensure product name contains keyword tokens (case-insensitive)."""
    if not keyword or not product_name:
        return True
    p_lower = product_name.lower()
    words = [w.strip() for w in keyword.lower().split() if w.strip()]
    return all(w in p_lower for w in words)


def detect_services_from_text(text: str) -> list[str]:
    """Extract matching Lazada service codes from text/badges/DOM."""
    if not text:
        return []
    t = text.lower()
    found = []
    for code, patterns in LAZADA_SERVICES.items():
        if any(pat in t for pat in patterns):
            found.append(code)
    return found


def classify_product(
    snapshot: Any,
    filters: dict[str, Any],
    include_unknown: bool = False,
) -> tuple[bool, int, str]:
    """Classify product snapshot against keyword filters.

    Returns:
        (is_match, verified_flag, reason)
        is_match: True if accepted for tracking, False otherwise.
        verified_flag: 1 if all filters explicitly verified, 0 if some were unknown.
        reason: Plain-text explanation.
    """
    keyword = filters.get("keyword", "")
    if keyword and snapshot.name and not is_keyword_relevant(keyword, snapshot.name):
        return False, 0, f"Tên sản phẩm không khớp từ khóa '{keyword}'"

    origin_filter = filters.get("origin_filter", "default")
    ship_filter = filters.get("ship_filter", "default")
    shop_filter = filters.get("shop_filter", "any")
    services_req = filters.get("services", [])
    if isinstance(services_req, str):
        services_req = [s.strip() for s in services_req.split(",") if s.strip()]

    has_unknown = False

    # 1. Origin Filter
    prod_origin = getattr(snapshot, "origin", "") or ""
    if origin_filter == "vn":
        if is_vietnam_location(prod_origin):
            pass
        elif is_foreign_location(prod_origin):
            return False, 0, f"Xuất xứ không phải Việt Nam ({prod_origin})"
        else:
            has_unknown = True
    elif origin_filter == "foreign":
        if is_foreign_location(prod_origin):
            pass
        elif is_vietnam_location(prod_origin):
            return False, 0, f"Xuất xứ là Việt Nam, không phải nước ngoài ({prod_origin})"
        else:
            has_unknown = True

    # 2. Shipping Filter
    prod_ships = getattr(snapshot, "ships_from", "") or ""
    shop_str = (getattr(snapshot, "shop", "") or "").lower()
    shop_country = getattr(snapshot, "shop_country", "") or ""
    if ship_filter == "vn":
        if is_vietnam_location(prod_ships):
            pass
        elif is_foreign_location(prod_ships):
            return False, 0, f"Vận chuyển từ nước ngoài ({prod_ships})"
        elif is_foreign_location(shop_country) or any(k in shop_str for k in ("cửa hàng nước ngoài", "quốc tế", "overseas", "global")):
            return False, 0, "Shop tại nước ngoài, không phải nội địa Việt Nam"
        elif is_vietnam_location(shop_country) or is_vietnam_location(getattr(snapshot, "origin", "")):
            pass
        else:
            has_unknown = True
    elif ship_filter == "foreign":
        if is_foreign_location(prod_ships):
            pass
        elif is_vietnam_location(prod_ships):
            return False, 0, f"Vận chuyển từ Việt Nam ({prod_ships})"
        elif is_foreign_location(shop_country) or any(k in shop_str for k in ("cửa hàng nước ngoài", "quốc tế", "overseas", "global")):
            pass
        elif is_vietnam_location(shop_country) or is_vietnam_location(getattr(snapshot, "origin", "")):
            return False, 0, "Shop/xuất xứ tại Việt Nam, không phải nước ngoài"
        else:
            has_unknown = True

    # 3. Shop Filter
    prod_country = getattr(snapshot, "shop_country", "") or ""
    if shop_filter == "foreign":
        if is_foreign_location(prod_country) or is_foreign_location(getattr(snapshot, "shop", "")):
            pass
        elif is_vietnam_location(prod_country):
            return False, 0, f"Shop tại Việt Nam, không phải shop nước ngoài"
        else:
            has_unknown = True

    # 4. Services & Promotions Filter (Lazada-specific)
    if services_req:
        if getattr(snapshot, "platform", "") != "lazada":
            # Other platforms don't support Lazada services filter
            has_unknown = True
        else:
            detected_services = getattr(snapshot, "services", "") or ""
            if isinstance(detected_services, str):
                detected_list = [s.strip() for s in detected_services.split(",") if s.strip()]
            else:
                detected_list = list(detected_services)

            # Check combined text if service code is not yet populated
            combined_text = f"{snapshot.name} {detected_services}".lower()
            missing_svcs = []
            for s_code in services_req:
                if s_code in detected_list:
                    continue
                patterns = LAZADA_SERVICES.get(s_code, (s_code,))
                if any(pat in combined_text for pat in patterns):
                    continue
                missing_svcs.append(s_code)
            if missing_svcs:
                return False, 0, f"Dịch vụ/khuyến mãi không khớp: thiếu {', '.join(missing_svcs)}"

    if has_unknown:
        if include_unknown:
            return True, 0, "Chưa rõ một số điều kiện, cần tự kiểm tra"
        else:
            return False, 0, "Thiếu thông tin hoặc chưa rõ điều kiện lọc"

    return True, 1, "Khớp mọi bộ lọc"


# ── TMALL Electronics & Accessories Classification ──────────────────────────

TMALL_REJECT_KEYWORDS = (
    "son", "phấn", "kem", "serum", "dưỡng", "mặt nạ", "tẩy trang", "sữa rửa mặt",
    "nước hoa", "váy", "đầm", "quần", "áo", "tất", "vớ", "ví da", "túi xách",
    "giày", "dép", "bánh", "kẹo", "trà", "cốc", "bình nước", "khăn", "chà lưng",
    "kính áp tròng", "cọ trang điểm", "dầu gội", "sữa tắm", "tã", "bỉm", "rubik",
    "đồ chơi", "mô hình", "nước giặt", "xịt thơm", "bột định hình", "lưỡi dao cạo",
    "chân váy", "thắt lưng", "dây nịt", "ô dù", "bọc đệm", "bông tai", "vòng tay",
    "thẻ quà tặng", "mã nạp", "mã kích hoạt", "cd key"
)

TMALL_ACCESSORY_KEYWORDS = (
    "sạc", "cáp", "tai nghe", "chuột", "bàn phím", "pin dự phòng", "củ sạc",
    "đế sạc", "hub", "adapter", "type-c", "lightning", "usb", "thẻ nhớ", "lót chuột",
    "pad chuột", "keycap", "switch", "ốp", "kính cường lực", "bao da", "dây sạc",
    "giá đỡ điện thoại", "giá đỡ laptop", "túi đựng laptop", "túi chống sốc",
    "nguồn máy tính", "ram", "ssd", "vga", "tản nhiệt", "quạt case"
)

TMALL_DEVICE_KEYWORDS = (
    "điện thoại", "smartphone", "iphone", "samsung", "xiaomi", "redmi", "oppo",
    "máy tính", "laptop", "pc", "macbook", "màn hình", "tivi", "tv", "loa",
    "camera", "webcam", "flycam", "máy ảnh", "máy quay", "máy chiếu",
    "smartwatch", "đồng hồ thông minh", "vòng đeo tay thông minh", "máy chơi game",
    "nintendo", "playstation", "xbox", "quạt tích điện", "quạt cầm tay", "quạt mini",
    "máy sấy tóc", "bàn chải điện", "tai nghe bluetooth", "headphone", "soundbar",
    "amply", "micro", "mic thu âm", "router", "wifi", "bộ phát wifi"
)


def is_tmall_electronics(title: str) -> tuple[bool, str]:
    """Classify if product title belongs to TMALL Electronics or Accessories.

    Returns (True, 'Thiết Bị Điện Tử' | 'Phụ Kiện Điện Tử') or (False, '').
    """
    if not title:
        return False, ""
    t = title.lower()
    if any(rw in t for rw in TMALL_REJECT_KEYWORDS):
        return False, ""
    if any(aw in t for aw in TMALL_ACCESSORY_KEYWORDS):
        return True, "Phụ Kiện Điện Tử"
    if any(dw in t for dw in TMALL_DEVICE_KEYWORDS):
        return True, "Thiết Bị Điện Tử"
    return False, ""
