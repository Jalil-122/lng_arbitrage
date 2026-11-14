"""
Tests for the status light in market_data.py.

These don't use the internet: we pass a fixed "now" time,
so the result is always the same.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd

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


class BrokenTicker:
    """A fake yfinance Ticker that always fails, like having no internet."""
    def __init__(self, ticker):
        pass

    def history(self, **kwargs):
        raise ConnectionError("no internet")


def test_failed_fetch_never_crashes(monkeypatch):
    # monkeypatch (a pytest feature) swaps yfinance's Ticker for our broken
    # one, only during this test
    monkeypatch.setattr(market_data.yf, "Ticker", BrokenTicker)
    market_data._last_good_quotes.clear()   # pretend we never had a price

    quote = market_data.fetch_yfinance_quote("Henry Hub", "NG=F", "USD/MMBtu")

    assert quote.value is None
    assert quote.status == "stale"


def test_failed_fetch_keeps_last_good_price_marked_stale(monkeypatch):
    # Pretend an earlier fetch succeeded, 2 minutes ago (so it was fresh)
    market_data._last_good_quotes["NG=F"] = market_data.Quote(
        "Henry Hub", 3.23, "USD/MMBtu", "yfinance (delayed)",
        datetime.now(timezone.utc) - timedelta(minutes=2), "fresh")
    monkeypatch.setattr(market_data.yf, "Ticker", BrokenTicker)

    quote = market_data.fetch_yfinance_quote("Henry Hub", "NG=F", "USD/MMBtu")

    assert quote.value == 3.23          # the old price is kept...
    assert quote.status == "stale"      # ...but clearly flagged red
    market_data._last_good_quotes.clear()


class DailyJkmTicker:
    """A fake yfinance Ticker that returns two daily JKM settlements."""
    def __init__(self, ticker):
        pass

    def history(self, **kwargs):
        dates = pd.to_datetime(["2026-11-12", "2026-11-13"]).tz_localize("America/New_York")
        return pd.DataFrame({"Close": [31.365, 31.351]}, index=dates)


def test_daily_jkm_settlement_takes_last_day(monkeypatch):
    monkeypatch.setattr(market_data.yf, "Ticker", DailyJkmTicker)

    quote = market_data.fetch_yfinance_quote(
        "JKM settlement", "JKM=F", "USD/MMBtu",
        period="1mo", interval="1d", source="yfinance (daily settlement)",
    )

    assert quote.value == 31.351                         # the latest settlement
    assert quote.source == "yfinance (daily settlement)"
    assert quote.timestamp.date().isoformat() == "2026-11-13"
    assert quote.status == "stale"                       # a day-old price is always red
    market_data._last_good_quotes.clear()


def test_boundaries():
    # Exactly 20 min old is no longer fresh; exactly 60 min old is stale
    assert market_data.quote_status(NOW - timedelta(minutes=20), now=NOW) == "delayed"
    assert market_data.quote_status(NOW - timedelta(minutes=60), now=NOW) == "stale"
