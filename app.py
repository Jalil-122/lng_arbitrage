"""
app.py: the dashboard screens (Streamlit).

This file only DISPLAYS things. It:
  1. gets live prices from market_data.py
  2. reads the trader's inputs from the sidebar
  3. runs the formulas in arb_calc.py
  4. shows the answer
  5. logs each price refresh to data/arb_log.csv (via arb_log.py)

Run it with:   streamlit run app.py

How Streamlit works: every time you change an input, Streamlit re-runs
this whole file from top to bottom and redraws the page.
"""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import arb_calc
import arb_log
import config
import market_data


# ---------------------------------------------------------------------------
# Page setup (must be the first Streamlit command)
# ---------------------------------------------------------------------------

st.set_page_config(page_title="LNG Arb: Sabine Pass", page_icon="🚢", layout="wide")


# ---------------------------------------------------------------------------
# 1. Live prices
# ---------------------------------------------------------------------------

# @st.cache_data keeps the result in memory for a while (ttl = "time to live").
# Without it, every click in the sidebar would re-download prices from Yahoo.
# It expires 10 seconds BEFORE the 5-minute auto refresh, so each timer tick
# is sure to find the old prices expired and fetch new ones.
@st.cache_data(ttl=config.REFRESH_SECONDS - 10)
def load_market_prices():
    """Fetch HH, TTF and EURUSD (cached for 5 minutes).

    Returns two things: (the prices, the time we fetched them).
    The fetch time lets us log exactly one row per real refresh.
    """
    return market_data.get_market_prices(), datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 2. Sidebar: the trader's inputs
# ---------------------------------------------------------------------------

def sidebar_inputs():
    """Draw the sidebar and return every input in a dictionary (USD/MMBtu)."""
    sb = st.sidebar   # shorter name for the sidebar

    sb.header("Inputs")

    if sb.button("🔄 Refresh prices now"):
        st.cache_data.clear()   # forget the cached prices, so they're fetched again

    sb.subheader("Asia price")
    jkm = sb.number_input("JKM front month", min_value=0.0,
                          value=config.DEFAULT_JKM, step=config.INPUT_STEP, format="%.2f")

    sb.subheader("Freight (Sabine Pass →)")
    freight_nwe = sb.number_input("North-West Europe", min_value=0.0,
                                  value=config.DEFAULT_FREIGHT_NWE, step=config.INPUT_STEP, format="%.2f")
    freight_panama = sb.number_input("North Asia via Panama", min_value=0.0,
                                     value=config.DEFAULT_FREIGHT_PANAMA, step=config.INPUT_STEP, format="%.2f")
    freight_cape = sb.number_input("North Asia via Cape", min_value=0.0,
                                   value=config.DEFAULT_FREIGHT_CAPE, step=config.INPUT_STEP, format="%.2f")
    panama_unavailable = sb.toggle("Panama Canal unavailable",
                                   value=not config.DEFAULT_PANAMA_AVAILABLE)

    sb.subheader("Fees")
    liquefaction_fee = sb.number_input("Liquefaction fee", min_value=0.0,
                                       value=config.DEFAULT_LIQUEFACTION_FEE, step=config.INPUT_STEP, format="%.2f")
    regas_europe = sb.number_input("Regas: Europe", min_value=0.0,
                                   value=config.DEFAULT_REGAS_EUROPE, step=config.INPUT_STEP, format="%.2f")
    regas_asia = sb.number_input("Regas: Asia", min_value=0.0,
                                 value=config.DEFAULT_REGAS_ASIA, step=config.INPUT_STEP, format="%.2f")

    sb.subheader("Decision")
    threshold = sb.number_input("Indifference threshold", min_value=0.0,
                                value=config.DEFAULT_INDIFFERENCE_THRESHOLD, step=config.INPUT_STEP, format="%.2f")

    sb.caption("All values in USD/MMBtu.")

    return {
        "jkm": jkm,
        "freight_nwe": freight_nwe,
        "freight_panama": freight_panama,
        "freight_cape": freight_cape,
        "panama_available": not panama_unavailable,
        "liquefaction_fee": liquefaction_fee,
        "regas_europe": regas_europe,
        "regas_asia": regas_asia,
        "threshold": threshold,
    }


# ---------------------------------------------------------------------------
# 3. Verdict banner
# ---------------------------------------------------------------------------

