"""
app.py: the dashboard screens (Streamlit).

This file only DISPLAYS things. It:
  1. gets live prices from market_data.py
  2. opens the "Evaluate a cargo" pop-up, where the trader enters prices and costs
  3. runs the formulas in arb_calc.py
  4. shows the answer (in the pop-up, on the page, and as a summary in the sidebar)
  5. shows the live market and logs each price refresh (via arb_log.py)

Run it with:   streamlit run app.py

How Streamlit works: every time you click something, Streamlit re-runs
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
# Without it, every click would re-download prices from Yahoo.
# It expires 10 seconds BEFORE the 5-minute auto refresh, so each timer tick
# is sure to find the old prices expired and fetch new ones.
@st.cache_data(ttl=config.REFRESH_SECONDS - 10)
def load_market_prices():
    """Fetch HH, TTF, EURUSD and the JKM settlement (cached for 5 minutes).

    Returns two things: (the prices, the time we fetched them).
    The fetch time lets us log exactly one row per real refresh.
    """
    return market_data.get_market_prices(), datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 2. Evaluations: the trader's inputs and the result, kept in memory
# ---------------------------------------------------------------------------
# st.session_state is the app's short-term memory: unlike normal variables,
# it survives each re-run of this file. We keep two things in it:
#   "costs"      -> the freight, regas and fee last used (to prefill the pop-up)
#   "evaluation" -> the last evaluation (inputs, result, time), shown on the page

def default_costs():
    """The cost assumptions from config.py, used until the trader enters their own."""
    return {
        "freight_nwe": config.DEFAULT_FREIGHT_NWE,
        "freight_panama": config.DEFAULT_FREIGHT_PANAMA,
        "freight_cape": config.DEFAULT_FREIGHT_CAPE,
        "panama_available": config.DEFAULT_PANAMA_AVAILABLE,
        "regas_europe": config.DEFAULT_REGAS_EUROPE,
        "regas_asia": config.DEFAULT_REGAS_ASIA,
        "liquefaction_fee": config.DEFAULT_LIQUEFACTION_FEE,
        "threshold": config.DEFAULT_INDIFFERENCE_THRESHOLD,
    }


def current_costs():
    """The latest cost assumptions: the trader's last ones, or the defaults."""
    return st.session_state.get("costs", default_costs())


def market_gas_prices(prices):
    """The market's gas prices as plain numbers (None where a price is missing).

    JKM falls back to the config default when Yahoo has no settlement.
    """
    jkm = prices["jkm_settlement"].value
    if jkm is None:
        jkm = config.DEFAULT_JKM
    return {
        "henry_hub": prices["henry_hub"].value,
        "ttf_eur_mwh": prices["ttf"].value,
        "eurusd": prices["eurusd"].value,
        "jkm": jkm,
    }


def make_evaluation(gas, costs, sources, indicative):
    """Run the arb calculation and pack everything the screens need.

    gas: the four gas prices used; costs: freight, regas, fee, threshold
    sources: for each gas price, "market" or "your input"
    indicative: True if this is the automatic case (no evaluation by the trader yet)
    """
    inputs = {**gas, **costs}   # {**a, **b} merges two dictionaries into one
    result = arb_calc.calculate_arb(**inputs)
    return {
        "time": datetime.now(timezone.utc),
        "inputs": inputs,
        "result": result,
        "sources": sources,
        "indicative": indicative,
    }


def indicative_evaluation(prices):
    """The automatic case shown before any evaluation: market prices + latest costs.

    Returns None if HH, TTF or EURUSD is missing (nothing to calculate with).
    """
    gas = market_gas_prices(prices)
    if None in gas.values():
        return None
    sources = {name: "market" for name in gas}
    return make_evaluation(gas, current_costs(), sources, indicative=True)


# ---------------------------------------------------------------------------
# 3. Verdict
# ---------------------------------------------------------------------------

BANNER_COLOURS = {"lift": "#1e7b34", "cancel": "#b3261e", "indifferent": "#5f6368"}  # green, red, grey


def dollars(value):
    """Format a number as dollars with the minus sign first: $2.27 or -$2.27."""
    if value < 0:
        return f"-${abs(value):.2f}"
    return f"${value:.2f}"


