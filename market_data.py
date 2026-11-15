"""
market_data.py: THE data module. Every market price enters the app here.

This is the ONLY file that knows where prices come from (today: yfinance).
It hands every price to the rest of the app as a Quote, a standard
"price ticket" with the value, unit, source, timestamp and status.

To switch to Bloomberg, ICE or Platts, a desk would rewrite
fetch_yfinance_quote() below so it returns the same Quote tickets.
Nothing else in the project would change.

Try it from the terminal:   python market_data.py
"""

import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

import config


# ---------------------------------------------------------------------------
# The Quote: a standard price ticket
# ---------------------------------------------------------------------------

@dataclass
class Quote:
    """One price, with everything a trader needs to judge it.

    @dataclass is a Python shortcut: it builds a simple container from
    this list of labelled fields, e.g. quote.value, quote.source.
    """
    name: str            # e.g. "Henry Hub"
    value: float | None  # the price, or None if we have no price at all
    unit: str            # e.g. "USD/MMBtu" or "EUR/MWh"
    source: str          # e.g. "yfinance (delayed)"
    timestamp: datetime | None   # when the price was traded (UTC), not when we fetched it
    status: str          # "fresh", "delayed" or "stale"


# ---------------------------------------------------------------------------
# Status light
# ---------------------------------------------------------------------------

def quote_status(timestamp, now=None):
    """Return "fresh", "delayed" or "stale" depending on how old a price is.

    timestamp: when the price was traded (or None if we have no price).
    now: the current time. Normally left empty; tests pass a fixed time.
    """
    if timestamp is None:
        return "stale"

    if now is None:
        now = datetime.now(timezone.utc)

    age_minutes = (now - timestamp).total_seconds() / 60

    if age_minutes < config.FRESH_MAX_MINUTES:
        return "fresh"
    if age_minutes < config.DELAYED_MAX_MINUTES:
        return "delayed"
    return "stale"


# ---------------------------------------------------------------------------
# Fetching from yfinance
# ---------------------------------------------------------------------------

# Memory of the last good price per ticker, so a failed fetch can still
# show the previous value (marked stale) instead of nothing.
# A dictionary: ticker -> Quote
_last_good_quotes = {}


def fetch_yfinance_quote(name, ticker, unit, period="5d", interval="1m",
                         source=config.SOURCE_YFINANCE):
    """Fetch the latest price for one ticker and return it as a Quote.

    By default asks Yahoo for 1-minute bars over the last 5 days and keeps
    the last one (5 days, so we still get Friday's close on a weekend).
    For once-a-day prices like JKM, call it with interval="1d" (daily bars).

    Never crashes: if anything goes wrong, returns the last good price
    marked "stale", or an empty Quote if we never had one.
    """
    try:
        bars = yf.Ticker(ticker).history(period=period, interval=interval)

        if bars.empty:
            raise ValueError(f"no data returned for {ticker}")

        last_price = float(bars["Close"].iloc[-1])           # last row's closing price
        last_time = bars.index[-1].to_pydatetime()           # time of that bar
        last_time = last_time.astimezone(timezone.utc)       # store every time in UTC

        quote = Quote(
            name=name,
            value=last_price,
            unit=unit,
            source=source,
            timestamp=last_time,
            status=quote_status(last_time),
        )
        _last_good_quotes[ticker] = quote    # remember it for next time
        return quote

    except Exception as error:
        # "except" catches any error (no internet, Yahoo down, odd data...)
        print(f"[market_data] could not fetch {ticker}: {error}")

        previous = _last_good_quotes.get(ticker)
        if previous is not None:
            # Keep the old value, but flag it clearly as stale
            return Quote(
                name=previous.name,
                value=previous.value,
                unit=previous.unit,
                source=previous.source,
                timestamp=previous.timestamp,
                status="stale",
            )

        return Quote(name=name, value=None, unit=unit,
                     source=source, timestamp=None, status="stale")


def get_market_prices():
    """Fetch every market price the app needs.

    Returns a dictionary of Quotes:
        {"henry_hub": Quote, "ttf": Quote, "eurusd": Quote, "jkm_settlement": Quote}
    This is the one function the rest of the app calls.
    """
    return {
        "henry_hub": fetch_yfinance_quote("Henry Hub", config.TICKER_HENRY_HUB, "USD/MMBtu"),
        "ttf": fetch_yfinance_quote("TTF", config.TICKER_TTF, "EUR/MWh"),
        "eurusd": fetch_yfinance_quote("EURUSD", config.TICKER_EURUSD, "USD per EUR"),
        # JKM: Yahoo only has daily settlements, so we ask for daily bars over a month
        "jkm_settlement": fetch_yfinance_quote(
            "JKM settlement", config.TICKER_JKM, "USD/MMBtu",
            period="1mo", interval="1d", source=config.SOURCE_YFINANCE_DAILY,
        ),
    }


