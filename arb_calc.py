"""
arb_calc.py: the LNG arbitrage formulas (SPEC.md section 6).

This file ONLY does maths:
  - it does not fetch prices (that's market_data.py)
  - it does not display anything (that's app.py)
That makes it easy to test: same inputs always give the same answer.

All prices are in USD/MMBtu, except TTF before conversion (EUR/MWh).
"""

import pandas as pd

import config


# ---------------------------------------------------------------------------
# Building blocks: one small function per formula
# ---------------------------------------------------------------------------

def ttf_to_usd_mmbtu(ttf_eur_mwh, eurusd):
    """Convert a TTF price from EUR/MWh to USD/MMBtu.

    Step 1: EUR -> USD by multiplying by EURUSD (dollars per euro).
    Step 2: per MWh -> per MMBtu by dividing by 3.412 (1 MWh = 3.412 MMBtu).
    """
    return ttf_eur_mwh * eurusd / config.MMBTU_PER_MWH


def fob_variable_cost(henry_hub):
    """Cost of the feed gas at Sabine Pass: 115% of Henry Hub.

    This is the only cost the offtaker can still avoid by cancelling the cargo.
    """
    return config.HH_MULTIPLIER * henry_hub


def fob_full_cost(henry_hub, liquefaction_fee):
    """Full cost of the cargo at Sabine Pass: 115% HH plus the liquefaction fee.

    The fee is paid whether or not the cargo is lifted (it's sunk), so it
    tells us if the cargo makes money overall, not whether to cancel.
    """
    return fob_variable_cost(henry_hub) + liquefaction_fee


def netback(hub_price, freight, regas, boil_off=0.0):
    """Netback = what the cargo is worth back at Sabine Pass, per MMBtu LOADED.

    Take the price at the destination hub, minus regas (turning it back into gas),
    on the gas that actually ARRIVES (1 - boil_off), then minus freight.

    boil_off: share of the cargo lost on the way (e.g. 0.014 = 1.4%).
    With boil_off = 0 (the default) this is simply hub - regas - freight (V1).
    """
    return (hub_price - regas) * (1 - boil_off) - freight


# ---------------------------------------------------------------------------
# Detailed freight model (V2): freight and boil-off from voyage inputs
# ---------------------------------------------------------------------------

def voyage_freight(charter_rate, one_way_days, cargo_mmbtu,
                   canal_toll_per_transit=0.0, canal_transits=0):
    """Freight in USD per MMBtu loaded, for a ROUND-TRIP voyage.

    The charterer pays the ship for the trip out (laden) AND back (ballast),
    plus any canal tolls, and spreads that bill over the MMBtu loaded.
    """
    round_trip_days = 2 * one_way_days
    charter_cost = charter_rate * round_trip_days                  # USD
    canal_cost = canal_toll_per_transit * canal_transits           # USD
    return (charter_cost + canal_cost) / cargo_mmbtu


def boil_off_fraction(boil_off_pct_per_day, laden_days):
    """Share of the cargo that evaporates on the laden leg.

    Example: 0.10% per day x 14 days = 1.4%, returned as 0.014.
    """
    return boil_off_pct_per_day / 100 * laden_days


def detailed_freight(charter_rate, cargo_mmbtu, boil_off_pct_per_day,
                     days_nwe, days_panama, days_cape, panama_toll):
    """Run the voyage model for the three routes.

    Returns a dictionary per route ("nwe", "panama", "cape") with the
    build-up: round-trip days, charter cost, canal cost, freight ($/MMBtu)
    and boil-off (fraction). The Panama route pays the toll twice
    (going laden, coming back in ballast).
    """
    routes = {
        "nwe": {"one_way_days": days_nwe, "canal_transits": 0},
        "panama": {"one_way_days": days_panama, "canal_transits": 2},
        "cape": {"one_way_days": days_cape, "canal_transits": 0},
    }

    build_up = {}
    for route, voyage in routes.items():   # .items() gives each (name, details) pair
        days = voyage["one_way_days"]
        transits = voyage["canal_transits"]
        build_up[route] = {
            "round_trip_days": 2 * days,
            "charter_cost": charter_rate * 2 * days,
            "canal_cost": panama_toll * transits,
            "freight": voyage_freight(charter_rate, days, cargo_mmbtu, panama_toll, transits),
            "boil_off": boil_off_fraction(boil_off_pct_per_day, days),
        }
    return build_up