def verdict_sentence(result, threshold):
    """Turn the result into one clear sentence and its banner colour."""
    if result["decision"] == "CANCEL":
        text = (f"CANCEL: best netback {dollars(result['best_netback'])} "
                f"does not cover 115% HH (${result['fob_variable']:.2f})")
        return text, BANNER_COLOURS["cancel"]

    if result["winner"] == "Indifferent":
        text = (f"LIFT → INDIFFERENT: spread ${abs(result['spread']):.2f}/MMBtu "
                f"is below the ${threshold:.2f} threshold")
        return text, BANNER_COLOURS["indifferent"]

    if result["winner"] == "Asia":
        text = (f"LIFT → ASIA, wins by ${abs(result['spread']):.2f}/MMBtu "
                f"(via {result['asia_route']})")
        return text, BANNER_COLOURS["lift"]

    text = f"LIFT → EUROPE, wins by ${abs(result['spread']):.2f}/MMBtu"
    return text, BANNER_COLOURS["lift"]


def show_banner(text, colour):
    """Draw a big coloured box with white text."""
    st.markdown(
        f"""<div style="background:{colour}; color:white; padding:18px 24px;
                        border-radius:8px; font-size:26px; font-weight:700;">
                {text}
            </div>""",
        unsafe_allow_html=True,   # allows our small bit of HTML styling
    )


def show_verdict(result, threshold):
    """Show the verdict banner, with one line of key numbers underneath."""
    text, colour = verdict_sentence(result, threshold)
    show_banner(text, colour)
    st.caption(f"Netback Europe {dollars(result['netback_europe'])} · "
               f"Netback Asia {dollars(result['netback_asia'])} ({result['asia_route']}) · "
               f"FOB 115% HH {dollars(result['fob_variable'])} · all USD/MMBtu")


# ---------------------------------------------------------------------------
# 4. The "Evaluate a cargo" pop-up
# ---------------------------------------------------------------------------

def source_of(typed, market):
    """Say whether a typed price is the market's ("market") or the trader's own."""
    if market is not None and typed == market:
        return "market"
    return "your input"


# @st.dialog turns this function into a pop-up window.
# on_dismiss="rerun": closing it with the ✕ also refreshes the page.
@st.dialog("🚢 Evaluate a cargo", width="large", on_dismiss="rerun")
def evaluate_dialog(prices):
    """Pop-up: enter prices and costs, click Evaluate, see the answer at once."""
    market = market_gas_prices(prices)
    costs = current_costs()

    st.caption("Gas prices are prefilled from the market (yfinance, delayed; JKM is "
               "yesterday's settlement). Change any number, then click **Evaluate**. "
               "All prices in USD/MMBtu unless stated.")

    missing = [name for name in ("henry_hub", "ttf_eur_mwh", "eurusd") if market[name] is None]
    if missing:
        st.warning("Some market prices are unavailable (no internet?). Type them in yourself.")

    # st.form groups inputs: nothing is calculated until the Evaluate button is pressed
    with st.form("evaluate_form"):
        st.markdown("**1. Gas prices**")
        c1, c2, c3, c4 = st.columns(4)
        henry_hub = c1.number_input("Henry Hub", min_value=0.0, step=0.05, format="%.3f",
                                    value=market["henry_hub"] or 0.0)
        ttf = c2.number_input("TTF (EUR/MWh)", min_value=0.0, step=0.50, format="%.2f",
                              value=market["ttf_eur_mwh"] or 0.0)
        eurusd = c3.number_input("EURUSD", min_value=0.0, step=0.005, format="%.4f",
                                 value=market["eurusd"] or 0.0)
        jkm = c4.number_input("JKM", min_value=0.0, step=0.05, format="%.3f",
                              value=market["jkm"])

        st.markdown("**2. Freight (Sabine Pass →)**")
        c1, c2, c3 = st.columns(3)
        freight_nwe = c1.number_input("North-West Europe", min_value=0.0, step=config.INPUT_STEP,
                                      format="%.2f", value=costs["freight_nwe"])
        freight_panama = c2.number_input("North Asia via Panama", min_value=0.0, step=config.INPUT_STEP,
                                         format="%.2f", value=costs["freight_panama"])
        freight_cape = c3.number_input("North Asia via Cape", min_value=0.0, step=config.INPUT_STEP,
                                       format="%.2f", value=costs["freight_cape"])
        panama_unavailable = st.toggle("Panama Canal unavailable",
                                       value=not costs["panama_available"])

        st.markdown("**3. Fees**")
        c1, c2, c3 = st.columns(3)
        regas_europe = c1.number_input("Regas Europe", min_value=0.0, step=config.INPUT_STEP,
                                       format="%.2f", value=costs["regas_europe"])
        regas_asia = c2.number_input("Regas Asia", min_value=0.0, step=config.INPUT_STEP,
                                     format="%.2f", value=costs["regas_asia"])
        liquefaction_fee = c3.number_input("Liquefaction fee", min_value=0.0, step=config.INPUT_STEP,
                                           format="%.2f", value=costs["liquefaction_fee"])

        with st.expander("Settings"):   # a section you can fold open/closed
            threshold = st.number_input("Indifference threshold", min_value=0.0,
                                        step=config.INPUT_STEP, format="%.2f",
                                        value=costs["threshold"])

        evaluate_clicked = st.form_submit_button("Evaluate", type="primary", width="stretch")

    if evaluate_clicked:
        gas = {"henry_hub": henry_hub, "ttf_eur_mwh": ttf, "eurusd": eurusd, "jkm": jkm}
        sources = {name: source_of(gas[name], market[name]) for name in gas}
        new_costs = {
            "freight_nwe": freight_nwe,
            "freight_panama": freight_panama,
            "freight_cape": freight_cape,
            "panama_available": not panama_unavailable,
            "regas_europe": regas_europe,
            "regas_asia": regas_asia,
            "liquefaction_fee": liquefaction_fee,
            "threshold": threshold,
        }
        st.session_state["costs"] = new_costs
        st.session_state["evaluation"] = make_evaluation(gas, new_costs, sources, indicative=False)
        st.session_state["show_result_in_popup"] = True

    # Show the answer inside the pop-up. (We use session_state, not
    # evaluate_clicked, so the answer stays visible when Close is clicked.)
    if st.session_state.get("show_result_in_popup"):
        evaluation = st.session_state["evaluation"]
        show_verdict(evaluation["result"], evaluation["inputs"]["threshold"])
        if st.button("Close and see the full breakdown", width="stretch"):
            st.rerun()   # re-running the whole page closes the pop-up


