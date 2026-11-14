"""
app.py: the dashboard screens (Streamlit).

This file only DISPLAYS things. It:
  1. gets live prices from market_data.py
  2. reads the trader's inputs from the sidebar
  3. runs the formulas in arb_calc.py
  4. shows the answer

Run it with:   streamlit run app.py

How Streamlit works: every time you change an input, Streamlit re-runs
this whole file from top to bottom and redraws the page.
"""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import arb_calc
import config
import market_data


# ---------------------------------------------------------------------------
# Page setup (must be the first Streamlit command)
# ---------------------------------------------------------------------------

st.set_page_config(page_title="LNG Arb: Sabine Pass", page_icon="🚢", layout="wide")


# ---------------------------------------------------------------------------
# 1. Live prices
# ---------------------------------------------------------------------------

# @st.cache_data keeps the result in memory for REFRESH_SECONDS.
# Without it, every click in the sidebar would re-download prices from Yahoo.
@st.cache_data(ttl=config.REFRESH_SECONDS)
def load_market_prices():
    """Fetch HH, TTF and EURUSD (cached for 5 minutes)."""
    return market_data.get_market_prices()


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
        text = (f"CANCEL: best netback ${result['best_netback']:.2f} "
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
    st.caption(f"Netback Europe ${result['netback_europe']:.2f} · "
               f"Netback Asia ${result['netback_asia']:.2f} ({result['asia_route']}) · "
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
# Main page: runs top to bottom
# ---------------------------------------------------------------------------

st.title("🚢 LNG Arbitrage: Sabine Pass cargo, Europe or Asia?")
st.caption("Front-month prices. yfinance data is delayed and indicative only.")

inputs = sidebar_inputs()
prices = load_market_prices()

# If any live price is missing, we can't calculate. Say so clearly and stop.
missing = [quote.name for quote in prices.values() if quote.value is None]
if missing:
    st.error(f"No price available for: {', '.join(missing)}. "
             "Check your internet connection, then click 'Refresh prices now'.")
    st.stop()   # stop drawing the rest of the page

result = arb_calc.calculate_arb(
    henry_hub=prices["henry_hub"].value,
    ttf_eur_mwh=prices["ttf"].value,
    eurusd=prices["eurusd"].value,
    **inputs,   # ** passes every sidebar input by name
)

show_verdict(result, inputs["threshold"])

# Wrap the converted TTF and the manual JKM as Quotes too,
# so every price on screen carries a source, timestamp and light.
ttf_usd_quote = market_data.derived_quote(
    "TTF", result["ttf_usd"], "USD/MMBtu", [prices["ttf"], prices["eurusd"]]
)
jkm_quote = market_data.manual_quote(
    "JKM", inputs["jkm"], "USD/MMBtu", jkm_changed_at(inputs["jkm"])
)

show_price_panel([
    (prices["henry_hub"], 3),
    (prices["ttf"], 2),
    (ttf_usd_quote, 3),
    (prices["eurusd"], 4),
    (jkm_quote, 2),
])