def choose_asia_route(netback_panama, netback_cape, panama_available):
    """Pick the Asia route with the higher netback (i.e. the cheaper freight).

    If the Panama Canal is unavailable (congestion, draft limits),
    the cargo has to go via the Cape of Good Hope.

    Returns two things: (best Asia netback, route name).
    """
    if panama_available and netback_panama >= netback_cape:
        return netback_panama, "Panama"
    return netback_cape, "Cape"


def destination_verdict(netback_europe, netback_asia, threshold):
    """Decide which destination wins, and by how much.

    spread = Asia netback minus Europe netback
      positive -> Asia pays more
      negative -> Europe pays more
    If the gap is smaller than the threshold, call it "Indifferent".

    Returns two things: (winner, spread).
    """
    spread = netback_asia - netback_europe

    if abs(spread) < threshold:      # abs() removes the sign: abs(-0.3) = 0.3
        winner = "Indifferent"
    elif spread > 0:
        winner = "Asia"
    else:
        winner = "Europe"

    return winner, spread


def lift_or_cancel(best_netback, fob_variable):
    """Offtaker decision: lift the cargo, or cancel it.

    The liquefaction fee is sunk, so we only compare the best netback
    with the avoidable cost (115% HH). If the netback can't cover it,
    the cargo loses more by lifting than by cancelling.
    """
    if best_netback < fob_variable:
        return "CANCEL"
    return "LIFT"


# ---------------------------------------------------------------------------
# The full calculation: runs every building block in order
# ---------------------------------------------------------------------------

def calculate_arb(
    henry_hub,
    ttf_eur_mwh,
    eurusd,
    jkm,
    freight_nwe,
    freight_panama,
    freight_cape,
    regas_europe,
    regas_asia,
    liquefaction_fee,
    panama_available=config.DEFAULT_PANAMA_AVAILABLE,
    threshold=config.DEFAULT_INDIFFERENCE_THRESHOLD,
    boil_off_nwe=0.0,
    boil_off_panama=0.0,
    boil_off_cape=0.0,
    ttf_usd=None,
):
    """Run the whole arb calculation and return every result in a dictionary.

    A dictionary is a set of labelled values, e.g. result["netback_europe"].
    The app displays these values, and the log saves them.

    boil_off_*: share of the cargo lost per route (Detailed freight mode).
    Left at 0 (Simple mode), the results are exactly the V1 ones.
    ttf_usd: only for prices already in USD/MMBtu (the FRED history). If given,
    ttf_eur_mwh and eurusd are ignored and no conversion is done.
    """
    # 1. Put TTF in the same unit as everything else (USD/MMBtu)
    if ttf_usd is None:
        ttf_usd = ttf_to_usd_mmbtu(ttf_eur_mwh, eurusd)

    # 2. Cost of the cargo at Sabine Pass
    fob_variable = fob_variable_cost(henry_hub)
    fob_full = fob_full_cost(henry_hub, liquefaction_fee)

    # 3. Netbacks: Europe, and Asia by both routes (boil-off is 0 in Simple mode)
    netback_europe = netback(ttf_usd, freight_nwe, regas_europe, boil_off_nwe)
    netback_asia_panama = netback(jkm, freight_panama, regas_asia, boil_off_panama)
    netback_asia_cape = netback(jkm, freight_cape, regas_asia, boil_off_cape)

    # 4. Best Asia route
    netback_asia, asia_route = choose_asia_route(
        netback_asia_panama, netback_asia_cape, panama_available
    )

    # 5. Europe vs Asia
    winner, spread = destination_verdict(netback_europe, netback_asia, threshold)

    # 6. Lift or cancel, and the margins
    best_netback = max(netback_europe, netback_asia)
    decision = lift_or_cancel(best_netback, fob_variable)
    margin_variable = best_netback - fob_variable   # vs avoidable cost
    margin_full = best_netback - fob_full           # vs full cost incl. fee

    # 7. Boil-off loss per route, in $/MMBtu loaded (for display):
    #    the value of the gas that evaporated = (hub - regas) x boil-off share
    boil_off_loss_europe = (ttf_usd - regas_europe) * boil_off_nwe
    boil_off_loss_panama = (jkm - regas_asia) * boil_off_panama
    boil_off_loss_cape = (jkm - regas_asia) * boil_off_cape

    return {
        "boil_off_loss_europe": boil_off_loss_europe,
        "boil_off_loss_panama": boil_off_loss_panama,
        "boil_off_loss_cape": boil_off_loss_cape,
        "ttf_usd": ttf_usd,
        "fob_variable": fob_variable,
        "fob_full": fob_full,
        "netback_europe": netback_europe,
        "netback_asia_panama": netback_asia_panama,
        "netback_asia_cape": netback_asia_cape,
        "netback_asia": netback_asia,
        "asia_route": asia_route,
        "spread": spread,
        "winner": winner,
        "best_netback": best_netback,
        "decision": decision,
        "margin_variable": margin_variable,
        "margin_full": margin_full,
    }


