"""Tests for detector.py — pure function tests, no DB needed."""
from deal_hunter.detector import detect, MIN_HISTORY_POINTS
from deal_hunter.models import DealStatus


# ── Helper ───────────────────────────────────────────────────────────────────

def _detect(current, history, list_price=None, in_stock=True, rating=4.5,
            min_discount=0.30, min_rating=4.0):
    return detect(current, history, list_price, in_stock, rating, min_discount, min_rating)


# ── Insufficient history ─────────────────────────────────────────────────────

def test_insufficient_history_when_empty():
    result = _detect(100_000, [])
    assert result.status == DealStatus.INSUFFICIENT_HISTORY
    assert result.disc_hist is None
    assert result.median_30d is None


def test_insufficient_history_when_below_minimum():
    history = [110_000] * (MIN_HISTORY_POINTS - 1)
    result = _detect(100_000, history)
    assert result.status == DealStatus.INSUFFICIENT_HISTORY


def test_just_enough_history():
    history = [100_000] * MIN_HISTORY_POINTS
    result = _detect(100_000, history)
    assert result.status != DealStatus.INSUFFICIENT_HISTORY


# ── Real deal detection ──────────────────────────────────────────────────────

def test_real_deal_detected():
    # price drops 40% below median of 100_000 → qualifies as deal
    history = [100_000] * 5
    result = _detect(60_000, history)
    assert result.status == DealStatus.REAL_DEAL
    assert abs(result.disc_hist - 0.40) < 0.01
    assert result.median_30d == 100_000


def test_real_deal_exactly_at_threshold():
    history = [100_000] * 5
    result = _detect(70_000, history)   # exactly 30% off
    assert result.status == DealStatus.REAL_DEAL


def test_not_a_deal_just_below_threshold():
    history = [100_000] * 5
    result = _detect(71_000, history)   # ~29% off — not enough
    assert result.status == DealStatus.NORMAL


# ── Fake list price (giá gốc ảo) ─────────────────────────────────────────────

def test_fake_list_price_detected():
    # High list_price makes it look like 50% off, but history shows it's always been this price
    history = [100_000] * 5
    result = _detect(90_000, history, list_price=200_000)
    assert result.status == DealStatus.FAKE_LIST_PRICE
    assert result.disc_list is not None and result.disc_list > 0.30
    assert result.disc_hist is not None and result.disc_hist < 0.30


# ── Rating and stock guards ───────────────────────────────────────────────────

def test_low_rating_blocks_deal():
    history = [100_000] * 5
    result = _detect(60_000, history, rating=3.5, min_rating=4.0)
    assert result.status != DealStatus.REAL_DEAL


def test_out_of_stock_blocks_deal():
    history = [100_000] * 5
    result = _detect(60_000, history, in_stock=False)
    assert result.status != DealStatus.REAL_DEAL


def test_unknown_stock_does_not_block_deal():
    history = [100_000] * 5
    result = _detect(60_000, history, in_stock=None)
    assert result.status == DealStatus.REAL_DEAL


def test_unknown_rating_does_not_block_deal():
    history = [100_000] * 5
    result = _detect(60_000, history, rating=None)
    assert result.status == DealStatus.REAL_DEAL


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_median_is_used_not_mean():
    # One extreme outlier should not move the median much
    history = [100_000, 100_000, 100_000, 100_000, 1_000_000]
    result = _detect(60_000, history)
    # median = 100_000, so disc_hist = 40% → real deal
    assert result.status == DealStatus.REAL_DEAL
    assert result.median_30d == 100_000


def test_zero_list_price_does_not_raise():
    history = [100_000] * 5
    result = _detect(60_000, history, list_price=0)
    assert result.disc_list is None   # gracefully handled


def test_disc_hist_returned_in_normal_case():
    history = [100_000] * 5
    result = _detect(90_000, history)
    assert result.status == DealStatus.NORMAL
    assert result.disc_hist is not None
    assert abs(result.disc_hist - 0.10) < 0.01


# ── Price error & Anti-fake tests ───────────────────────────────────────────

