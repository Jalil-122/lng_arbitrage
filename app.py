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

st.set_page_config(page_title="LNG Arb: Europe or Asia", page_icon="🚢", layout="wide")


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
    """Fetch HH, TTF, EURUSD, the JKM futures settlement and the contract months (cached 5 minutes).

    Returns two things: (the prices, the time we fetched them).
    The fetch time lets us log exactly one row per real refresh.
    """
    # {**a, **b} merges two dictionaries into one: the front-month prices
    # plus the contract months used for M+1 pricing (HH loading month, TTF M+1)
    prices = {**market_data.get_market_prices(), **market_data.get_contract_prices()}
    return prices, datetime.now(timezone.utc)


@st.cache_data(ttl=config.HISTORY_CACHE_SECONDS)
def load_history():
    """Fetch the monthly history (FRED + Yahoo JKM), kept in memory for 24 hours.

    History only changes once a month, so there's no need to download it more often.
    """
    return market_data.get_history()


# ---------------------------------------------------------------------------
# 2. Evaluations: the trader's inputs and the result, kept in memory
# ---------------------------------------------------------------------------
# st.session_state is the app's short-term memory: unlike normal variables,
# it survives each re-run of this file. We keep two things in it:
#   "costs"      -> the port, passages, freight, regas and fee last used (to prefill the pop-up)
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
        # V4: where the cargo loads, and which passages are open
        "load_port": config.DEFAULT_LOAD_PORT,
        "passage_open": {key: passage["default_open"] for key, passage in config.PASSAGES.items()},
        # Per port, filled once the trader evaluates that port (empty = use the defaults):
        "route_freight": {},   # Simple mode:   {port: {route: $/MMBtu}}
        "route_days": {},      # Detailed mode: {port: {"speed": knots, "days": {route: days}}}
        # Detailed mode: voyage inputs
        "ship_speed": config.DEFAULT_SHIP_SPEED_KNOTS,
        "cargo_mmbtu": config.DEFAULT_CARGO_MMBTU,
        "charter_rate": config.DEFAULT_CHARTER_RATE,
        "boil_off_pct_per_day": config.DEFAULT_BOIL_OFF_PCT_PER_DAY,
        "panama_toll": config.DEFAULT_PANAMA_TOLL,
        "suez_toll": config.DEFAULT_SUEZ_TOLL,
        # Both modes
        "regas_europe": config.DEFAULT_REGAS_EUROPE,
        "regas_asia": config.DEFAULT_REGAS_ASIA,
        "liquefaction_fee": config.DEFAULT_LIQUEFACTION_FEE,
        "threshold": config.DEFAULT_INDIFFERENCE_THRESHOLD,
    }


def current_costs():
    """The latest cost assumptions: the trader's last ones, or the defaults."""
    # {**defaults, **saved}: start from the defaults, then overwrite with what was saved
    return {**default_costs(), **st.session_state.get("costs", {})}


def is_us_port(port_key):
    """True for US ports: Henry Hub-linked cargoes, with the lift/cancel decision."""
    return config.LOAD_PORTS[port_key]["us_hh_linked"]


def port_name(port_key):
    """The port's display name, e.g. "Ras Laffan"."""
    return config.LOAD_PORTS[port_key]["name"]


def route_label(port_key, route_key):
    """How a route is written on screen, e.g. "via Panama" or "direct"."""
    return config.LOAD_PORTS[port_key]["routes"][route_key]["label"]


def route_title(port_key, route_key):
    """A route's full name, e.g. "Asia via Panama" or "Europe direct"."""
    route = config.LOAD_PORTS[port_key]["routes"][route_key]
    destination = "Europe" if route["destination"] == "nwe" else "Asia"
    return f"{destination} {route['label']}"


def is_route_open(port_key, route_key, passage_open):
    """True if none of the route's passages is closed (Hormuz only warns)."""
    passages = config.LOAD_PORTS[port_key]["routes"][route_key]["passages"]
    return arb_calc.route_is_open(passages, passage_open)


def default_simple_freight(port_key):
    """Simple-mode prefill for a port: the Detailed model's freight with the default
    voyage inputs (charter rate, cargo, speed, tolls), rounded to the cent."""
    build_up = arb_calc.port_detailed_freight(
        port_key, arb_calc.default_route_days(port_key),
        charter_rate=config.DEFAULT_CHARTER_RATE, cargo_mmbtu=config.DEFAULT_CARGO_MMBTU,
        boil_off_pct_per_day=0.0, panama_toll=config.DEFAULT_PANAMA_TOLL,
        suez_toll=config.DEFAULT_SUEZ_TOLL)
    return {route_key: round(voyage["freight"], 2) for route_key, voyage in build_up.items()}


def port_route_freight(costs, port_key):
    """Simple-mode freight per route for a port: the trader's last values, or the defaults."""
    saved = costs["route_freight"].get(port_key)
    if saved:
        return saved
    return default_simple_freight(port_key)


