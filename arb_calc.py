"""
arb_calc.py: the LNG arbitrage formulas (SPEC.md section 6).

This file ONLY does maths:
  - it does not fetch prices (that's market_data.py)
  - it does not display anything (that's app.py)
That makes it easy to test: same inputs always give the same answer.

All prices are in USD/MMBtu, except TTF before conversion (EUR/MWh).
"""

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


def netback(hub_price, freight, regas):
    """Netback = what the cargo is worth back at Sabine Pass.

    Take the price at the destination hub, then subtract the cost
    of getting it there (freight) and turning it back into gas (regas).
    """
    return hub_price - freight - regas


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
):
    """Run the whole arb calculation and return every result in a dictionary.

    A dictionary is a set of labelled values, e.g. result["netback_europe"].
    The app displays these values, and the log saves them.
    """
    # 1. Put TTF in the same unit as everything else (USD/MMBtu)
    ttf_usd = ttf_to_usd_mmbtu(ttf_eur_mwh, eurusd)

    # 2. Cost of the cargo at Sabine Pass
    fob_variable = fob_variable_cost(henry_hub)
    fob_full = fob_full_cost(henry_hub, liquefaction_fee)

    # 3. Netbacks: Europe, and Asia by both routes
    netback_europe = netback(ttf_usd, freight_nwe, regas_europe)
    netback_asia_panama = netback(jkm, freight_panama, regas_asia)
    netback_asia_cape = netback(jkm, freight_cape, regas_asia)

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

    return {
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
