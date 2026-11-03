"""Tests for campaign detection."""
from datetime import datetime

from deal_hunter.campaign import VN_TZ, get_active_campaign


def test_mega_sale_double_day():
    dt = datetime(2026, 11, 11, 12, 0, tzinfo=VN_TZ)
    assert get_active_campaign(dt=dt) == "11.11 Mega Sale"


def test_mega_sale_eve():
    dt = datetime(2026, 11, 10, 19, 0, tzinfo=VN_TZ)
    assert get_active_campaign(dt=dt) == "11.11 Mega Sale"


def test_payday_15():
    dt = datetime(2026, 10, 15, 14, 0, tzinfo=VN_TZ)
    assert get_active_campaign(dt=dt) == "Payday 15"


def test_payday_25():
    dt = datetime(2026, 10, 25, 10, 0, tzinfo=VN_TZ)
    assert get_active_campaign(dt=dt) == "Payday 25"


def test_flash_sale_normal_day():
    # 18th is neither double day nor payday
    dt = datetime(2026, 10, 18, 9, 30, tzinfo=VN_TZ)
    assert get_active_campaign(dt=dt) == "Flash Sale"


def test_normal_time():
    # 18th at 15:00 is normal time
    dt = datetime(2026, 10, 18, 15, 0, tzinfo=VN_TZ)
    assert get_active_campaign(dt=dt) is None