def port_route_days(costs, port_key):
    """Detailed-mode one-way days per route: the trader's last values (if typed at the
    same ship speed), or distance / speed."""
    saved = costs["route_days"].get(port_key)
    if saved and saved["speed"] == costs["ship_speed"]:
        return saved["days"]
    return arb_calc.default_route_days(port_key, costs["ship_speed"])


def arb_inputs(gas, costs):
    """Turn gas prices + cost assumptions into the inputs arb_calc.calculate_port_arb needs.

    Simple mode: freight as typed, no boil-off.
    Detailed mode: freight and boil-off calculated from the voyage inputs.

    Returns two things: (inputs, freight build-up or None).
    """
    port_key = costs["load_port"]
    if costs["freight_mode"] == FREIGHT_DETAILED:
        build_up = arb_calc.port_detailed_freight(
            port_key, port_route_days(costs, port_key),
            charter_rate=costs["charter_rate"],
            cargo_mmbtu=costs["cargo_mmbtu"],
            boil_off_pct_per_day=costs["boil_off_pct_per_day"],
            panama_toll=costs["panama_toll"],
            suez_toll=costs["suez_toll"],
        )
        route_freight = {route: build_up[route]["freight"] for route in build_up}
        route_boil_off = {route: build_up[route]["boil_off"] for route in build_up}
    else:
        build_up = None
        route_freight = dict(port_route_freight(costs, port_key))
        route_boil_off = {}

    inputs = {
        "port_key": port_key,
        "ttf_eur_mwh": gas["ttf_eur_mwh"],
        "eurusd": gas["eurusd"],
        "jkm": gas["jkm"],
        "route_freight": route_freight,
        "route_boil_off": route_boil_off,
        "regas_europe": costs["regas_europe"],
        "regas_asia": costs["regas_asia"],
        "passage_open": dict(costs["passage_open"]),
        "threshold": costs["threshold"],
    }
    if is_us_port(port_key):   # only US cargoes cost 115% HH + a fee (and can be cancelled)
        inputs["henry_hub"] = gas["henry_hub"]
        inputs["liquefaction_fee"] = costs["liquefaction_fee"]
    return inputs, build_up


def sabine_pass_inputs(gas, costs):
    """Inputs in the V3 shape (calculate_arb) for a Sabine Pass cargo, Panama or Cape.

    The refresh log and the History tab stay Sabine Pass based (SPEC 14.2), so they
    take the Sabine Pass freight from the trader's latest costs, whatever port is chosen.
    """
    port_inputs, _ = arb_inputs(gas, dict(costs, load_port="sabine_pass"))
    freight = port_inputs["route_freight"]
    boil_off = port_inputs["route_boil_off"]
    return {
        "henry_hub": gas["henry_hub"],
        "ttf_eur_mwh": gas["ttf_eur_mwh"],
        "eurusd": gas["eurusd"],
        "jkm": gas["jkm"],
        "freight_nwe": freight["nwe"],
        "freight_panama": freight["asia_panama"],
        "freight_cape": freight["asia_cape"],
        "boil_off_nwe": boil_off.get("nwe", 0.0),
        "boil_off_panama": boil_off.get("asia_panama", 0.0),
        "boil_off_cape": boil_off.get("asia_cape", 0.0),
        "panama_available": costs["passage_open"]["panama"],
        "regas_europe": costs["regas_europe"],
        "regas_asia": costs["regas_asia"],
        "liquefaction_fee": costs["liquefaction_fee"],
        "threshold": costs["threshold"],
    }


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

    gas: the gas prices used; costs: port, passages, delivery pricing, freight mode, fees
    sources: for each gas price, "market" or "your input"
    indicative: True if this is the automatic case (no evaluation by the trader yet)
    price_names: names of the HH and TTF prices used (e.g. "TTF Jan-27")
    """
    inputs, build_up = arb_inputs(gas, costs)
    result = arb_calc.calculate_port_arb(**inputs)
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

    Returns None if a price the calculation needs is missing (TTF, EURUSD,
    and Henry Hub for a US port).
    """
    costs = current_costs()
    gas = market_gas_prices(prices, costs["delivery_pricing"])
    needed = ["ttf_eur_mwh", "eurusd"]
    if is_us_port(costs["load_port"]):
        needed.append("henry_hub")
    if any(gas[name] is None for name in needed):
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
    """Turn the result into one clear sentence and its banner colour.

    US ports: "LIFT → ASIA ..." or "CANCEL ...". Non-US ports have no cancel
    option, so the sentence is the destination only: "→ ASIA ...".
    """
    port_key = result["port"]
    prefix = "LIFT → " if is_us_port(port_key) else "→ "

    if result["decision"] == "CANCEL":
        text = (f"CANCEL: best netback {dollars(result['best_netback'])} "
                f"does not cover 115% HH (${result['fob_variable']:.2f})")
        return text, BANNER_COLOURS["cancel"]

    if result["winner"] == "Indifferent":
        text = (f"{prefix}INDIFFERENT: spread ${abs(result['spread']):.2f}/MMBtu "
                f"is below the ${threshold:.2f} threshold")
        return text, BANNER_COLOURS["indifferent"]

    if result["winner"] == "Asia":
        text = (f"{prefix}ASIA, wins by ${abs(result['spread']):.2f}/MMBtu "
                f"({route_label(port_key, result['asia_route'])})")
        return text, BANNER_COLOURS["lift"]

    text = (f"{prefix}EUROPE, wins by ${abs(result['spread']):.2f}/MMBtu "
            f"({route_label(port_key, result['europe_route'])})")
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