def test_check_price_error_genuine():
    from deal_hunter.detector import check_price_error
    is_err, disc = check_price_error(
        current_price=2_000_000,
        baseline=20_000_000,
        name="Laptop Asus Gaming ROG Zephyrus G14",
        min_error_discount=0.65,
    )
    assert is_err is True
    assert disc == 0.90


def test_check_price_error_accessory_filtered():
    from deal_hunter.detector import check_price_error, is_accessory_or_fake
    assert is_accessory_or_fake("Ốp lưng iPhone 15 Pro Max Silicon") is True
    assert is_accessory_or_fake("Cáp sạc Type-C nhanh 65W") is True
    assert is_accessory_or_fake("Laptop Gaming Dell Alienware") is False

    is_err, disc = check_price_error(
        current_price=50_000,
        baseline=1_000_000,
        name="Ốp lưng điện thoại da bò cao cấp",
        min_error_discount=0.65,
    )
    assert is_err is False  # Filtered by accessory detection


def test_check_price_error_small_discount_not_error():
    from deal_hunter.detector import check_price_error
    is_err, disc = check_price_error(
        current_price=6_000_000,
        baseline=10_000_000,
        name="Màn hình Gaming 27 inch 144Hz",
        min_error_discount=0.65,
    )
    assert is_err is False  # 40% discount is a normal deal, not an error


def test_check_price_error_keyboard_accessories_and_ratio_guard():
    from deal_hunter.detector import check_price_error, is_accessory_or_fake

    # Accessory keywords detection
    assert is_accessory_or_fake("Hộp 10 Switch lẻ Outemu Red") is True
    assert is_accessory_or_fake("Set Keycap PBT Retro 134 phím") is True
    assert is_accessory_or_fake("Dụng cụ kẹp nhổ switch và keycap") is True
    assert is_accessory_or_fake("Lọ mỡ bôi trơn Krytox lube switch") is True
    assert is_accessory_or_fake("Pad chuột cỡ lớn 80x30cm") is True
    assert is_accessory_or_fake("Miếng dán feet chuột PTFE") is True
    assert is_accessory_or_fake("Núm xoay kim loại cho phím cơ") is True

    # Price ratio guard: price < 20% of baseline with accessory/unit cues
    assert is_accessory_or_fake("Phiên bản lẻ 1 chiếc", price=30_000, baseline=1_500_000) is True
    assert is_accessory_or_fake("Phụ kiện kèm theo", price=40_000, baseline=1_200_000) is True

    # Legitimate keyboard variation is NOT treated as accessory
    assert is_accessory_or_fake("Bàn phím cơ AULA F75 Trắng Switch Reaper") is False
    assert is_accessory_or_fake("AULA F75 Glacier Blue - Reaper Axis") is False

    # Genuine price error on mechanical keyboard is detected
    is_err, disc = check_price_error(
        current_price=223_000,
        baseline=2_230_000,
        name="Bàn phím cơ không dây AULA F75 (Trắng Switch Reaper)",
        min_error_discount=0.65,
    )
    assert is_err is True
    assert round(disc, 2) == 0.90


def test_bundled_main_device_with_cable_not_treated_as_accessory():
    from deal_hunter.detector import is_accessory_or_fake

    # Charger / power bank bundled with cable is a legitimate main device
    cuktech_v = "[Màn hình tất cả trong một 1,57 inch] Sạc nhanh TỐI ĐA 120W với màn hình dữ liệu trực quan, bao gồm cáp dữ liệu bện C-to-C 1m miễn phí."
    assert is_accessory_or_fake(cuktech_v, price=1_384_000, baseline=2_217_000) is False

    cuktech_bundle = "[Màn hình đa năng 1.57 inch] Bộ sạc 120W + Cáp chuyển đổi thông minh một ra hai số 10"
    assert is_accessory_or_fake(cuktech_bundle, price=1_914_000, baseline=2_217_000) is False

    # Standalone cable even at moderate price is treated as accessory
    assert is_accessory_or_fake("Cáp rời Type-C cho bàn phím cơ", price=300_000, baseline=900_000) is True

