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

from dataclasses import dataclass
from datetime import datetime, timezone

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

    for quote in get_market_prices().values():
        when = quote.timestamp.strftime("%Y-%m-%d %H:%M UTC") if quote.timestamp else "no time"
        value = f"{quote.value:.4f}" if quote.value is not None else "no price"
        print(f"{lights[quote.status]} {quote.name:<10} {value:>10} {quote.unit:<12} "
              f"| {quote.source} | {when}")
