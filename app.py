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
import charts
import config
import market_data


# ---------------------------------------------------------------------------
# Page setup (must be the first Streamlit command)
# ---------------------------------------------------------------------------

st.set_page_config(page_title="LNG Arb: Sabine Pass", page_icon="🚢", layout="wide")


# ---------------------------------------------------------------------------
# Look: dark trading terminal
# ---------------------------------------------------------------------------
# The colours come from .streamlit/config.toml. This small block of CSS (the
# language web pages use for styling) adds what the theme can't do on its own.

ACCENT = "#FFB000"       # amber (same as primaryColor in config.toml)
MUTED_TEXT = "#8B95A3"   # grey for labels
MONO = '"SF Mono", Menlo, Consolas, "Liberation Mono", monospace'

TERMINAL_CSS = f"""
<style>
/* Use more of the screen, less empty space at the top */
.block-container {{ padding-top: 3.2rem; padding-bottom: 2rem; max-width: 1400px; }}

/* Big numbers (metrics) in an aligned monospace font, like a trading screen */
[data-testid="stMetricValue"], [data-testid="stMetricDelta"] {{
    font-family: {MONO}; font-variant-numeric: tabular-nums;
}}
[data-testid="stMetricLabel"] p {{
    text-transform: uppercase; letter-spacing: .06em; font-size: .72rem; color: {MUTED_TEXT};
}}

/* Section titles: small amber uppercase labels with a thin line underneath */
.section-label {{
    text-transform: uppercase; letter-spacing: .12em; font-size: .78rem; font-weight: 700;
    color: {ACCENT}; border-bottom: 1px solid #2A323D;
    padding-bottom: .35rem; margin: 1.4rem 0 .7rem 0;
}}

/* Header bar */
.app-kicker {{ color: {ACCENT}; font-family: {MONO}; font-size: .8rem; letter-spacing: .15em; }}
.app-title  {{ font-size: 1.9rem; font-weight: 700; margin: .1rem 0 .2rem 0; }}
.app-sub    {{ color: {MUTED_TEXT}; font-size: .85rem; }}

/* Verdict banner */
.verdict {{
    padding: 16px 22px; border-radius: 4px; border-left: 6px solid;
    font-family: {MONO}; font-size: 1.45rem; font-weight: 700; letter-spacing: .02em;
}}
</style>
"""


def apply_terminal_style():
    """Inject the CSS above into the page."""
    st.markdown(TERMINAL_CSS, unsafe_allow_html=True)


def section_header(title, where=st):
    """A small amber uppercase section title (where = st, st.sidebar, a column...)."""
    where.markdown(f'<div class="section-label">{title}</div>', unsafe_allow_html=True)


apply_terminal_style()


# ---------------------------------------------------------------------------
# 1. Live prices
# ---------------------------------------------------------------------------

# @st.cache_data keeps the result in memory for a while (ttl = "time to live").
# Without it, every click would re-download prices from Yahoo.
# It expires 10 seconds BEFORE the 5-minute auto refresh, so each timer tick
# is sure to find the old prices expired and fetch new ones.
@st.cache_data(ttl=config.REFRESH_SECONDS - 10)
def load_market_prices():
    """Fetch HH, TTF, EURUSD, the JKM settlement and the contract months (cached 5 minutes).

    Returns two things: (the prices, the time we fetched them).
    The fetch time lets us log exactly one row per real refresh.
    """
    # {**a, **b} merges two dictionaries into one: the front-month prices
    # plus the contract months used for M+1 pricing (HH loading month, TTF M+1)
    prices = {**market_data.get_market_prices(), **market_data.get_contract_prices()}
    return prices, datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 2. Evaluations: the trader's inputs and the result, kept in memory
# ---------------------------------------------------------------------------
# st.session_state is the app's short-term memory: unlike normal variables,
# it survives each re-run of this file. We keep two things in it:
#   "costs"      -> the freight, regas and fee last used (to prefill the pop-up)
#   "evaluation" -> the last evaluation (inputs, result, time), shown on the page

FREIGHT_SIMPLE = "Simple ($/MMBtu)"
FREIGHT_DETAILED = "Detailed (charter model)"

# Delivery pricing (V3): which futures months price the cargo
DELIVERY_FRONT = "Front month"     # HH and TTF front month (V1/V2 behaviour)
DELIVERY_M1 = "M+1 delivery"       # HH = loading month, TTF = the month the cargo arrives


