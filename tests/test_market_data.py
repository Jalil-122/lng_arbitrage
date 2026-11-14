"""
Tests for the status light in market_data.py.

These don't use the internet: we pass a fixed "now" time,
so the result is always the same.
"""

from datetime import datetime, timedelta, timezone

import market_data

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)   # a fixed "current time"


def test_recent_price_is_fresh():
    traded = NOW - timedelta(minutes=5)
    assert market_data.quote_status(traded, now=NOW) == "fresh"


def test_half_hour_old_price_is_delayed():
    traded = NOW - timedelta(minutes=30)
    assert market_data.quote_status(traded, now=NOW) == "delayed"


def test_two_hour_old_price_is_stale():
    traded = NOW - timedelta(hours=2)
    assert market_data.quote_status(traded, now=NOW) == "stale"


def test_missing_price_is_stale():
    assert market_data.quote_status(None, now=NOW) == "stale"


def test_boundaries():
    # Exactly 20 min old is no longer fresh; exactly 60 min old is stale
    assert market_data.quote_status(NOW - timedelta(minutes=20), now=NOW) == "delayed"
    assert market_data.quote_status(NOW - timedelta(minutes=60), now=NOW) == "stale"