# ---------------------------------------------------------------------------
# 5. Sidebar: read-only summary of the evaluation
# ---------------------------------------------------------------------------

def markdown_table(rows):
    """Build a small Markdown table (text) from a list of (label, value) pairs."""
    lines = ["| Item | Value |", "|---|---|"]
    for label, value in rows:
        lines.append(f"| {label} | {value} |")
    return "\n".join(lines)


def show_sidebar_summary(evaluation):
    """Show what the trader did: when, at what prices, with what costs, and the answer."""
    sb = st.sidebar
    sb.header("Your evaluation")

    if evaluation is None:
        sb.info("No evaluation yet, and no market prices to show. "
                "Click **Evaluate a cargo** and type the prices.")
        return

    inputs = evaluation["inputs"]
    result = evaluation["result"]
    sources = evaluation["sources"]

    if evaluation["indicative"]:
        sb.info("Indicative only: market prices + default costs. "
                "Click **Evaluate a cargo** to enter your own.")
    else:
        sb.caption(f"Evaluated {evaluation['time'].strftime('%a %d %b, %H:%M UTC')}")

    text, _ = verdict_sentence(result, inputs["threshold"])
    sb.markdown(f"**{text}**")

    sb.subheader("Prices used")
    sb.markdown(markdown_table([
        ("Henry Hub", f"{inputs['henry_hub']:.3f} · {sources['henry_hub']}"),
        ("TTF (EUR/MWh)", f"{inputs['ttf_eur_mwh']:.2f} · {sources['ttf_eur_mwh']}"),
        ("EURUSD", f"{inputs['eurusd']:.4f} · {sources['eurusd']}"),
        ("TTF ($/MMBtu)", f"{result['ttf_usd']:.3f} · converted"),
        ("JKM", f"{inputs['jkm']:.3f} · {sources['jkm']}"),
    ]))

    sb.subheader("Costs used")
    panama_text = "open" if inputs["panama_available"] else "**closed**"
    sb.markdown(markdown_table([
        ("Freight NWE", f"{inputs['freight_nwe']:.2f}"),
        ("Freight Asia via Panama", f"{inputs['freight_panama']:.2f} (canal {panama_text})"),
        ("Freight Asia via Cape", f"{inputs['freight_cape']:.2f}"),
        ("Regas Europe", f"{inputs['regas_europe']:.2f}"),
        ("Regas Asia", f"{inputs['regas_asia']:.2f}"),
        ("Liquefaction fee", f"{inputs['liquefaction_fee']:.2f}"),
    ]))

    sb.subheader("Results")
    sb.markdown(markdown_table([
        ("Netback Europe", dollars(result["netback_europe"])),
        ("Netback Asia", f"{dollars(result['netback_asia'])} via {result['asia_route']}"),
        ("FOB variable (115% HH)", dollars(result["fob_variable"])),
        ("FOB full", dollars(result["fob_full"])),
        ("Margin (variable)", dollars(result["margin_variable"])),
        ("Margin (full)", dollars(result["margin_full"])),
    ]))
    sb.caption("All values in USD/MMBtu unless stated.")