def show_hormuz_warning(result):
    """A clear warning when the cargo must cross a disrupted Strait of Hormuz."""
    if result["hormuz_warning"]:
        st.warning("⚠️ **Strait of Hormuz disrupted.** Every cargo from "
                   f"{port_name(result['port'])} must cross it, and there is no way around. "
                   "Shipping has been largely blocked since the March 2026 Iran war and "
                   "QatarEnergy has declared force majeure. The numbers above assume the "
                   "cargo can sail; in practice it may not.")


def show_verdict(result, threshold):
    """Show the verdict banner, one line of key numbers underneath, and any Hormuz warning."""
    text, colour = verdict_sentence(result, threshold)
    show_banner(text, colour)
    port_key = result["port"]
    line = (f"{port_name(port_key)} · "
            f"Netback Europe {dollars(result['netback_europe'])} "
            f"({route_label(port_key, result['europe_route'])}) · "
            f"Netback Asia {dollars(result['netback_asia'])} "
            f"({route_label(port_key, result['asia_route'])})")
    if result["fob_variable"] is not None:   # US ports only
        line += f" · FOB 115% HH {dollars(result['fob_variable'])}"
    st.caption(line + " · all USD/MMBtu")
    show_hormuz_warning(result)


# ---------------------------------------------------------------------------
# 4. The "Evaluate a cargo" pop-up
# ---------------------------------------------------------------------------

def source_of(typed, market):
    """Say whether a typed price is the market's ("market") or the trader's own."""
    if market is not None and typed == market:
        return "market"
    return "your input"


# Help texts for the passage switches: the market facts behind each default (Nov 2026)
PASSAGE_HELP = {
    "panama": "Open by default, but congested in 2026: slots are auctioned, so many spot "
              "US cargoes to Asia still go round the Cape.",
    "suez": "Avoided by default: LNG carriers have mostly avoided the Red Sea since the "
            "2023-24 Houthi attacks, and attacks resumed in September 2026.",
    "hormuz": "Disrupted by default: largely blocked since the March 2026 Iran war. "
              "Only Ras Laffan (Qatar) cargoes cross it; there's no way around, so "
              "closing it shows a warning instead of removing routes.",
}


def port_option_text(port_key):
    """How a port is listed in the picker, e.g. "Ras Laffan · Qatar"."""
    port = config.LOAD_PORTS[port_key]
    return f"{port['name']} · {port['country']}"


