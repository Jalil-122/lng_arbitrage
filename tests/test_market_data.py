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


# ---------------------------------------------------------------------------
# Contract months (V3, M+1 pricing)
# ---------------------------------------------------------------------------

def test_spec_example_14_november_2026():
    # SPEC 13.7: on 14 Nov 2026, front = TTFZ26.NYM (Dec-26), M+1 = TTFF27.NYM (Jan-27)
    today = datetime(2026, 11, 14)
    front = market_data.contract_month(today, 1)
    m1 = market_data.contract_month(today, 2)
    assert front == (2026, 12)
    assert m1 == (2027, 1)
    assert market_data.contract_ticker("TTF", *front) == "TTFZ26.NYM"
    assert market_data.contract_ticker("TTF", *m1) == "TTFF27.NYM"
    assert market_data.contract_ticker("NG", *front) == "NGZ26.NYM"


def test_december_rolls_into_next_year():
    # In December, the front month is already January and M+1 is February
    today = datetime(2026, 12, 3)
    assert market_data.contract_month(today, 1) == (2027, 1)
    assert market_data.contract_month(today, 2) == (2027, 2)


def test_every_month_letter():
    # January F ... December Z: the 12 standard futures letters, in order
    letters = [market_data.contract_ticker("NG", 2027, month)[2] for month in range(1, 13)]
    assert "".join(letters) == "FGHJKMNQUVXZ"


def test_month_label():
    assert market_data.month_label(2027, 1) == "Jan-27"
    assert market_data.month_label(2026, 12) == "Dec-26"


class RecordingTicker:
    """A fake yfinance Ticker that remembers which tickers were asked for."""
    asked = []

    def __init__(self, ticker):
        RecordingTicker.asked.append(ticker)

    def history(self, **kwargs):
        dates = pd.to_datetime(["2026-11-13 11:33"]).tz_localize("America/New_York")
        return pd.DataFrame({"Close": [90.781]}, index=dates)


def test_contract_prices_ask_for_the_right_contracts(monkeypatch):
    monkeypatch.setattr(market_data.yf, "Ticker", RecordingTicker)
    RecordingTicker.asked = []

    quotes = market_data.get_contract_prices(today=datetime(2026, 11, 14))

    assert RecordingTicker.asked == ["NGZ26.NYM", "TTFF27.NYM"]
    assert quotes["henry_hub_front"].name == "Henry Hub Dec-26"
    assert quotes["ttf_m1"].name == "TTF Jan-27"
    assert quotes["ttf_m1"].unit == "EUR/MWh"
    market_data._last_good_quotes.clear()


def test_contract_prices_offline_are_red_not_errors(monkeypatch):
    # SPEC 13.4: if the M+1 contract has no data, its quote is red (stale)
    monkeypatch.setattr(market_data.yf, "Ticker", BrokenTicker)
    market_data._last_good_quotes.clear()

    quotes = market_data.get_contract_prices(today=datetime(2026, 11, 14))

    assert quotes["ttf_m1"].value is None
    assert quotes["ttf_m1"].status == "stale"


# ---------------------------------------------------------------------------
# Monthly history (V3): tested offline with fake downloads
# ---------------------------------------------------------------------------

def fake_fred_csv(series_id):
    """A fake FRED download: three months, one of them missing (".")."""
    return pd.DataFrame({
        "observation_date": ["2026-07-01", "2026-08-01", "2026-09-01"],
        series_id: ["11.50", ".", "12.25"],
    })


def test_fred_history_reads_months_and_skips_missing(monkeypatch):
    monkeypatch.setattr(market_data, "download_fred_csv", fake_fred_csv)

    history = market_data.fetch_fred_monthly("Europe gas", "PNGASEUUSDM")

    assert history.status == "ok"
    assert history.source == "FRED (IMF, monthly)"
    assert list(history.values) == [11.50, 12.25]          # August (".") is skipped
    assert history.values.index[-1] == pd.Timestamp("2026-09-01")


def broken_download(series_id):
    raise ConnectionError("no internet")


def test_fred_failure_never_crashes(monkeypatch):
    monkeypatch.setattr(market_data, "download_fred_csv", broken_download)

    history = market_data.fetch_fred_monthly("Henry Hub", "PNGASUSUSDM")

    assert history.status == "failed"
    assert history.values.empty
    assert "no internet" in history.error


class DailyJkmHistoryTicker:
    """A fake Yahoo JKM: 2 days in September, 3 in October, 1 in November."""
    def __init__(self, ticker):
        pass

    def history(self, **kwargs):
        dates = pd.to_datetime(["2026-09-29", "2026-09-30",
                                "2026-10-01", "2026-10-02", "2026-10-30",
                                "2026-11-02"]).tz_localize("America/New_York")
        return pd.DataFrame({"Close": [10.0, 12.0, 20.0, 21.0, 25.0, 30.0]}, index=dates)


def test_jkm_monthly_average_by_hand(monkeypatch):
    monkeypatch.setattr(market_data.yf, "Ticker", DailyJkmHistoryTicker)

    history = market_data.fetch_jkm_monthly(today=datetime(2026, 11, 15))

    # By hand: September (10 + 12) / 2 = 11.0 ; October (20 + 21 + 25) / 3 = 22.0
    # November is not finished on 15 Nov, so it is left out
    assert history.status == "ok"
    assert list(history.values.index) == [pd.Timestamp("2026-09-01"), pd.Timestamp("2026-10-01")]
    assert list(history.values) == [11.0, 22.0]


def test_jkm_history_failure_never_crashes(monkeypatch):
    monkeypatch.setattr(market_data.yf, "Ticker", BrokenTicker)

    history = market_data.fetch_jkm_monthly()

    assert history.status == "failed"
    assert history.values.empty


def test_boundaries():
    # Exactly 20 min old is no longer fresh; exactly 60 min old is stale
    assert market_data.quote_status(NOW - timedelta(minutes=20), now=NOW) == "delayed"
    assert market_data.quote_status(NOW - timedelta(minutes=60), now=NOW) == "stale"