def default_costs():
    """The cost assumptions from config.py, used until the trader enters their own."""
    return {
        "delivery_pricing": DELIVERY_FRONT,
        "freight_mode": FREIGHT_SIMPLE,
        # Simple mode: freight typed directly in $/MMBtu
        "freight_nwe": config.DEFAULT_FREIGHT_NWE,
        "freight_panama": config.DEFAULT_FREIGHT_PANAMA,
        "freight_cape": config.DEFAULT_FREIGHT_CAPE,
        # Detailed mode: voyage inputs
        "cargo_mmbtu": config.DEFAULT_CARGO_MMBTU,
        "charter_rate": config.DEFAULT_CHARTER_RATE,
        "boil_off_pct_per_day": config.DEFAULT_BOIL_OFF_PCT_PER_DAY,
        "days_nwe": config.DEFAULT_DAYS_NWE,
        "days_panama": config.DEFAULT_DAYS_PANAMA,
        "days_cape": config.DEFAULT_DAYS_CAPE,
        "panama_toll": config.DEFAULT_PANAMA_TOLL,
        # Both modes
        "panama_available": config.DEFAULT_PANAMA_AVAILABLE,
        "regas_europe": config.DEFAULT_REGAS_EUROPE,
        "regas_asia": config.DEFAULT_REGAS_ASIA,
        "liquefaction_fee": config.DEFAULT_LIQUEFACTION_FEE,
        "threshold": config.DEFAULT_INDIFFERENCE_THRESHOLD,
    }


def current_costs():
    """The latest cost assumptions: the trader's last ones, or the defaults."""
    # {**defaults, **saved}: start from the defaults, then overwrite with what was saved
    return {**default_costs(), **st.session_state.get("costs", {})}


def arb_inputs(gas, costs):
    """Turn gas prices + cost assumptions into the inputs arb_calc needs.

    Simple mode: freight as typed, no boil-off.
    Detailed mode: freight and boil-off calculated from the voyage inputs.

    Returns two things: (inputs for calculate_arb, freight build-up or None).
    """
    if costs["freight_mode"] == FREIGHT_DETAILED:
        build_up = arb_calc.detailed_freight(
            charter_rate=costs["charter_rate"],
            cargo_mmbtu=costs["cargo_mmbtu"],
            boil_off_pct_per_day=costs["boil_off_pct_per_day"],
            days_nwe=costs["days_nwe"],
            days_panama=costs["days_panama"],
            days_cape=costs["days_cape"],
            panama_toll=costs["panama_toll"],
        )
        freight = {route: build_up[route]["freight"] for route in build_up}
        boil_off = {route: build_up[route]["boil_off"] for route in build_up}
    else:
        build_up = None
        freight = {"nwe": costs["freight_nwe"], "panama": costs["freight_panama"],
                   "cape": costs["freight_cape"]}
        boil_off = {"nwe": 0.0, "panama": 0.0, "cape": 0.0}

    inputs = {
        **gas,
        "freight_nwe": freight["nwe"],
        "freight_panama": freight["panama"],
        "freight_cape": freight["cape"],
        "boil_off_nwe": boil_off["nwe"],
        "boil_off_panama": boil_off["panama"],
        "boil_off_cape": boil_off["cape"],
        "panama_available": costs["panama_available"],
        "regas_europe": costs["regas_europe"],
        "regas_asia": costs["regas_asia"],
        "liquefaction_fee": costs["liquefaction_fee"],
        "threshold": costs["threshold"],
    }
    return inputs, build_up


def use_contract(prices, delivery_pricing, contract_key):
    """True if M+1 pricing is on AND that contract month has a price.

    If the contract has no data, we fall back to the front month (SPEC 13.4).
    """
    return delivery_pricing == DELIVERY_M1 and prices[contract_key].value is not None