# @st.dialog turns this function into a pop-up window.
# on_dismiss="rerun": closing it with the ✕ also refreshes the page.
@st.dialog("🚢 Evaluate a cargo", width="large", on_dismiss="rerun")
def evaluate_dialog(prices):
    """Pop-up: choose the port, enter prices and costs, click Evaluate, see the answer at once."""
    costs = current_costs()

    st.caption("Gas prices are prefilled from the market (yfinance, delayed; JKM is the "
               "last daily settlement of the CME JKM futures). Change any number, then click "
               "**Evaluate**. "
               "All prices in USD/MMBtu unless stated.")

    # Every change in the pop-up re-runs only the pop-up (it's cheap: nothing is
    # calculated until Evaluate). That lets each switch show the right boxes at once.
    section_header("1 · Cargo")
    port_keys = list(config.LOAD_PORTS)
    # st.selectbox: a drop-down list. format_func decides how each option is written.
    port_key = st.selectbox("Load port", port_keys, index=port_keys.index(costs["load_port"]),
                            format_func=port_option_text)
    us_port = is_us_port(port_key)
    if not us_port:
        st.caption("Non-US cargo: mostly sold on oil-linked long-term contracts, with no "
                   "cancel option and no Henry Hub cost. The verdict is the destination only.")

    delivery_pricing = st.radio(
        "Delivery pricing", [DELIVERY_FRONT, DELIVERY_M1], horizontal=True,
        index=[DELIVERY_FRONT, DELIVERY_M1].index(costs["delivery_pricing"]),
        help="Front month: HH and TTF front month. M+1 delivery: HH for the loading "
             "month and TTF for the month the cargo arrives in Europe. JKM stays the "
             "futures daily settlement (Yahoo has no JKM contract months).")

    # The market prices for the chosen pricing, and their names (e.g. "TTF Jan-27")
    market = market_gas_prices(prices, delivery_pricing)
    names = gas_price_names(prices, delivery_pricing)

    needed = ["ttf_eur_mwh", "eurusd"] + (["henry_hub"] if us_port else [])
    if any(market[name] is None for name in needed):
        st.warning("Some market prices are unavailable (no internet?). Type them in yourself.")
    if delivery_pricing == DELIVERY_M1 and prices["ttf_m1"].value is None:
        st.warning(f"No price for the {prices['ttf_m1'].name} contract: "
                   "TTF is prefilled with the front month instead.")

    # When the label changes (e.g. "TTF" -> "TTF Jan-27"), Streamlit treats it as a
    # new box, so switching the pricing refills the box with the right market price.
    # Non-US ports have no Henry Hub box (their cargo isn't priced on HH).
    boxes = st.columns(4 if us_port else 3)
    henry_hub = None
    if us_port:
        henry_hub = boxes[0].number_input(names["henry_hub"], min_value=0.0, step=0.05,
                                          format="%.3f", value=market["henry_hub"] or 0.0)
        boxes = boxes[1:]          # the other three boxes
    ttf = boxes[0].number_input(f"{names['ttf']} (EUR/MWh)", min_value=0.0, step=0.50,
                                format="%.2f", value=market["ttf_eur_mwh"] or 0.0)
    eurusd = boxes[1].number_input("EURUSD", min_value=0.0, step=0.005, format="%.4f",
                                   value=market["eurusd"] or 0.0)
    jkm = boxes[2].number_input("JKM (CME futures)", min_value=0.0, step=0.05, format="%.3f",
                                help="The CME JKM futures front month, last daily settlement. "
                                     "It can differ from the Platts JKM spot assessment by "
                                     "$1-2/MMBtu: type a spot price here if you have one.",
                                value=market["jkm"])

    section_header("2 · Passages")
    passage_open = {}
    boxes = st.columns(len(config.PASSAGES))
    for box, (passage_key, passage) in zip(boxes, config.PASSAGES.items()):
        # st.toggle: an on/off switch. On = the passage can be used.
        passage_open[passage_key] = box.toggle(f"{passage['name']} open",
                                               value=costs["passage_open"][passage_key],
                                               help=PASSAGE_HELP[passage_key])
    st.caption("The Cape of Good Hope and Cape Horn are always open. For each destination, "
               "the cargo takes the open route with the best netback.")

    # Start from the last costs; the boxes shown below overwrite the ones they cover.
    # The per-port dictionaries are copied, so the other ports' values are kept.
    new_costs = dict(costs, load_port=port_key, delivery_pricing=delivery_pricing,
                     passage_open=passage_open,
                     route_freight=dict(costs["route_freight"]),
                     route_days=dict(costs["route_days"]))

    routes = config.LOAD_PORTS[port_key]["routes"]

    def route_box_label(route_key, prefix=""):
        """The label above a route's box, flagged when the route is closed."""
        label = prefix + route_title(port_key, route_key)
        if not is_route_open(port_key, route_key, passage_open):
            label += " (closed)"
        return label

    section_header(f"3 · Freight ({port_name(port_key)} →)")
    freight_mode = st.radio("Freight mode", [FREIGHT_SIMPLE, FREIGHT_DETAILED], horizontal=True,
                            index=[FREIGHT_SIMPLE, FREIGHT_DETAILED].index(costs["freight_mode"]),
                            label_visibility="collapsed")
    new_costs["freight_mode"] = freight_mode
    st.caption("Freight here = charter hire for the round trip + canal tolls (+ boil-off in "
               "Detailed mode). It **excludes** ballast-leg fuel, port and agency costs, so it "
               "is a floor: published freight assessments (e.g. Platts) are higher.")

    if freight_mode == FREIGHT_SIMPLE:
        st.caption("Prefilled from the charter model with the default voyage inputs.")
        saved_freight = port_route_freight(costs, port_key)
        port_freight = {}
        boxes = st.columns(len(routes))
        for box, route_key in zip(boxes, routes):
            # key=...: a unique name for the box, per port, so each port keeps its own values
            port_freight[route_key] = box.number_input(
                route_box_label(route_key), min_value=0.0, step=config.INPUT_STEP, format="%.2f",
                value=float(saved_freight[route_key]), key=f"freight_{port_key}_{route_key}")
        new_costs["route_freight"][port_key] = port_freight
    else:
        c1, c2, c3, c4 = st.columns(4)
        new_costs["charter_rate"] = c1.number_input(
            "Charter rate ($/day)", min_value=0, step=5_000, value=int(costs["charter_rate"]),
            help="Default $52,000/day: the one-year time-charter rate, late Oct 2026 "
                 "(IndexBox). Spot varies by route: ~$25k US Gulf→Europe, ~$59k "
                 "US Gulf→Japan, ~$33k Australia→Japan. Update it from a broker report.")
        new_costs["cargo_mmbtu"] = c2.number_input(
            "Cargo loaded (MMBtu)", min_value=1, step=100_000, value=int(costs["cargo_mmbtu"]))
        new_costs["boil_off_pct_per_day"] = c3.number_input(
            "Boil-off (% per laden day)", min_value=0.0, step=0.01, format="%.2f",
            value=float(costs["boil_off_pct_per_day"]))
        speed = c4.number_input(
            "Ship speed (knots)", min_value=5.0, max_value=25.0, step=0.5, format="%.1f",
            value=float(costs["ship_speed"]),
            help="Prefills the days: distance / (speed x 24). A knot = 1 nautical mile per hour.")
        new_costs["ship_speed"] = speed

        # The day boxes' names include the speed: a new speed makes new boxes,
        # prefilled with distance / speed (typed days are kept while the speed is unchanged).
        saved_days = port_route_days(dict(costs, ship_speed=speed), port_key)
        port_days = {}
        boxes = st.columns(len(routes))
        for box, route_key in zip(boxes, routes):
            distance = routes[route_key]["distance_nm"]
            port_days[route_key] = box.number_input(
                route_box_label(route_key, "Days to "), min_value=1, step=1,
                value=int(saved_days[route_key]), key=f"days_{port_key}_{route_key}_{speed}",
                help=f"{distance:,} nautical miles one way (searoute, Eurostat sea lanes).")
        new_costs["route_days"][port_key] = {"speed": speed, "days": port_days}

        c1, c2 = st.columns(2)
        new_costs["panama_toll"] = c1.number_input(
            "Panama toll ($ per transit)", min_value=0, step=50_000, value=int(costs["panama_toll"]))
        new_costs["suez_toll"] = c2.number_input(
            "Suez toll ($ per transit)", min_value=0, step=50_000, value=int(costs["suez_toll"]),
            help="Editable placeholder: the Suez Canal Authority publishes no simple LNG "
                 "figure, and its surcharges changed in July 2026.")

    section_header("4 · Fees")
    boxes = st.columns(3)
    new_costs["regas_europe"] = boxes[0].number_input(
        "Regas Europe", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
        value=costs["regas_europe"])
    new_costs["regas_asia"] = boxes[1].number_input(
        "Regas Asia", min_value=0.0, step=config.INPUT_STEP, format="%.2f",
        value=costs["regas_asia"])
    if us_port:   # the liquefaction (tolling) fee only exists for US cargoes
        new_costs["liquefaction_fee"] = boxes[2].number_input(
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
            show_freight_build_up(evaluation["build_up"], evaluation["inputs"])
        if st.button("Close and see the full breakdown", width="stretch"):
            st.rerun()   # re-running the whole page closes the pop-up


def show_freight_build_up(build_up, inputs):
    """Table: how freight and boil-off were built for each route (Detailed mode)."""
    port_key = inputs["port_key"]
    rows = []
    for route_key, voyage in build_up.items():
        name = route_title(port_key, route_key)
        if not is_route_open(port_key, route_key, inputs["passage_open"]):
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


def passages_text(passage_open):
    """One line with every passage's status, e.g. "Panama open · Suez avoided · Hormuz disrupted"."""
    short_names = {"panama": "Panama", "suez": "Suez", "hormuz": "Hormuz"}
    closed_words = {"panama": "closed", "suez": "avoided", "hormuz": "disrupted"}
    parts = []
    for key in config.PASSAGES:
        status = "open" if passage_open[key] else f"**{closed_words[key]}**"
        short_name = short_names[key]
        parts.append(f"{short_name} {status}")
    return " · ".join(parts)


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
    costs = evaluation["costs"]
    port_key = inputs["port_key"]
    us_port = is_us_port(port_key)

    if evaluation["indicative"]:
        sb.info("Indicative only: market prices + default costs. "
                "Click **Evaluate a cargo** to enter your own.")
    else:
        sb.caption(f"Evaluated {evaluation['time'].strftime('%a %d %b, %H:%M UTC')}")

    text, _ = verdict_sentence(result, inputs["threshold"])
    sb.markdown(f"**{text}**")

    section_header("Cargo", sb)
    sb.markdown(markdown_table([
        ("Load port", port_option_text(port_key)),
        ("Passages", passages_text(inputs["passage_open"])),
    ]))

    section_header("Prices used", sb)
    names = evaluation["price_names"]
    rows = [("Delivery pricing", costs["delivery_pricing"])]
    if us_port:
        rows.append((names["henry_hub"], f"{inputs['henry_hub']:.3f} · {sources['henry_hub']}"))
    rows += [
        (f"{names['ttf']} (EUR/MWh)", f"{inputs['ttf_eur_mwh']:.2f} · {sources['ttf_eur_mwh']}"),
        ("EURUSD", f"{inputs['eurusd']:.4f} · {sources['eurusd']}"),
        ("TTF ($/MMBtu)", f"{result['ttf_usd']:.3f} · converted"),
        ("JKM (CME futures)", f"{inputs['jkm']:.3f} · {sources['jkm']}"),
    ]
    sb.markdown(markdown_table(rows))

    section_header("Costs used", sb)
    detailed = costs["freight_mode"] == FREIGHT_DETAILED
    rows = [("Freight mode", "Detailed (charter model)" if detailed else "Simple ($/MMBtu)")]
    if detailed:
        rows += [
            ("Charter rate", f"${costs['charter_rate']:,.0f}/day"),
            ("Cargo loaded", f"{costs['cargo_mmbtu']:,.0f} MMBtu"),
            ("Boil-off", f"{costs['boil_off_pct_per_day']:.2f}% per laden day"),
            ("Ship speed", f"{costs['ship_speed']:.1f} knots"),
            ("Tolls per transit", f"Panama ${costs['panama_toll']:,.0f} · Suez ${costs['suez_toll']:,.0f}"),
        ]
    # In both modes: the freight actually used ($/MMBtu) per route, plus boil-off if any
    for route_key, freight in inputs["route_freight"].items():
        value = f"{freight:.3f}"
        if detailed:
            days = evaluation["build_up"][route_key]["round_trip_days"] // 2
            value += f" · {days} d · boil-off {inputs['route_boil_off'][route_key] * 100:.1f}%"
        if not is_route_open(port_key, route_key, inputs["passage_open"]):
            value += " (closed)"
        rows.append((f"Freight {route_title(port_key, route_key)}", value))
    rows += [
        ("Regas Europe", f"{inputs['regas_europe']:.2f}"),
        ("Regas Asia", f"{inputs['regas_asia']:.2f}"),
    ]
    if us_port:
        rows.append(("Liquefaction fee", f"{inputs['liquefaction_fee']:.2f}"))
    sb.markdown(markdown_table(rows))

    section_header("Results", sb)
    rows = [
        ("Netback Europe", f"{dollars(result['netback_europe'])} "
                           f"{route_label(port_key, result['europe_route'])}"),
        ("Netback Asia", f"{dollars(result['netback_asia'])} "
                         f"{route_label(port_key, result['asia_route'])}"),
    ]
    if us_port:
        rows += [
            ("FOB variable (115% HH)", dollars(result["fob_variable"])),
            ("FOB full", dollars(result["fob_full"])),
            ("Margin (variable)", dollars(result["margin_variable"])),
            ("Margin (full)", dollars(result["margin_full"])),
        ]
    sb.markdown(markdown_table(rows))
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


def netback_table(result, inputs, destination):
    """Table for one destination: one column per route, hub price - regas - boil-off - freight.

    The chosen route is ticked ✅, closed routes say "(closed)".
    """
    port_key = inputs["port_key"]
    if destination == "nwe":
        hub_name, hub_price, regas_name = "TTF (converted)", result["ttf_usd"], "Regas Europe"
        regas, chosen = inputs["regas_europe"], result["europe_route"]
    else:
        hub_name, hub_price, regas_name = "JKM", inputs["jkm"], "Regas Asia"
        regas, chosen = inputs["regas_asia"], result["asia_route"]

    route_keys = [key for key, route in config.LOAD_PORTS[port_key]["routes"].items()
                  if route["destination"] == destination]
    has_boil_off = sum(inputs["route_boil_off"].values()) > 0   # only in Detailed mode

    columns = {}   # column title -> route key
    for route_key in route_keys:
        title = route_label(port_key, route_key).capitalize()
        if not is_route_open(port_key, route_key, inputs["passage_open"]):
            title += " (closed)"
        if route_key == chosen:
            title += " ✅"
        columns[title] = route_key

    def row(item, value_of_route):
        """One table row: the item name, then one value per route column."""
        cells = {"Item": item}
        for title, route_key in columns.items():
            cells[title] = money(value_of_route(route_key))
        return cells

    rows = [row(hub_name, lambda route_key: hub_price),
            row(regas_name, lambda route_key: -regas)]
    # lambda: a tiny one-line function, here "given a route, give its value"
    if has_boil_off:
        rows.append(row("Boil-off loss", lambda route_key: -result["route_boil_off_loss"][route_key]))
    rows += [row("Freight", lambda route_key: -inputs["route_freight"][route_key]),
             row("= Netback", lambda route_key: result["route_netbacks"][route_key])]
    return pd.DataFrame(rows)


def show_netbacks(result, inputs):
    """Show Europe and Asia side by side: hub price - regas - freight = netback, per route.

    Only displays numbers already calculated in arb_calc.py.
    """
    port_key = inputs["port_key"]
    section_header(f"Netbacks at {port_name(port_key)}")
    st.caption(f"Netback = what the cargo is worth back at {port_name(port_key)}, per MMBtu "
               "loaded, in USD/MMBtu. The prices and costs used are listed in the sidebar.")

    # st.columns(2) splits the page into two side-by-side boxes
    europe_box, asia_box = st.columns(2)

    with europe_box:   # everything indented below is drawn inside the left box
        delta_text, delta_colour = spread_delta(-result["spread"])   # positive = Europe ahead
        st.metric(
            f"🇪🇺 Europe (NWE, TTF), {route_label(port_key, result['europe_route'])}",
            dollars(result["netback_europe"]),
            delta=f"{delta_text} vs Asia",
            delta_color=delta_colour,
        )
        st.dataframe(netback_table(result, inputs, "nwe"), hide_index=True, width="stretch")

    with asia_box:
        delta_text, delta_colour = spread_delta(result["spread"])    # positive = Asia ahead
        st.metric(
            f"🌏 Asia (North Asia, JKM), {route_label(port_key, result['asia_route'])}",
            dollars(result["netback_asia"]),
            delta=f"{delta_text} vs Europe",
            delta_color=delta_colour,
        )
        st.dataframe(netback_table(result, inputs, "asia"), hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# 7. FOB cost and margins
# ---------------------------------------------------------------------------

def show_margins(result):
    """Show the cost of the cargo at the load port and the margin of the best destination.

    US ports only: non-US cargoes have no Henry Hub cost and no cancel option.
    """
    section_header("FOB cost and margins")

    if not is_us_port(result["port"]):
        port = config.LOAD_PORTS[result["port"]]
        st.caption(f"No FOB cost or margin for a cargo from {port['name']} ({port['country']}): "
                   "these cargoes are mostly sold on oil-linked long-term contracts with no "
                   "cancel option, so the question is only which destination pays more.")
        return

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
    route_key = result["asia_route"]
    route_text = route_label(inputs["port_key"], route_key)          # e.g. "via Panama"
    current_freight = inputs["route_freight"][route_key]
    jkm_low, jkm_high = charts.chart_range(inputs["jkm"], breakeven_jkm)
    jkm_values = [jkm_low + (jkm_high - jkm_low) * i / (config.HEATMAP_POINTS - 1)
                  for i in range(config.HEATMAP_POINTS)]
    freight_values = charts.heatmap_freight_range(current_freight)
    outcomes, spreads = arb_calc.decision_grid(inputs, jkm_values, freight_values)
    st.plotly_chart(
        charts.decision_heatmap(jkm_values, freight_values, outcomes, spreads,
                                inputs["jkm"], current_freight, route_text),
        width="stretch", config={"displayModeBar": False})
    st.caption(f"Each cell re-runs the full calculation with that JKM and that Asia freight "
               f"({route_text}), everything else as in this evaluation. If that route gets too "
               "expensive, the cargo may switch to another open Asia route. "
               "Hover a cell for its spread.")


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
               "Markets closed (e.g. weekends) show 🔴. JKM is a futures daily settlement, so always 🔴.")


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

    st.caption(f"{len(log)} refreshes recorded in {config.LOG_FILE_PATH}: a Sabine Pass cargo "
               "(Panama or Cape) at live market prices, with your latest cost assumptions. "
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
        # The log always uses FRONT-month prices, so its history stays comparable,
        # and always a Sabine Pass cargo (Panama or Cape), whatever port is evaluated.
        market_inputs = sabine_pass_inputs(market_gas_prices(prices, DELIVERY_FRONT), current_costs())
        market_result = arb_calc.calculate_arb(**market_inputs)
        log_if_new_prices(fetched_at, prices, market_inputs, market_result)
    else:
        missing = [q.name for q in (hh, ttf, eurusd) if q.value is None]
        st.error(f"No market price for: {', '.join(missing)}. Check your internet connection, "
                 "then click 'Refresh prices'. You can still evaluate a cargo by typing prices.")

    show_log()


# ---------------------------------------------------------------------------
# 10. History tab (V3)
# ---------------------------------------------------------------------------

# Period selector: label -> number of years (None = everything)
HISTORY_PERIODS = {"1Y": 1, "3Y": 3, "5Y": 5, "All": None}


def history_inputs():
    """The cost assumptions applied to every month: the latest ones (last evaluation, or defaults).

    The history is for a Sabine Pass cargo (Panama or Cape), like the log.
    sabine_pass_inputs also needs gas prices, but historical_arb replaces them with
    each month's prices, so zeros are fine here.
    """
    placeholder_gas = {"henry_hub": 0.0, "ttf_eur_mwh": 0.0, "eurusd": 1.0, "jkm": 0.0}
    return sabine_pass_inputs(placeholder_gas, current_costs())


def history_tab():
    """The History tab: how the Europe/Asia arb looked month by month since 2014."""
    history = load_history()

    # If any download failed, say which and stop here (the Evaluate tab still works)
    failed = [series for series in history.values() if series.status == "failed"]
    if failed:
        names = ", ".join(series.name for series in failed)
        st.error(f"Could not load the history for: {names}. Check your internet connection "
                 "and reload the page later. The 'Evaluate a cargo' tab still works.")
        # Forget this failed attempt, so the next page load tries again
        # (otherwise the failure would be kept in memory for 24 hours)
        load_history.clear()
        return

    inputs = history_inputs()
    table = arb_calc.historical_arb(history["europe"].values, history["henry_hub"].values,
                                    history["jkm"].values, inputs)

    section_header("Arb history · month by month")
    first, last = table["month"].iloc[0], table["month"].iloc[-1]
    st.caption(f"A **Sabine Pass** cargo (Panama or Cape), each month priced like today's "
               f"evaluation: that month's average gas prices "
               f"with **your current costs** (freight, regas, fees, threshold). Freight and regas "
               f"history isn't free anywhere, so this shows how **gas prices alone** moved the arb. "
               f"Data: {first:%b %Y} to {last:%b %Y}, {len(table)} months.")

    # st.segmented_control: a row of buttons where one option is selected at a time
    period = st.segmented_control("Period", list(HISTORY_PERIODS), default="All",
                                  label_visibility="collapsed")
    if period is None:          # clicking the selected button again un-selects it
        period = "All"
    shown = arb_calc.last_years(table, HISTORY_PERIODS[period])

    st.plotly_chart(charts.arb_over_time_chart(shown, inputs["threshold"]),
                    width="stretch", config={"displayModeBar": False})
    st.caption("Bars above zero: Asia paid more. Below zero: Europe paid more. "
               "Shaded band: Indifferent (± threshold). Red: the cargo would have been cancelled. "
               "Hover a bar for both netbacks and the route.")

    # Win rates: one tile per outcome, then a stacked bar per calendar year
    section_header(f"Win rates · {period} ({len(shown)} months)")
    rates = arb_calc.win_rates(shown)
    tiles = st.columns(len(arb_calc.OUTCOMES))
    for tile, name in zip(tiles, arb_calc.OUTCOMES):   # zip pairs each tile with an outcome
        months_won = int((shown["outcome"] == name).sum())
        # delta_arrow="off": the month count is a count, not a rise, so no ↑ arrow
        tile.metric(name, f"{rates[name]:.0f}%", f"{months_won} months",
                    delta_color="off", delta_arrow="off")
    st.plotly_chart(charts.win_rate_by_year_chart(arb_calc.win_rates_by_year(shown)),
                    width="stretch", config={"displayModeBar": False})
    st.caption("Share of months each destination paid more, per calendar year. "
               "The first and last years may be partial.")

    # Seasonality: the average spread per calendar month
    section_header(f"Seasonality · {period}")
    st.plotly_chart(charts.seasonality_chart(arb_calc.seasonality(shown)),
                    width="stretch", config={"displayModeBar": False})
    st.caption("Average spread for each calendar month over the period: amber when Asia "
               "paid more on average, blue when Europe did. Hover a bar to see how many months "
               "it averages (with 1Y, each bar is a single month).")

    # The monthly table, to download
    st.download_button(
        f"⬇️ Download the monthly arb ({period}, CSV)",
        data=shown.round(4).to_csv(index=False),
        file_name=f"lng_arb_history_{period}.csv",
        mime="text/csv",
    )

    # Sources and timestamps, as for every price in the app
    source_lines = [f"{series.name}: {series.source}, downloaded "
                    f"{series.fetched_at:%d %b %H:%M UTC}, last month {series.values.index[-1]:%b %Y}"
                    for series in history.values()]
    st.caption("Sources · " + " · ".join(source_lines))


# ---------------------------------------------------------------------------
# Main page: runs top to bottom
# ---------------------------------------------------------------------------

# Header bar: title on the left, the two buttons on the right
title_box, buttons_box = st.columns([3, 2], vertical_alignment="bottom")
title_box.markdown(
    '<div class="app-kicker">LNG ARB ▸ NINE LOAD PORTS ▸ FOB</div>'
    '<div class="app-title">Europe or Asia?</div>'
    '<div class="app-sub">Where should an LNG cargo go right now, and by how much? '
    'US, Qatar, Australia, Canada, Nigeria, Norway, Trinidad · '
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

# st.tabs splits the page into tabs; "with tab:" puts everything below it inside that tab
evaluate_tab, history_tab_box = st.tabs(["Evaluate a cargo", "History"])

with evaluate_tab:
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

        section_header(f"Routes from {port_name(evaluation['inputs']['port_key'])}")
        st.info("The route map is being rebuilt for all nine ports (V4 step 5).")

        show_netbacks(evaluation["result"], evaluation["inputs"])
        show_margins(evaluation["result"])
        show_sensitivity(evaluation)

    st.divider()   # a thin horizontal line
    live_market()

with history_tab_box:
    history_tab()