BANNER_COLOURS = {"lift": "#1e7b34", "cancel": "#b3261e", "indifferent": "#5f6368"}  # green, red, grey


def show_banner(text, colour):
    """Draw a big coloured box with white text across the top of the page."""
    st.markdown(
        f"""<div style="background:{colour}; color:white; padding:18px 24px;
                        border-radius:8px; font-size:28px; font-weight:700;">
                {text}
            </div>""",
        unsafe_allow_html=True,   # allows our small bit of HTML styling
    )


def show_verdict(result, threshold):
    """Turn the calculation result into one clear sentence in a coloured banner."""
    if result["decision"] == "CANCEL":
        text = (f"CANCEL: best netback {dollars(result['best_netback'])} "
                f"does not cover 115% HH (${result['fob_variable']:.2f})")
        show_banner(text, BANNER_COLOURS["cancel"])

    elif result["winner"] == "Indifferent":
        text = (f"LIFT → INDIFFERENT: spread ${abs(result['spread']):.2f}/MMBtu "
                f"is below the ${threshold:.2f} threshold")
        show_banner(text, BANNER_COLOURS["indifferent"])

    elif result["winner"] == "Asia":
        text = (f"LIFT → ASIA, wins by ${abs(result['spread']):.2f}/MMBtu "
                f"(via {result['asia_route']})")
        show_banner(text, BANNER_COLOURS["lift"])

    else:  # Europe
        text = f"LIFT → EUROPE, wins by ${abs(result['spread']):.2f}/MMBtu"
        show_banner(text, BANNER_COLOURS["lift"])

    # One line of key numbers under the banner
    st.caption(f"Netback Europe {dollars(result['netback_europe'])} · "
               f"Netback Asia {dollars(result['netback_asia'])} ({result['asia_route']}) · "
               f"FOB 115% HH ${result['fob_variable']:.2f} · all USD/MMBtu")


# ---------------------------------------------------------------------------
# 4. Price panel
# ---------------------------------------------------------------------------

def jkm_changed_at(jkm):
    """Return the time the JKM input was last changed.

    st.session_state is the app's short-term memory: unlike normal
    variables, it survives each re-run of this file. We store the last
    JKM value seen, and the time it changed.
    """
    if st.session_state.get("last_jkm") != jkm:
        st.session_state["last_jkm"] = jkm
        st.session_state["jkm_changed_at"] = datetime.now(timezone.utc)
    return st.session_state["jkm_changed_at"]


def format_age(timestamp):
    """Turn a timestamp into a short age like '4 min', '3 h' or '2 d'."""
    if timestamp is None:
        return "n/a"
    minutes = (datetime.now(timezone.utc) - timestamp).total_seconds() / 60
    if minutes < 60:
        return f"{minutes:.0f} min"
    if minutes < 24 * 60:
        return f"{minutes / 60:.0f} h"
    return f"{minutes / (24 * 60):.0f} d"


STATUS_LIGHTS = {"fresh": "🟢 fresh", "delayed": "🟡 delayed", "stale": "🔴 stale"}


def show_price_panel(quotes):
    """Show one row per price: value, unit, source, timestamp, age, status light.

    quotes: a list of (Quote, number of decimals to show) pairs.
    """
    st.subheader("Prices")

    rows = []
    for quote, decimals in quotes:
        rows.append({
            "Status": STATUS_LIGHTS[quote.status],   # first, because it's what a trader checks first
            "Price": quote.name,
            "Value": f"{quote.value:.{decimals}f}" if quote.value is not None else "n/a",
            "Unit": quote.unit,
            "Source": quote.source,
            "Last traded / changed": (quote.timestamp.strftime("%a %d %b %H:%M UTC")
                                      if quote.timestamp else "n/a"),
            "Age": format_age(quote.timestamp),
        })

    # A pandas DataFrame is a table; st.dataframe draws it on the page
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Status: 🟢 under 20 min old · 🟡 20 to 60 min · 🔴 over 60 min or fetch failed. "
               "Markets closed (e.g. weekends) show 🔴.")


# ---------------------------------------------------------------------------
# 5. Netback comparison
# ---------------------------------------------------------------------------

def money(value):
    """Format a number as a signed price, e.g. +29.40 or -0.90."""
    return f"{value:+.2f}"