# ---------------------------------------------------------------------------
# 6. Netback comparison
# ---------------------------------------------------------------------------

def money(value):
    """Format a number as a signed price, e.g. +29.40 or -0.90."""
    return f"{value:+.2f}"


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
               "The prices and costs used are listed in the sidebar.")

    # st.columns(2) splits the page into two side-by-side boxes
    europe_box, asia_box = st.columns(2)

    with europe_box:   # everything indented below is drawn inside the left box
        delta_text, delta_colour = spread_delta(-result["spread"])   # positive = Europe ahead
        st.metric(
            "🇪🇺 Europe (NWE, TTF)",
            dollars(result["netback_europe"]),
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
            dollars(result["netback_asia"]),
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
# 7. FOB cost and margins
# ---------------------------------------------------------------------------

def show_margins(result):
    """Show the cost of the cargo at Sabine Pass and the margin of the best destination."""
    st.subheader("FOB cost and margins")

    tile1, tile2, tile3, tile4 = st.columns(4)

    tile1.metric("FOB variable", dollars(result["fob_variable"]),
                 help="115% of Henry Hub: the cost of the feed gas. "
                      "The only cost still avoidable by cancelling.")
    tile2.metric("FOB full", dollars(result["fob_full"]),
                 help="115% HH + liquefaction fee: full cost including the sunk fee.")
    tile3.metric("Margin (variable)", dollars(result["margin_variable"]),
                 delta="lift" if result["decision"] == "LIFT" else "cancel",
                 delta_color="normal" if result["decision"] == "LIFT" else "inverse",
                 help="Best netback minus 115% HH. Below zero means cancel the cargo.")
    tile4.metric("Margin (full)", dollars(result["margin_full"]),
                 help="Best netback minus full FOB. Below zero: the cargo loses money "
                      "overall, but may still be worth lifting because the fee is sunk.")


# ---------------------------------------------------------------------------
# 8. Live market panel
# ---------------------------------------------------------------------------

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
    """Show one row per price: status light, value, unit, source, timestamp, age.

    quotes: a list of (Quote, number of decimals to show) pairs.
    """
    rows = []
    for quote, decimals in quotes:
        # Daily settlements have a date but no meaningful time of day
        if quote.timestamp is None:
            when = "n/a"
        elif quote.source == config.SOURCE_YFINANCE_DAILY:
            when = quote.timestamp.strftime("%a %d %b (daily)")
        else:
            when = quote.timestamp.strftime("%a %d %b %H:%M UTC")

        rows.append({
            "Status": STATUS_LIGHTS[quote.status],   # first, because it's what a trader checks first
            "Price": quote.name,
            "Value": f"{quote.value:.{decimals}f}" if quote.value is not None else "n/a",
            "Unit": quote.unit,
            "Source": quote.source,
            "Last traded": when,
            "Age": format_age(quote.timestamp),
        })

    # A pandas DataFrame is a table; st.dataframe draws it on the page
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("Status: 🟢 under 20 min old · 🟡 20 to 60 min · 🔴 over 60 min or fetch failed. "
               "Markets closed (e.g. weekends) show 🔴. JKM is a daily settlement, so always 🔴.")


# ---------------------------------------------------------------------------
# 9. Refresh log
# ---------------------------------------------------------------------------

def log_if_new_prices(fetched_at, prices, inputs, result):
    """Write one row to the log, but only once per price fetch.

    Streamlit re-runs the page on every click, and each browser tab runs
    its own copy of the page. So before writing, we check the log file
    itself: if its last row already has this fetch time, we skip.
    """
    if arb_log.last_refresh_time() != arb_log.time_text(fetched_at):
        row = arb_log.build_log_row(fetched_at, prices, inputs, result)
        arb_log.append_row(row)


# The few columns shown on screen (the download has all of them)
LOG_COLUMNS_SHOWN = ["refresh_time_utc", "hh", "ttf_usd", "jkm", "netback_eu",
                     "netback_asia", "asia_route", "spread", "verdict", "margin_variable"]


def show_log():
    """Show the most recent refreshes, newest first, and a download button."""
    st.subheader("Refresh log (market arb history)")
    log = arb_log.read_log()

    st.caption(f"{len(log)} refreshes recorded in {config.LOG_FILE_PATH}: live market prices "
               "with your latest cost assumptions. "
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


# @st.fragment(run_every=...) makes Streamlit re-run this function on a timer
# (every 5 minutes), so the live market refreshes without anyone clicking.
@st.fragment(run_every=config.REFRESH_SECONDS)
def live_market():
    """Live market panel + refresh log. Logs the market arb at every new price fetch."""
    prices, fetched_at = load_market_prices()

    st.subheader("Live market")
    next_refresh = fetched_at.timestamp() + config.REFRESH_SECONDS
    st.caption(f"Last price check {fetched_at.strftime('%H:%M:%S UTC')} · "
               f"next auto refresh around "
               f"{datetime.fromtimestamp(next_refresh, timezone.utc).strftime('%H:%M UTC')}")

    hh, ttf, eurusd = prices["henry_hub"], prices["ttf"], prices["eurusd"]
    jkm_settlement = prices["jkm_settlement"]
    live_ok = hh.value is not None and ttf.value is not None and eurusd.value is not None

    rows = [(hh, 3), (ttf, 2)]
    if live_ok:
        # TTF in USD is made from TTF and EURUSD, so it takes the worse of their lights
        ttf_usd = arb_calc.ttf_to_usd_mmbtu(ttf.value, eurusd.value)
        rows.append((market_data.derived_quote("TTF", ttf_usd, "USD/MMBtu", [ttf, eurusd]), 3))
    rows += [(eurusd, 4), (jkm_settlement, 3)]
    show_price_panel(rows)

    if live_ok:
        # Log the MARKET arb: live prices with the latest cost assumptions
        market_inputs = {**market_gas_prices(prices), **current_costs()}
        market_result = arb_calc.calculate_arb(**market_inputs)
        log_if_new_prices(fetched_at, prices, market_inputs, market_result)
    else:
        missing = [q.name for q in (hh, ttf, eurusd) if q.value is None]
        st.error(f"No market price for: {', '.join(missing)}. Check your internet connection, "
                 "then click 'Refresh prices'. You can still evaluate a cargo by typing prices.")

    show_log()


# ---------------------------------------------------------------------------
# Main page: runs top to bottom
# ---------------------------------------------------------------------------

st.title("🚢 LNG Arbitrage: Sabine Pass cargo, Europe or Asia?")
st.caption("Front-month prices. yfinance data is delayed and indicative only.")

# Buttons first (we only act on them once prices are loaded below)
button1, button2, _ = st.columns([2, 2, 2])
evaluate_clicked = button1.button("🚢 Evaluate a cargo", type="primary", width="stretch")
refresh_clicked = button2.button("🔄 Refresh prices", width="stretch")

if refresh_clicked:
    st.cache_data.clear()   # forget the cached prices, so they're fetched again

prices, _ = load_market_prices()   # "_" = a value we don't need here

if evaluate_clicked:
    st.session_state["show_result_in_popup"] = False   # fresh pop-up: no old answer inside
    evaluate_dialog(prices)

# The trader's last evaluation, or the automatic indicative one
evaluation = st.session_state.get("evaluation")
if evaluation is None:
    evaluation = indicative_evaluation(prices)

show_sidebar_summary(evaluation)

if evaluation is None:
    st.warning("Market prices are unavailable. Click **Evaluate a cargo** and type them in.")
else:
    if evaluation["indicative"]:
        st.caption("⚪ Indicative: live market prices with default costs. "
                   "Click **Evaluate a cargo** to enter your own.")
    else:
        st.caption(f"Your evaluation of {evaluation['time'].strftime('%H:%M UTC')} "
                   "(details in the sidebar).")
    show_verdict(evaluation["result"], evaluation["inputs"]["threshold"])
    show_netbacks(evaluation["result"], evaluation["inputs"])
    show_margins(evaluation["result"])

st.divider()   # a thin horizontal line
live_market()