# ---------------------------------------------------------------------------
# Contract months (V3): the front month and M+1
# ---------------------------------------------------------------------------

def contract_month(today, months_ahead):
    """The (year, month) of the contract `months_ahead` months after today.

    Gas futures roll before the delivery month starts, so in November:
        months_ahead=1 -> December = the FRONT month (the loading month M)
        months_ahead=2 -> January  = M+1 (the delivery month in Europe)
    """
    # Count months from year 0 so that December + 1 rolls into next January.
    # divmod(a, b) gives two answers at once: a // b and a % b.
    month_count = today.year * 12 + (today.month - 1) + months_ahead
    year, month_index = divmod(month_count, 12)
    return year, month_index + 1


def contract_ticker(prefix, year, month):
    """Yahoo ticker of one contract month, e.g. ("TTF", 2027, 1) -> "TTFF27.NYM"."""
    letter = config.MONTH_CODES[month - 1]   # January -> "F", December -> "Z"
    two_digit_year = f"{year % 100:02d}"     # 2027 -> "27", 2030 -> "30"
    return f"{prefix}{letter}{two_digit_year}{config.CONTRACT_SUFFIX}"


def month_label(year, month):
    """Trader-style month name, e.g. (2027, 1) -> "Jan-27"."""
    return datetime(year, month, 1).strftime("%b-%y")


def get_contract_prices(today=None):
    """Fetch the two contract-month prices used for M+1 delivery pricing.

    Returns a dictionary of Quotes:
        {"henry_hub_front": Henry Hub for the loading month (e.g. Dec-26),
         "ttf_m1":          TTF for the delivery month     (e.g. Jan-27)}
    Like every fetch here, a failure gives a red (stale) Quote, never an error.
    today: normally left empty; tests pass a fixed date.
    """
    if today is None:
        today = datetime.now(timezone.utc)

    front_year, front_month = contract_month(today, 1)
    m1_year, m1_month = contract_month(today, 2)

    return {
        "henry_hub_front": fetch_yfinance_quote(
            f"Henry Hub {month_label(front_year, front_month)}",
            contract_ticker(config.CONTRACT_PREFIX_HENRY_HUB, front_year, front_month),
            "USD/MMBtu",
        ),
        "ttf_m1": fetch_yfinance_quote(
            f"TTF {month_label(m1_year, m1_month)}",
            contract_ticker(config.CONTRACT_PREFIX_TTF, m1_year, m1_month),
            "EUR/MWh",
        ),
    }


# ---------------------------------------------------------------------------
# Monthly history (V3): FRED + Yahoo JKM
# ---------------------------------------------------------------------------

@dataclass
class History:
    """A monthly price history: the monthly version of a Quote.

    values is a pandas Series: one price per month, labelled by the first day
    of the month (e.g. 2026-09-01 -> the September 2026 average).
    """
    name: str                # e.g. "Europe gas"
    unit: str                # "USD/MMBtu"
    source: str              # e.g. "FRED (IMF, monthly)"
    fetched_at: datetime     # when we downloaded it (UTC)
    status: str              # "ok" or "failed"
    values: pd.Series        # the monthly prices (empty if the download failed)
    error: str = ""          # what went wrong, if it failed


def failed_history(name, source, error):
    """An empty History marked "failed", so a broken download never crashes the app."""
    print(f"[market_data] could not load {name} history: {error}")
    return History(name=name, unit="USD/MMBtu", source=source,
                   fetched_at=datetime.now(timezone.utc), status="failed",
                   values=pd.Series(dtype=float), error=str(error))


def download_fred_csv(series_id):
    """Download one FRED series as a table (columns: observation_date, <series_id>).

    Kept as its own small function so the tests can replace it with fake data.
    """
    url = config.FRED_CSV_URL + series_id
    # "with" opens the connection and closes it automatically afterwards
    with urllib.request.urlopen(url, timeout=config.HISTORY_TIMEOUT_SECONDS) as response:
        return pd.read_csv(response)


def fetch_fred_monthly(name, series_id):
    """Fetch one monthly FRED series as a History. Never crashes."""
    try:
        table = download_fred_csv(series_id)
        dates = pd.to_datetime(table["observation_date"])
        # FRED marks missing months with "." : errors="coerce" turns those into
        # "not a number", and dropna() removes them
        prices = pd.to_numeric(table[series_id], errors="coerce")
        values = pd.Series(prices.values, index=dates).dropna()
        if values.empty:
            raise ValueError(f"no data in FRED series {series_id}")
        return History(name=name, unit="USD/MMBtu", source=config.SOURCE_FRED,
                       fetched_at=datetime.now(timezone.utc), status="ok", values=values)
    except Exception as error:
        return failed_history(name, config.SOURCE_FRED, error)