def dollars(value):
    """Format a number as dollars with the minus sign first: $2.27 or -$2.27."""
    if value < 0:
        return f"-${abs(value):.2f}"
    return f"${value:.2f}"


def spread_delta(spread):
    """Prepare the small arrow under a netback tile.

    Returns (text, colour mode). A spread that rounds to 0.00 is shown
    grey with no arrow, instead of a confusing red "-0.00".
    """
    rounded = round(spread, 2)
    if rounded == 0:
        return "0.00", "off"          # "off" = grey, no green/red
    return f"{rounded:+.2f}", "normal"  # "normal" = green if positive, red if negative


def show_netbacks(result, inputs):
    """Show Europe and Asia side by side: hub price - freight - regas = netback.

    Only displays numbers already calculated in arb_calc.py.
    """
    st.subheader("Netbacks at Sabine Pass")
    st.caption("Netback = what the cargo is worth back at Sabine Pass, in USD/MMBtu. "
               "Price sources and times are in the panel above.")

    # st.columns(2) splits the page into two side-by-side boxes
    europe_box, asia_box = st.columns(2)

    with europe_box:   # everything indented below is drawn inside the left box
        delta_text, delta_colour = spread_delta(-result["spread"])   # positive = Europe ahead
        st.metric(
            "🇪🇺 Europe (NWE, TTF)",
            dollars(result['netback_europe']),
            delta=f"{delta_text} vs Asia",
            delta_color=delta_colour,
        )
        europe_table = pd.DataFrame([
            {"Item": "TTF (converted)", "USD/MMBtu": money(result["ttf_usd"])},
            {"Item": "Freight to NWE", "USD/MMBtu": money(-inputs["freight_nwe"])},
            {"Item": "Regas Europe", "USD/MMBtu": money(-inputs["regas_europe"])},
            {"Item": "= Netback", "USD/MMBtu": money(result["netback_europe"])},
        ])
        st.dataframe(europe_table, hide_index=True, width="stretch")

    with asia_box:
        delta_text, delta_colour = spread_delta(result["spread"])    # positive = Asia ahead
        st.metric(
            f"🌏 Asia (North Asia, JKM), via {result['asia_route']}",
            dollars(result['netback_asia']),
            delta=f"{delta_text} vs Europe",
            delta_color=delta_colour,
        )

        # Column titles: tick the chosen route, flag Panama if closed
        panama_title = "Via Panama"
        if not inputs["panama_available"]:
            panama_title += " (closed)"
        cape_title = "Via Cape"
        if result["asia_route"] == "Panama":
            panama_title += " ✅"
        else:
            cape_title += " ✅"

        asia_table = pd.DataFrame([
            {"Item": "JKM", panama_title: money(inputs["jkm"]), cape_title: money(inputs["jkm"])},
            {"Item": "Freight", panama_title: money(-inputs["freight_panama"]),
             cape_title: money(-inputs["freight_cape"])},
            {"Item": "Regas Asia", panama_title: money(-inputs["regas_asia"]),
             cape_title: money(-inputs["regas_asia"])},
            {"Item": "= Netback", panama_title: money(result["netback_asia_panama"]),
             cape_title: money(result["netback_asia_cape"])},
        ])
        st.dataframe(asia_table, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# 6. FOB cost and margins
# ---------------------------------------------------------------------------

def show_margins(result):
    """Show the cost of the cargo at Sabine Pass and the margin of the best destination."""
    st.subheader("FOB cost and margins")

    tile1, tile2, tile3, tile4 = st.columns(4)

    tile1.metric("FOB variable", dollars(result['fob_variable']),
                 help="115% of Henry Hub: the cost of the feed gas. "
                      "The only cost still avoidable by cancelling.")
    tile2.metric("FOB full", dollars(result['fob_full']),
                 help="115% HH + liquefaction fee: full cost including the sunk fee.")
    tile3.metric("Margin (variable)", dollars(result['margin_variable']),
                 delta="lift" if result["decision"] == "LIFT" else "cancel",
                 delta_color="normal" if result["decision"] == "LIFT" else "inverse",
                 help="Best netback minus 115% HH. Below zero means cancel the cargo.")
    tile4.metric("Margin (full)", dollars(result['margin_full']),
                 help="Best netback minus full FOB. Below zero: the cargo loses money "
                      "overall, but may still be worth lifting because the fee is sunk.")


# ---------------------------------------------------------------------------
# 7. Refresh log
# ---------------------------------------------------------------------------

def log_if_new_prices(fetched_at, prices, inputs, result):
    """Write one row to the log, but only once per price fetch.

    Streamlit re-runs the page on every click, and each browser tab runs
    its own copy of the page. So before writing, we check the log file
    itself: if its last row already has this fetch time, we skip.
    Result: changing an input, reloading, or opening two tabs never adds
    a duplicate. Only new prices do (app start, every 5 minutes, or
    'Refresh prices now').
    """
    if arb_log.last_refresh_time() != arb_log.time_text(fetched_at):
        row = arb_log.build_log_row(fetched_at, prices, inputs, result)
        arb_log.append_row(row)


# The few columns shown on screen (the download has all of them)
LOG_COLUMNS_SHOWN = ["refresh_time_utc", "hh", "ttf_usd", "jkm", "netback_eu",
                     "netback_asia", "asia_route", "spread", "verdict", "margin_variable"]


def show_log():
    """Show the most recent refreshes, newest first, and a download button."""
    st.subheader("Refresh log")
    log = arb_log.read_log()

    st.caption(f"{len(log)} refreshes recorded in {config.LOG_FILE_PATH}. "
               f"Showing the last {config.LOG_ROWS_SHOWN}, newest first. "
               "History only builds while the app is open.")

    recent = log.tail(config.LOG_ROWS_SHOWN).iloc[::-1]   # last N rows, reversed (newest on top)
    st.dataframe(recent[LOG_COLUMNS_SHOWN], hide_index=True, width="stretch")

    st.download_button(
        "⬇️ Download full log (CSV)",
        data=log.to_csv(index=False),
        file_name="arb_log.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

# @st.fragment(run_every=...) makes Streamlit re-run this function on a timer
# (every 5 minutes), so prices refresh without anyone clicking.
# The sidebar stays outside: a fragment is not allowed to draw in the sidebar.
@st.fragment(run_every=config.REFRESH_SECONDS)
def dashboard(inputs):
    """Fetch prices, calculate, display everything, and log the refresh."""
    prices, fetched_at = load_market_prices()

    next_refresh = fetched_at.timestamp() + config.REFRESH_SECONDS
    st.caption(f"Last price check {fetched_at.strftime('%H:%M:%S UTC')} · "
               f"next auto refresh around "
               f"{datetime.fromtimestamp(next_refresh, timezone.utc).strftime('%H:%M UTC')}")

    # The manual JKM ticket (needed in both branches below)
    jkm_quote = market_data.manual_quote(
        "JKM", inputs["jkm"], "USD/MMBtu", jkm_changed_at(inputs["jkm"])
    )

    # If any live price is missing, we can't calculate. Show which feeds are
    # down (red lights), say so clearly, and stop here.
    missing = [quote.name for quote in prices.values() if quote.value is None]
    if missing:
        st.error(f"No price available for: {', '.join(missing)}. "
                 "Check your internet connection, then click 'Refresh prices now'.")
        show_price_panel([
            (prices["henry_hub"], 3),
            (prices["ttf"], 2),
            (prices["eurusd"], 4),
            (jkm_quote, 2),
        ])
        show_log()
        return   # leave the function: nothing more to draw

    result = arb_calc.calculate_arb(
        henry_hub=prices["henry_hub"].value,
        ttf_eur_mwh=prices["ttf"].value,
        eurusd=prices["eurusd"].value,
        **inputs,   # ** passes every sidebar input by name
    )

    show_verdict(result, inputs["threshold"])

    # Wrap the converted TTF as a Quote too,
    # so every price on screen carries a source, timestamp and light.
    ttf_usd_quote = market_data.derived_quote(
        "TTF", result["ttf_usd"], "USD/MMBtu", [prices["ttf"], prices["eurusd"]]
    )

    show_price_panel([
        (prices["henry_hub"], 3),
        (prices["ttf"], 2),
        (ttf_usd_quote, 3),
        (prices["eurusd"], 4),
        (jkm_quote, 2),
    ])

    show_netbacks(result, inputs)
    show_margins(result)

    log_if_new_prices(fetched_at, prices, inputs, result)
    show_log()


st.title("🚢 LNG Arbitrage: Sabine Pass cargo, Europe or Asia?")
st.caption("Front-month prices. yfinance data is delayed and indicative only.")

inputs = sidebar_inputs()
dashboard(inputs)
