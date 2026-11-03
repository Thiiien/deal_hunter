"""Shared fixtures for all tests."""
import pytest
from deal_hunter.config import Config
from deal_hunter.db import DB


@pytest.fixture
def config():
    return Config(
        db_path=":memory:",
        fetch_mode="mock",
        deal_min_discount=30.0,
        deal_min_rating=4.0,
        deal_min_original_price=0.0,
        scan_interval_min=30,
        request_delay_sec=0.0,   # no sleep in tests
    )


@pytest.fixture
def db():
    d = DB(":memory:")
    yield d
    d.close()