# ---------------------------------------------------------------------------
# Sensitivity (V2): breakevens and spread curves
# ---------------------------------------------------------------------------
# "inputs" below is the same dictionary calculate_arb takes (the evaluation's inputs).
# inputs.get("boil_off_nwe", 0.0) means "the boil-off if it's there, otherwise 0"
# (Simple mode may leave it out, just like calculate_arb's default).

def breakeven_jkm(inputs):
    """The JKM price (USD/MMBtu) at which Asia's best netback equals Europe's.

    Asia netback for a route = (JKM - regas) x (1 - boil-off) - freight.
    Setting it equal to the Europe netback and solving for JKM gives:
        JKM = regas_asia + (netback_europe + freight) / (1 - boil-off)
    Each open route gives one answer; the breakeven is the LOWEST one,
    because the cheapest route reaches parity first.
    """
    result = calculate_arb(**inputs)
    candidates = [
        inputs["regas_asia"]
        + (result["netback_europe"] + inputs["freight_cape"]) / (1 - inputs.get("boil_off_cape", 0.0))
    ]
    if inputs["panama_available"]:
        candidates.append(
            inputs["regas_asia"]
            + (result["netback_europe"] + inputs["freight_panama"]) / (1 - inputs.get("boil_off_panama", 0.0))
        )
    return min(candidates)


def breakeven_ttf(inputs):
    """The TTF price (EUR/MWh) at which Europe's netback equals Asia's best netback.

    Europe netback = (TTF_usd - regas) x (1 - boil-off) - freight. Solving for TTF:
        TTF_usd = regas_europe + (netback_asia + freight_nwe) / (1 - boil-off_nwe)
    then converted back to EUR/MWh: x 3.412 / EURUSD.
    """
    result = calculate_arb(**inputs)
    ttf_usd = (inputs["regas_europe"]
               + (result["netback_asia"] + inputs["freight_nwe"]) / (1 - inputs.get("boil_off_nwe", 0.0)))
    return ttf_usd * config.MMBTU_PER_MWH / inputs["eurusd"]


def spread_curve(inputs, price_name, low, high, points=config.SENSITIVITY_POINTS):
    """Re-run the arb for a range of one price, keeping everything else fixed.

    price_name: "jkm" or "ttf_eur_mwh"
    Returns two lists: the prices tried, and the spread (Asia - Europe) at each.
    """
    prices = []
    spreads = []
    for i in range(points):
        price = low + (high - low) * i / (points - 1)    # evenly spaced from low to high
        changed = dict(inputs)                            # a copy, so we don't alter the original
        changed[price_name] = price
        prices.append(price)
        spreads.append(calculate_arb(**changed)["spread"])
    return prices, spreads


# ---------------------------------------------------------------------------
# Decision heatmap (V2): the outcome for every JKM x Asia freight combination
# ---------------------------------------------------------------------------

OUTCOMES = ["Europe", "Asia", "Indifferent", "Cancel"]   # the four possible answers


def outcome(result):
    """Sum up a result in one word: "Europe", "Asia", "Indifferent" or "Cancel"."""
    if result["decision"] == "CANCEL":
        return "Cancel"
    return result["winner"]