def fetch_jkm_monthly(today=None):
    """JKM history: Yahoo's daily settlements averaged by month. Never crashes.

    The current month is left out: it isn't finished, so its average isn't final.
    today: normally left empty; tests pass a fixed date.
    """
    name, source = "JKM", config.SOURCE_YFINANCE_MONTHLY
    if today is None:
        today = datetime.now(timezone.utc)
    try:
        bars = yf.Ticker(config.TICKER_JKM).history(period="max", interval="1d")
        if bars.empty:
            raise ValueError(f"no data returned for {config.TICKER_JKM}")

        daily = bars["Close"]
        daily.index = daily.index.tz_localize(None)   # drop the time zone: we only need the date
        # resample("MS") groups the days by month ("Month Start"), mean() averages each group
        monthly = daily.resample("MS").mean().dropna()

        this_month = pd.Timestamp(today.year, today.month, 1)
        monthly = monthly[monthly.index < this_month]   # finished months only
        return History(name=name, unit="USD/MMBtu", source=source,
                       fetched_at=datetime.now(timezone.utc), status="ok", values=monthly)
    except Exception as error:
        return failed_history(name, source, error)


def get_history():
    """Fetch the three monthly histories the History tab needs.

    Returns a dictionary of History tickets:
        {"europe": Europe gas (FRED), "henry_hub": Henry Hub (FRED), "jkm": JKM (Yahoo)}
    """
    return {
        "europe": fetch_fred_monthly("Europe gas (TTF-based)", config.FRED_SERIES_EUROPE),
        "henry_hub": fetch_fred_monthly("Henry Hub", config.FRED_SERIES_HENRY_HUB),
        "jkm": fetch_jkm_monthly(),
    }


# ---------------------------------------------------------------------------
# Prices that don't come from yfinance
# ---------------------------------------------------------------------------

def manual_quote(name, value, unit, changed_at):
    """Wrap a price the trader typed in (e.g. JKM) as a Quote.

    changed_at: when the trader last changed the value.
    The status light uses the same age rule as market prices, so a manual
    price nobody has updated for over an hour turns red as a reminder.
    (If a desk gets a real JKM feed, e.g. Platts, it replaces this function.)
    """
    return Quote(
        name=name,
        value=value,
        unit=unit,
        source=config.SOURCE_USER,
        timestamp=changed_at,
        status=quote_status(changed_at),
    )


# Order of the lights from best to worst, used to pick the worse of two
STATUS_ORDER = ["fresh", "delayed", "stale"]


def derived_quote(name, value, unit, ingredients):
    """Build a Quote for a price calculated from other Quotes.

    Example: TTF in USD/MMBtu is made from TTF (EUR/MWh) and EURUSD.
    A calculated price is only as good as its worst ingredient, so it takes:
      - the OLDEST timestamp of the ingredients
      - the WORST status light of the ingredients
    """
    timestamps = [q.timestamp for q in ingredients if q.timestamp is not None]
    oldest = min(timestamps) if timestamps else None

    worst_status = "fresh"
    for q in ingredients:
        if STATUS_ORDER.index(q.status) > STATUS_ORDER.index(worst_status):
            worst_status = q.status

    sources = sorted(set(q.source for q in ingredients))   # set() removes duplicates
    return Quote(
        name=name,
        value=value,
        unit=unit,
        source=", ".join(sources) + " (converted)",
        timestamp=oldest,
        status=worst_status,
    )


# ---------------------------------------------------------------------------
# Run this file directly to see live prices in the terminal
# ---------------------------------------------------------------------------

# This block only runs when you type "python market_data.py",
# not when another file imports this one.
if __name__ == "__main__":
    lights = {"fresh": "🟢", "delayed": "🟡", "stale": "🔴"}

    all_quotes = list(get_market_prices().values()) + list(get_contract_prices().values())
    for quote in all_quotes:
        when = quote.timestamp.strftime("%Y-%m-%d %H:%M UTC") if quote.timestamp else "no time"
        value = f"{quote.value:.4f}" if quote.value is not None else "no price"
        print(f"{lights[quote.status]} {quote.name:<16} {value:>10} {quote.unit:<12} "
              f"| {quote.source} | {when}")

    print("\nMonthly history:")
    for history in get_history().values():
        if history.status == "ok":
            first, last = history.values.index[0], history.values.index[-1]
            print(f"✅ {history.name:<24} {len(history.values):>4} months "
                  f"{first:%b-%y} → {last:%b-%y} (last {history.values.iloc[-1]:.2f}) | {history.source}")
        else:
            print(f"❌ {history.name:<24} failed: {history.error}")
