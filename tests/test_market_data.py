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


def make_quote(status, minutes_old):
    """Small helper: build a test Quote with a given status and age."""
    return market_data.Quote(name="X", value=1.0, unit="u", source="yfinance (delayed)",
                             timestamp=NOW - timedelta(minutes=minutes_old), status=status)


def test_derived_quote_takes_oldest_time_and_worst_light():
    ttf = make_quote("fresh", minutes_old=5)
    eurusd = make_quote("delayed", minutes_old=30)

    converted = market_data.derived_quote("TTF", 29.4, "USD/MMBtu", [ttf, eurusd])

    assert converted.timestamp == NOW - timedelta(minutes=30)   # the older one
    assert converted.status == "delayed"                        # the worse one
    assert converted.source == "yfinance (delayed) (converted)"


def test_manual_quote_is_labelled_user_input():
    quote = market_data.manual_quote("JKM", 30.0, "USD/MMBtu", changed_at=datetime.now(timezone.utc))
    assert quote.source == "User input"
    assert quote.status == "fresh"   # just changed


def test_boundaries():
    # Exactly 20 min old is no longer fresh; exactly 60 min old is stale
    assert market_data.quote_status(NOW - timedelta(minutes=20), now=NOW) == "delayed"
    assert market_data.quote_status(NOW - timedelta(minutes=60), now=NOW) == "stale"