def decision_grid(inputs, jkm_values, freight_values):
    """Re-run the arb for every (JKM, Asia freight) pair.

    freight_values replace the freight of the Asia route chosen in `inputs`
    (Panama or Cape); the other route keeps its own freight, so the app may
    switch routes if that one becomes cheaper.

    Returns two grids (lists of rows, one row per freight value):
      outcomes: the one-word outcome of each cell
      spreads:  the spread (Asia - Europe) of each cell
    """
    chosen_route = calculate_arb(**inputs)["asia_route"]          # "Panama" or "Cape"
    freight_key = "freight_panama" if chosen_route == "Panama" else "freight_cape"

    outcomes = []
    spreads = []
    for freight in freight_values:          # one row per freight level
        outcome_row = []
        spread_row = []
        for jkm in jkm_values:              # one cell per JKM level
            changed = dict(inputs)
            changed["jkm"] = jkm
            changed[freight_key] = freight
            result = calculate_arb(**changed)
            outcome_row.append(outcome(result))
            spread_row.append(result["spread"])
        outcomes.append(outcome_row)
        spreads.append(spread_row)
    return outcomes, spreads


# ---------------------------------------------------------------------------
# History (V3): the arb month by month, win rates, seasonality
# ---------------------------------------------------------------------------

def historical_arb(europe, henry_hub, jkm, inputs):
    """Re-run today's arb calculation for every month in the history.

    europe, henry_hub, jkm: monthly prices in USD/MMBtu (pandas Series, one
        value per month, labelled by the first day of the month).
    inputs: the current evaluation's inputs. Only its COSTS are used
        (freight, boil-off, regas, fee, Panama, threshold); the gas prices
        are replaced by each month's prices.

    Only months where all three prices exist are kept.
    Returns a table (pandas DataFrame) with one row per month.
    """
    # The months the three series have in common, oldest first
    months = europe.index.intersection(henry_hub.index).intersection(jkm.index).sort_values()

    rows = []
    for month in months:
        month_inputs = dict(inputs)
        month_inputs["henry_hub"] = float(henry_hub[month])
        month_inputs["jkm"] = float(jkm[month])
        month_inputs["ttf_usd"] = float(europe[month])   # already USD/MMBtu: no conversion
        result = calculate_arb(**month_inputs)

        rows.append({
            "month": month,
            "henry_hub": month_inputs["henry_hub"],
            "europe": month_inputs["ttf_usd"],
            "jkm": month_inputs["jkm"],
            "netback_europe": result["netback_europe"],
            "netback_asia": result["netback_asia"],
            "asia_route": result["asia_route"],
            "spread": result["spread"],              # Asia - Europe
            "outcome": outcome(result),              # Europe / Asia / Indifferent / Cancel
            "margin_variable": result["margin_variable"],
        })
    return pd.DataFrame(rows)


def last_years(table, years):
    """Keep only the last `years` years of a monthly table (years=None keeps everything).

    1 year = the last 12 months in the table, 3 years = the last 36, and so on.
    """
    if years is None:
        return table
    return table.tail(years * 12)


def win_rates(table):
    """Share of months (in %) for each outcome. The four shares add up to 100.

    An outcome that never happened gets 0.
    """
    total = len(table)
    rates = {}
    for name in OUTCOMES:
        months_won = (table["outcome"] == name).sum()   # count the rows with this outcome
        rates[name] = 100 * months_won / total if total else 0.0
    return rates


def win_rates_by_year(table):
    """Win rates (in %) for each calendar year: one row per year, one column per outcome."""
    years = table["month"].dt.year          # .dt.year takes the year out of each date
    rows = []
    for year in sorted(years.unique()):
        year_rates = win_rates(table[years == year])
        rows.append({"year": int(year), **year_rates})
    return pd.DataFrame(rows, columns=["year"] + OUTCOMES)


def seasonality(table):
    """Average spread (Asia - Europe) for each calendar month, Jan to Dec.

    Only calendar months present in the table are returned.
    Columns: month_number (1-12), month_name ("Jan"), average_spread, months (how many).
    """
    month_numbers = table["month"].dt.month
    rows = []
    for number in sorted(month_numbers.unique()):
        spreads = table.loc[month_numbers == number, "spread"]
        rows.append({
            "month_number": int(number),
            "month_name": pd.Timestamp(2000, int(number), 1).strftime("%b"),
            "average_spread": spreads.mean(),
            "months": len(spreads),
        })
    return pd.DataFrame(rows)