def market_gas_prices(prices, delivery_pricing=DELIVERY_FRONT):
    """The market's gas prices as plain numbers (None where a price is missing).

    Front month: HH and TTF front month.
    M+1 delivery: HH for the loading month and TTF for the delivery month
    (each falls back to its front month if the contract has no price).
    JKM falls back to the config default when Yahoo has no settlement.
    """
    jkm = prices["jkm_settlement"].value
    if jkm is None:
        jkm = config.DEFAULT_JKM

    henry_hub = prices["henry_hub"].value
    if use_contract(prices, delivery_pricing, "henry_hub_front"):
        henry_hub = prices["henry_hub_front"].value

    ttf = prices["ttf"].value
    if use_contract(prices, delivery_pricing, "ttf_m1"):
        ttf = prices["ttf_m1"].value

    return {
        "henry_hub": henry_hub,
        "ttf_eur_mwh": ttf,
        "eurusd": prices["eurusd"].value,
        "jkm": jkm,
    }


def gas_price_names(prices, delivery_pricing):
    """Names for the HH and TTF prices used, e.g. "TTF Jan-27" in M+1 mode.

    Shown on the pop-up boxes and in the sidebar, so the trader always
    knows which contract month priced the cargo.
    """
    names = {"henry_hub": "Henry Hub", "ttf": "TTF"}   # front month: plain names
    if use_contract(prices, delivery_pricing, "henry_hub_front"):
        names["henry_hub"] = prices["henry_hub_front"].name    # e.g. "Henry Hub Dec-26"
    if use_contract(prices, delivery_pricing, "ttf_m1"):
        names["ttf"] = prices["ttf_m1"].name                   # e.g. "TTF Jan-27"
    elif delivery_pricing == DELIVERY_M1:
        names["ttf"] = "TTF front (M+1 unavailable)"
    return names


def make_evaluation(gas, costs, sources, indicative, price_names):
    """Run the arb calculation and pack everything the screens need.

    gas: the four gas prices used; costs: delivery pricing, freight mode, freight/voyage inputs, fees
    sources: for each gas price, "market" or "your input"
    indicative: True if this is the automatic case (no evaluation by the trader yet)
    price_names: names of the HH and TTF prices used (e.g. "TTF Jan-27")
    """
    inputs, build_up = arb_inputs(gas, costs)
    result = arb_calc.calculate_arb(**inputs)
    return {
        "time": datetime.now(timezone.utc),
        "inputs": inputs,       # what the maths used (incl. calculated freight)
        "costs": costs,         # what the trader entered (incl. freight mode)
        "build_up": build_up,   # freight build-up per route (Detailed mode), or None
        "result": result,
        "sources": sources,
        "indicative": indicative,
        "price_names": price_names,
    }


def indicative_evaluation(prices):
    """The automatic case shown before any evaluation: market prices + latest costs.

    Returns None if HH, TTF or EURUSD is missing (nothing to calculate with).
    """
    costs = current_costs()
    gas = market_gas_prices(prices, costs["delivery_pricing"])
    if None in gas.values():
        return None
    sources = {name: "market" for name in gas}
    names = gas_price_names(prices, costs["delivery_pricing"])
    return make_evaluation(gas, costs, sources, indicative=True, price_names=names)


# ---------------------------------------------------------------------------
# 3. Verdict
# ---------------------------------------------------------------------------

# Each verdict: (dark tinted background, bright border/text colour)
BANNER_COLOURS = {
    "lift": ("#0F2A1F", "#2EBD85"),         # green
    "cancel": ("#2E1217", "#F6465D"),       # red
    "indifferent": ("#1B222C", "#9AA4B2"),  # slate grey
}


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


def show_banner(text, colours):
    """Draw the verdict box: dark tinted background, bright coloured border and text.

    colours: (background, accent) from BANNER_COLOURS.
    """
    background, accent = colours
    st.markdown(
        f'<div class="verdict" style="background:{background}; border-color:{accent}; '
        f'color:{accent};">{text}</div>',
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
    costs = current_costs()

    st.caption("Gas prices are prefilled from the market (yfinance, delayed; JKM is "
               "yesterday's settlement). Change any number, then click **Evaluate**. "
               "All prices in USD/MMBtu unless stated.")

    # Every change in the pop-up re-runs only the pop-up (it's cheap: nothing is
    # calculated until Evaluate). That lets each switch show the right boxes at once.
    section_header("1 · Gas prices")
    delivery_pricing = st.radio(
        "Delivery pricing", [DELIVERY_FRONT, DELIVERY_M1], horizontal=True,
        index=[DELIVERY_FRONT, DELIVERY_M1].index(costs["delivery_pricing"]),
        help="Front month: HH and TTF front month. M+1 delivery: HH for the loading "
             "month and TTF for the month the cargo arrives in Europe. JKM stays the "
             "daily settlement (Yahoo has no JKM contract months).")

    # The market prices for the chosen pricing, and their names (e.g. "TTF Jan-27")
    market = market_gas_prices(prices, delivery_pricing)
    names = gas_price_names(prices, delivery_pricing)

    missing = [name for name in ("henry_hub", "ttf_eur_mwh", "eurusd") if market[name] is None]
    if missing:
        st.warning("Some market prices are unavailable (no internet?). Type them in yourself.")
    if delivery_pricing == DELIVERY_M1 and prices["ttf_m1"].value is None:
        st.warning(f"No price for the {prices['ttf_m1'].name} contract: "
                   "TTF is prefilled with the front month instead.")

    # When the label changes (e.g. "TTF" -> "TTF Jan-27"), Streamlit treats it as a
    # new box, so switching the pricing refills the box with the right market price.
    c1, c2, c3, c4 = st.columns(4)
    henry_hub = c1.number_input(names["henry_hub"], min_value=0.0, step=0.05, format="%.3f",
                                value=market["henry_hub"] or 0.0)
    ttf = c2.number_input(f"{names['ttf']} (EUR/MWh)", min_value=0.0, step=0.50, format="%.2f",
                          value=market["ttf_eur_mwh"] or 0.0)
    eurusd = c3.number_input("EURUSD", min_value=0.0, step=0.005, format="%.4f",
                             value=market["eurusd"] or 0.0)
    jkm = c4.number_input("JKM", min_value=0.0, step=0.05, format="%.3f",
                          value=market["jkm"])

    section_header("2 · Freight (Sabine Pass →)")
    freight_mode = st.radio("Freight mode", [FREIGHT_SIMPLE, FREIGHT_DETAILED], horizontal=True,
                            index=[FREIGHT_SIMPLE, FREIGHT_DETAILED].index(costs["freight_mode"]),
                            label_visibility="collapsed")

    # Start from the last costs; the boxes shown below overwrite the ones they cover.
    # (The other mode's values are kept, so switching back remembers them.)
    new_costs = dict(costs, freight_mode=freight_mode, delivery_pricing=delivery_pricing)

    if freight_mode == FREIGHT_SIMPLE:
        c1, c2, c3 = st.columns(3)
        new_costs["freight_nwe"] = c1.number_input(
            "North-West Europe", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
            value=costs["freight_nwe"])
        new_costs["freight_panama"] = c2.number_input(
            "North Asia via Panama", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
            value=costs["freight_panama"])
        new_costs["freight_cape"] = c3.number_input(
            "North Asia via Cape", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
            value=costs["freight_cape"])
    else:
        c1, c2, c3 = st.columns(3)
        new_costs["charter_rate"] = c1.number_input(
            "Charter rate ($/day)", min_value=0, step=5_000, value=int(costs["charter_rate"]))
        new_costs["cargo_mmbtu"] = c2.number_input(
            "Cargo loaded (MMBtu)", min_value=1, step=100_000, value=int(costs["cargo_mmbtu"]))
        new_costs["boil_off_pct_per_day"] = c3.number_input(
            "Boil-off (% per laden day)", min_value=0.0, step=0.01, format="%.2f",
            value=float(costs["boil_off_pct_per_day"]))
        c1, c2, c3, c4 = st.columns(4)
        new_costs["days_nwe"] = c1.number_input(
            "Days to NWE (one way)", min_value=1, step=1, value=int(costs["days_nwe"]))
        new_costs["days_panama"] = c2.number_input(
            "Days to Asia via Panama", min_value=1, step=1, value=int(costs["days_panama"]))
        new_costs["days_cape"] = c3.number_input(
            "Days to Asia via Cape", min_value=1, step=1, value=int(costs["days_cape"]))
        new_costs["panama_toll"] = c4.number_input(
            "Panama toll ($ per transit)", min_value=0, step=50_000, value=int(costs["panama_toll"]))

    new_costs["panama_available"] = not st.toggle("Panama Canal unavailable",
                                                  value=not costs["panama_available"])

    section_header("3 · Fees")
    c1, c2, c3 = st.columns(3)
    new_costs["regas_europe"] = c1.number_input(
        "Regas Europe", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
        value=costs["regas_europe"])
    new_costs["regas_asia"] = c2.number_input(
        "Regas Asia", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
        value=costs["regas_asia"])
    new_costs["liquefaction_fee"] = c3.number_input(
        "Liquefaction fee", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
        value=costs["liquefaction_fee"])

    with st.expander("Settings"):   # a section you can fold open/closed
        new_costs["threshold"] = st.number_input(
            "Indifference threshold", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
            value=costs["threshold"])

    if st.button("Evaluate", type="primary", width="stretch"):
        gas = {"henry_hub": henry_hub, "ttf_eur_mwh": ttf, "eurusd": eurusd, "jkm": jkm}
        sources = {name: source_of(gas[name], market[name]) for name in gas}
        st.session_state["costs"] = new_costs
        st.session_state["evaluation"] = make_evaluation(gas, new_costs, sources,
                                                         indicative=False, price_names=names)
        st.session_state["show_result_in_popup"] = True

    # Show the answer inside the pop-up. (We use session_state, not the button,
    # so the answer stays visible when Close is clicked.)
    if st.session_state.get("show_result_in_popup"):
        evaluation = st.session_state["evaluation"]
        show_verdict(evaluation["result"], evaluation["inputs"]["threshold"])
        if evaluation["build_up"] is not None:
            show_freight_build_up(evaluation["build_up"], evaluation["inputs"]["panama_available"])
        if st.button("Close and see the full breakdown", width="stretch"):
            st.rerun()   # re-running the whole page closes the pop-up


def show_freight_build_up(build_up, panama_available):
    """Table: how freight and boil-off were built for each route (Detailed mode)."""
    names = {"nwe": "NWE", "panama": "Asia via Panama", "cape": "Asia via Cape"}
    rows = []
    for route, name in names.items():
        voyage = build_up[route]
        if route == "panama" and not panama_available:
            name += " (closed)"
        rows.append({
            "Route": name,
            "Round trip (days)": voyage["round_trip_days"],
            "Charter ($m)": f"{voyage['charter_cost'] / 1e6:.2f}",
            "Canal tolls ($m)": f"{voyage['canal_cost'] / 1e6:.2f}",
            "Freight ($/MMBtu)": f"{voyage['freight']:.3f}",
            "Boil-off (%)": f"{voyage['boil_off'] * 100:.1f}",
        })
    section_header("Freight build-up")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


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
    section_header("Your evaluation", sb)

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

    section_header("Prices used", sb)
    names = evaluation["price_names"]
    sb.markdown(markdown_table([
        ("Delivery pricing", evaluation["costs"]["delivery_pricing"]),
        (names["henry_hub"], f"{inputs['henry_hub']:.3f} · {sources['henry_hub']}"),
        (f"{names['ttf']} (EUR/MWh)", f"{inputs['ttf_eur_mwh']:.2f} · {sources['ttf_eur_mwh']}"),
        ("EURUSD", f"{inputs['eurusd']:.4f} · {sources['eurusd']}"),
        ("TTF ($/MMBtu)", f"{result['ttf_usd']:.3f} · converted"),
        ("JKM", f"{inputs['jkm']:.3f} · {sources['jkm']}"),
    ]))

    section_header("Costs used", sb)
    costs = evaluation["costs"]
    panama_text = "open" if inputs["panama_available"] else "**closed**"
    detailed = costs["freight_mode"] == FREIGHT_DETAILED

    rows = [("Freight mode", "Detailed (charter model)" if detailed else "Simple ($/MMBtu)")]
    if detailed:
        rows += [
            ("Charter rate", f"${costs['charter_rate']:,.0f}/day"),
            ("Cargo loaded", f"{costs['cargo_mmbtu']:,.0f} MMBtu"),
            ("Boil-off", f"{costs['boil_off_pct_per_day']:.2f}% per laden day"),
            ("Days one way", f"NWE {costs['days_nwe']} · Panama {costs['days_panama']} "
                             f"· Cape {costs['days_cape']}"),
            ("Panama toll", f"${costs['panama_toll']:,.0f} per transit"),
        ]
    # In both modes: the freight actually used ($/MMBtu), plus boil-off if any
    for label, route, extra in [("NWE", "nwe", ""), ("Asia via Panama", "panama", f" (canal {panama_text})"),
                                ("Asia via Cape", "cape", "")]:
        value = f"{inputs['freight_' + route]:.3f}"
        if detailed:
            value += f" · boil-off {inputs['boil_off_' + route] * 100:.1f}%"
        rows.append((f"Freight {label}", value + extra))
    sb.markdown(markdown_table(rows + [
        ("Regas Europe", f"{inputs['regas_europe']:.2f}"),
        ("Regas Asia", f"{inputs['regas_asia']:.2f}"),
        ("Liquefaction fee", f"{inputs['liquefaction_fee']:.2f}"),
    ]))

    section_header("Results", sb)
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
    section_header("Netbacks at Sabine Pass")
    st.caption("Netback = what the cargo is worth back at Sabine Pass, per MMBtu loaded, in "
               "USD/MMBtu. The prices and costs used are listed in the sidebar.")

    # Boil-off lines only appear when there is boil-off (Detailed freight mode)
    has_boil_off = (inputs["boil_off_nwe"] + inputs["boil_off_panama"] + inputs["boil_off_cape"]) > 0

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
        europe_rows = [
            {"Item": "TTF (converted)", "USD/MMBtu": money(result["ttf_usd"])},
            {"Item": "Regas Europe", "USD/MMBtu": money(-inputs["regas_europe"])},
        ]
        if has_boil_off:   # only shown in Detailed freight mode
            europe_rows.append({"Item": "Boil-off loss",
                                "USD/MMBtu": money(-result["boil_off_loss_europe"])})
        europe_rows += [
            {"Item": "Freight to NWE", "USD/MMBtu": money(-inputs["freight_nwe"])},
            {"Item": "= Netback", "USD/MMBtu": money(result["netback_europe"])},
        ]
        st.dataframe(pd.DataFrame(europe_rows), hide_index=True, width="stretch")

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

        asia_rows = [
            {"Item": "JKM", panama_title: money(inputs["jkm"]), cape_title: money(inputs["jkm"])},
            {"Item": "Regas Asia", panama_title: money(-inputs["regas_asia"]),
             cape_title: money(-inputs["regas_asia"])},
        ]
        if has_boil_off:
            asia_rows.append({"Item": "Boil-off loss",
                              panama_title: money(-result["boil_off_loss_panama"]),
                              cape_title: money(-result["boil_off_loss_cape"])})
        asia_rows += [
            {"Item": "Freight", panama_title: money(-inputs["freight_panama"]),
             cape_title: money(-inputs["freight_cape"])},
            {"Item": "= Netback", panama_title: money(result["netback_asia_panama"]),
             cape_title: money(result["netback_asia_cape"])},
        ]
        st.dataframe(pd.DataFrame(asia_rows), hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# 7. FOB cost and margins
# ---------------------------------------------------------------------------

def show_margins(result):
    """Show the cost of the cargo at Sabine Pass and the margin of the best destination."""
    section_header("FOB cost and margins")

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
# 7b. Sensitivity: breakeven charts
# ---------------------------------------------------------------------------

def show_sensitivity(evaluation):
    """Two charts: the spread as JKM moves, and as TTF moves (everything else fixed)."""
    inputs = evaluation["inputs"]
    result = evaluation["result"]

    section_header("Sensitivity · breakeven")
    st.caption("How the Asia − Europe spread changes if one price moves and everything else "
               "stays as in this evaluation. Shaded band = Indifferent zone (± threshold).")

    jkm_box, ttf_box = st.columns(2)

    # JKM: the price where Asia starts to beat Europe
    breakeven_jkm = arb_calc.breakeven_jkm(inputs)
    low, high = charts.chart_range(inputs["jkm"], breakeven_jkm)
    prices, spreads = arb_calc.spread_curve(inputs, "jkm", low, high)
    jkm_box.plotly_chart(
        charts.breakeven_chart(prices, spreads, inputs["jkm"], result["spread"], breakeven_jkm,
                               inputs["threshold"], "JKM ($/MMBtu)"),
        width="stretch", config={"displayModeBar": False})
    jkm_box.caption(f"Asia wins above JKM **${breakeven_jkm:.2f}** "
                    f"(today {inputs['jkm'] - breakeven_jkm:+.2f} from breakeven).")

    # TTF: the price (EUR/MWh) where Europe starts to beat Asia
    breakeven_ttf = arb_calc.breakeven_ttf(inputs)
    low, high = charts.chart_range(inputs["ttf_eur_mwh"], breakeven_ttf)
    prices, spreads = arb_calc.spread_curve(inputs, "ttf_eur_mwh", low, high)
    ttf_box.plotly_chart(
        charts.breakeven_chart(prices, spreads, inputs["ttf_eur_mwh"], result["spread"],
                               breakeven_ttf, inputs["threshold"], "TTF (EUR/MWh)",
                               unit_prefix="€"),
        width="stretch", config={"displayModeBar": False})
    ttf_box.caption(f"Europe wins above TTF **€{breakeven_ttf:.2f}/MWh** "
                    f"(today {inputs['ttf_eur_mwh'] - breakeven_ttf:+.2f} from breakeven).")

    # Decision heatmap: JKM x Asia freight (of the route chosen in this evaluation)
    section_header("Decision map · JKM × Asia freight")
    route = result["asia_route"]
    current_freight = inputs["freight_panama"] if route == "Panama" else inputs["freight_cape"]
    jkm_low, jkm_high = charts.chart_range(inputs["jkm"], breakeven_jkm)
    jkm_values = [jkm_low + (jkm_high - jkm_low) * i / (config.HEATMAP_POINTS - 1)
                  for i in range(config.HEATMAP_POINTS)]
    freight_values = charts.heatmap_freight_range(current_freight)
    outcomes, spreads = arb_calc.decision_grid(inputs, jkm_values, freight_values)
    st.plotly_chart(
        charts.decision_heatmap(jkm_values, freight_values, outcomes, spreads,
                                inputs["jkm"], current_freight, route),
        width="stretch", config={"displayModeBar": False})
    st.caption(f"Each cell re-runs the full calculation with that JKM and that freight via "
               f"{route} (everything else as in this evaluation). If {route} gets too expensive, "
               "the cargo may switch to the other Asia route. Hover a cell for its spread.")


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
    section_header("Refresh log · market arb history")
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

    section_header("Live market")
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
    # The contract months used for M+1 pricing (e.g. Henry Hub Dec-26, TTF Jan-27)
    rows += [(prices["henry_hub_front"], 3), (prices["ttf_m1"], 2)]
    show_price_panel(rows)

    if live_ok:
        # Log the MARKET arb: live prices with the latest cost assumptions
        # (same freight mode as the last evaluation: Simple, or Detailed with boil-off).
        # The log always uses FRONT-month prices, so its history stays comparable.
        market_inputs, _ = arb_inputs(market_gas_prices(prices, DELIVERY_FRONT), current_costs())
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

# Header bar: title on the left, the two buttons on the right
title_box, buttons_box = st.columns([3, 2], vertical_alignment="bottom")
title_box.markdown(
    '<div class="app-kicker">LNG ARB ▸ SABINE PASS FOB</div>'
    '<div class="app-title">Europe or Asia?</div>'
    '<div class="app-sub">Where should a US LNG cargo go right now, and by how much? '
    'Front-month or M+1 prices · yfinance data delayed, indicative only.</div>',
    unsafe_allow_html=True,
)
# Buttons first (we only act on them once prices are loaded below)
button1, button2 = buttons_box.columns(2)
evaluate_clicked = button1.button("Evaluate a cargo", type="primary", width="stretch")
refresh_clicked = button2.button("↻ Refresh prices", width="stretch")

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
        st.caption("INDICATIVE · live market prices with default costs. "
                   "Click **Evaluate a cargo** to enter your own.")
    else:
        st.caption(f"YOUR EVALUATION · {evaluation['time'].strftime('%H:%M UTC')} "
                   "· details in the sidebar")
    show_verdict(evaluation["result"], evaluation["inputs"]["threshold"])

    section_header("Routes from Sabine Pass")
    # config={"displayModeBar": False} hides Plotly's toolbar, for a cleaner look
    st.plotly_chart(charts.route_map(evaluation["result"], evaluation["inputs"]),
                    width="stretch", config={"displayModeBar": False})

    show_netbacks(evaluation["result"], evaluation["inputs"])
    show_margins(evaluation["result"])
    show_sensitivity(evaluation)

st.divider()   # a thin horizontal line
live_market()
