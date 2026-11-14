"""
Tests for arb_calc.py: hand-calculated examples, checked by pytest.

Run them with:   pytest
Each function starting with "test_" is one check. If the code's answer
differs from the hand calculation, pytest prints a red FAILED line.

pytest.approx(x) means "equal to x, allowing for tiny rounding differences",
because computers store decimals like 0.1 slightly imprecisely.
"""

import pytest

import arb_calc


# One base case, used by most tests (all USD/MMBtu except TTF in EUR/MWh).
BASE_INPUTS = {
    "henry_hub": 3.00,
    "ttf_eur_mwh": 35.00,
    "eurusd": 1.10,
    "jkm": 12.00,
    "freight_nwe": 0.90,
    "freight_panama": 1.60,
    "freight_cape": 2.10,
    "regas_europe": 0.45,
    "regas_asia": 0.35,
    "liquefaction_fee": 2.50,
    "panama_available": True,
    "threshold": 0.10,
}


def test_ttf_conversion():
    # 35 EUR/MWh x 1.10 USD/EUR / 3.412 MMBtu/MWh = 11.2837 USD/MMBtu
    assert arb_calc.ttf_to_usd_mmbtu(35.00, 1.10) == pytest.approx(11.283705, abs=1e-6)


def test_fob_costs():
    # Variable: 1.15 x 3.00 = 3.45 ; Full: 3.45 + 2.50 = 5.95
    assert arb_calc.fob_variable_cost(3.00) == pytest.approx(3.45)
    assert arb_calc.fob_full_cost(3.00, 2.50) == pytest.approx(5.95)


def test_netback():
    # 12.00 - 1.60 - 0.35 = 10.05
    assert arb_calc.netback(12.00, 1.60, 0.35) == pytest.approx(10.05)


def test_base_case_asia_wins_via_panama():
    result = arb_calc.calculate_arb(**BASE_INPUTS)   # ** unpacks the dict into named inputs

    # Europe: 11.2837 - 0.90 - 0.45 = 9.9337
    assert result["netback_europe"] == pytest.approx(9.933705, abs=1e-6)
    # Asia: Panama 10.05 beats Cape 9.55
    assert result["netback_asia_panama"] == pytest.approx(10.05)
    assert result["netback_asia_cape"] == pytest.approx(9.55)
    assert result["asia_route"] == "Panama"
    assert result["netback_asia"] == pytest.approx(10.05)
    # Spread 10.05 - 9.9337 = +0.1163, above the 0.10 threshold -> Asia
    assert result["spread"] == pytest.approx(0.116295, abs=1e-6)
    assert result["winner"] == "Asia"
    # Margins: 10.05 - 3.45 = 6.60 ; 10.05 - 5.95 = 4.10 -> LIFT
    assert result["margin_variable"] == pytest.approx(6.60)
    assert result["margin_full"] == pytest.approx(4.10)
    assert result["decision"] == "LIFT"


def test_panama_closed_sends_cargo_to_europe():
    inputs = dict(BASE_INPUTS, panama_available=False)   # copy, with one change
    result = arb_calc.calculate_arb(**inputs)

    # Asia must go via Cape: 9.55. Spread 9.55 - 9.9337 = -0.3837 -> Europe
    assert result["asia_route"] == "Cape"
    assert result["netback_asia"] == pytest.approx(9.55)
    assert result["winner"] == "Europe"
    assert result["spread"] == pytest.approx(-0.383705, abs=1e-6)


def test_wider_threshold_gives_indifferent():
    inputs = dict(BASE_INPUTS, threshold=0.20)
    result = arb_calc.calculate_arb(**inputs)

    # Spread of 0.1163 is now inside the 0.20 band
    assert result["winner"] == "Indifferent"


def test_expensive_henry_hub_cancels_cargo():
    inputs = dict(BASE_INPUTS, henry_hub=10.00)
    result = arb_calc.calculate_arb(**inputs)

    # FOB variable = 1.15 x 10 = 11.50, above the best netback of 10.05
    assert result["margin_variable"] == pytest.approx(-1.45)
    assert result["decision"] == "CANCEL"


def test_lift_even_when_full_cost_not_covered():
    # Key offtaker logic: the fee is sunk, so a cargo can lose money overall
    # and STILL be worth lifting. HH 6.00 and a high fee of 4.00 show this.
    inputs = dict(BASE_INPUTS, henry_hub=6.00, liquefaction_fee=4.00)
    result = arb_calc.calculate_arb(**inputs)

    # Variable: 10.05 - 6.90 = 3.15 (positive -> lift)
    # Full: 10.05 - 10.90 = -0.85 (loses money overall, but less than cancelling)
    assert result["margin_variable"] == pytest.approx(3.15)
    assert result["margin_full"] == pytest.approx(-0.85)
    assert result["decision"] == "LIFT"


# ---------------------------------------------------------------------------
# V2: detailed freight model and boil-off (SPEC.md section 12.3)
# ---------------------------------------------------------------------------

# Default voyage inputs from the spec
VOYAGE = {
    "charter_rate": 80_000, "cargo_mmbtu": 3_500_000, "boil_off_pct_per_day": 0.10,
    "days_nwe": 14, "days_panama": 25, "days_cape": 40, "panama_toll": 500_000,
}


def test_voyage_freight_round_trip():
    # NWE: 80,000 $/day x 28 days = 2,240,000 $ / 3,500,000 MMBtu = 0.64 $/MMBtu
    assert arb_calc.voyage_freight(80_000, 14, 3_500_000) == pytest.approx(0.64)
    # Panama: 80,000 x 50 = 4.0m + 2 tolls x 0.5m = 5.0m / 3.5m = 1.428571
    assert arb_calc.voyage_freight(80_000, 25, 3_500_000, 500_000, 2) == pytest.approx(1.428571, abs=1e-6)


def test_boil_off_fraction():
    # 0.10% per day x 14 laden days = 1.4% = 0.014
    assert arb_calc.boil_off_fraction(0.10, 14) == pytest.approx(0.014)


def test_netback_with_boil_off():
    # (29.40 - 0.45) x (1 - 0.014) - 0.64 = 28.95 x 0.986 - 0.64 = 27.9047
    assert arb_calc.netback(29.40, 0.64, 0.45, boil_off=0.014) == pytest.approx(27.9047)


def test_netback_without_boil_off_is_v1():
    # Boil-off 0 must give exactly the V1 formula: 12.00 - 1.60 - 0.35 = 10.05
    assert arb_calc.netback(12.00, 1.60, 0.35, boil_off=0.0) == pytest.approx(10.05)


def test_detailed_freight_matches_spec_example():
    build_up = arb_calc.detailed_freight(**VOYAGE)

    assert build_up["nwe"]["freight"] == pytest.approx(0.640, abs=1e-3)
    assert build_up["panama"]["freight"] == pytest.approx(1.429, abs=1e-3)
    assert build_up["cape"]["freight"] == pytest.approx(1.829, abs=1e-3)

    assert build_up["nwe"]["boil_off"] == pytest.approx(0.014)
    assert build_up["panama"]["boil_off"] == pytest.approx(0.025)
    assert build_up["cape"]["boil_off"] == pytest.approx(0.040)

    assert build_up["panama"]["canal_cost"] == 1_000_000   # toll paid twice
    assert build_up["cape"]["canal_cost"] == 0
    assert build_up["cape"]["round_trip_days"] == 80


def test_boil_off_flips_base_case_to_europe():
    # V1 base case gave "Asia by 0.12". With the detailed model, the longer Asia
    # voyage loses more cargo, so Europe wins:
    #   Europe: (11.283705 - 0.45) x 0.986 - 0.640    = 10.042033
    #   Panama: (12.00 - 0.35)     x 0.975 - 1.428571 =  9.930179
    #   Cape:   (12.00 - 0.35)     x 0.960 - 1.828571 =  9.355429
    #   Spread = 9.930179 - 10.042033 = -0.111854 -> Europe (beyond 0.10)
    b = arb_calc.detailed_freight(**VOYAGE)
    inputs = dict(
        BASE_INPUTS,
        freight_nwe=b["nwe"]["freight"],
        freight_panama=b["panama"]["freight"],
        freight_cape=b["cape"]["freight"],
        boil_off_nwe=b["nwe"]["boil_off"],
        boil_off_panama=b["panama"]["boil_off"],
        boil_off_cape=b["cape"]["boil_off"],
    )
    result = arb_calc.calculate_arb(**inputs)

    assert result["netback_europe"] == pytest.approx(10.042033, abs=1e-6)
    assert result["netback_asia_panama"] == pytest.approx(9.930179, abs=1e-6)
    assert result["netback_asia_cape"] == pytest.approx(9.355429, abs=1e-6)
    assert result["asia_route"] == "Panama"
    assert result["spread"] == pytest.approx(-0.111854, abs=1e-6)
    assert result["winner"] == "Europe"

    # Boil-off loss = value of the evaporated gas: (hub - regas) x share
    #   Europe: (11.283705 - 0.45) x 0.014 = 0.151672
    #   Cape:   (12.00 - 0.35)     x 0.040 = 0.466
    assert result["boil_off_loss_europe"] == pytest.approx(0.151672, abs=1e-6)
    assert result["boil_off_loss_cape"] == pytest.approx(0.466)
    # The table must add up: hub - regas - boil-off loss - freight = netback
    assert (result["ttf_usd"] - 0.45 - result["boil_off_loss_europe"] - b["nwe"]["freight"]
            == pytest.approx(result["netback_europe"]))


# ---------------------------------------------------------------------------
# V2: breakevens and spread curves (SPEC.md 12.4, done criterion 6)
# ---------------------------------------------------------------------------

def test_breakeven_jkm_simple_mode():
    # Europe netback 9.933705. Cheapest Asia route is Panama (freight 1.60):
    #   JKM = regas 0.35 + (9.933705 + 1.60) / (1 - 0) = 11.883705
    breakeven = arb_calc.breakeven_jkm(BASE_INPUTS)
    assert breakeven == pytest.approx(11.883705, abs=1e-6)
    # ...and at that JKM the spread really is zero
    assert arb_calc.calculate_arb(**dict(BASE_INPUTS, jkm=breakeven))["spread"] == pytest.approx(0, abs=1e-9)


def test_breakeven_jkm_panama_closed_uses_cape():
    # Panama closed: only Cape (freight 2.10): 0.35 + 9.933705 + 2.10 = 12.383705
    inputs = dict(BASE_INPUTS, panama_available=False)
    assert arb_calc.breakeven_jkm(inputs) == pytest.approx(12.383705, abs=1e-6)


def test_breakeven_ttf_simple_mode():
    # Asia netback 10.05 (Panama). Europe parity:
    #   TTF_usd = 0.45 + (10.05 + 0.90) = 11.40 $/MMBtu
    #   in EUR/MWh: 11.40 x 3.412 / 1.10 = 35.360727
    breakeven = arb_calc.breakeven_ttf(BASE_INPUTS)
    assert breakeven == pytest.approx(35.360727, abs=1e-6)
    assert arb_calc.calculate_arb(**dict(BASE_INPUTS, ttf_eur_mwh=breakeven))["spread"] == pytest.approx(0, abs=1e-9)


def test_breakeven_jkm_detailed_mode_with_boil_off():
    # Europe netback 10.042033 (with boil-off). Panama: freight 1.428571, boil-off 2.5%:
    #   JKM = 0.35 + (10.042033 + 1.428571) / 0.975 = 12.114722
    b = arb_calc.detailed_freight(**VOYAGE)
    inputs = dict(
        BASE_INPUTS,
        freight_nwe=b["nwe"]["freight"], freight_panama=b["panama"]["freight"],
        freight_cape=b["cape"]["freight"], boil_off_nwe=b["nwe"]["boil_off"],
        boil_off_panama=b["panama"]["boil_off"], boil_off_cape=b["cape"]["boil_off"],
    )
    breakeven = arb_calc.breakeven_jkm(inputs)
    assert breakeven == pytest.approx(12.114722, abs=1e-6)
    assert arb_calc.calculate_arb(**dict(inputs, jkm=breakeven))["spread"] == pytest.approx(0, abs=1e-9)


def test_spread_curve_rises_with_jkm():
    prices, spreads = arb_calc.spread_curve(BASE_INPUTS, "jkm", 10.0, 14.0, points=5)
    assert prices == [10.0, 11.0, 12.0, 13.0, 14.0]
    assert spreads == sorted(spreads)                              # higher JKM -> Asia better
    assert spreads[2] == pytest.approx(0.116295, abs=1e-6)         # JKM 12 = the base case


# ---------------------------------------------------------------------------
# V2: decision heatmap (SPEC.md 12.4, done criterion 7)
# ---------------------------------------------------------------------------

def test_outcome_labels():
    assert arb_calc.outcome(arb_calc.calculate_arb(**BASE_INPUTS)) == "Asia"
    assert arb_calc.outcome(arb_calc.calculate_arb(**dict(BASE_INPUTS, threshold=0.20))) == "Indifferent"
    assert arb_calc.outcome(arb_calc.calculate_arb(**dict(BASE_INPUTS, panama_available=False))) == "Europe"
    assert arb_calc.outcome(arb_calc.calculate_arb(**dict(BASE_INPUTS, henry_hub=10.0))) == "Cancel"


def test_decision_grid_cells_by_hand():
    # Rows = Asia freight (Panama, the chosen route), columns = JKM
    outcomes, spreads = arb_calc.decision_grid(BASE_INPUTS, [11.0, 12.0], [1.60, 3.00])

    # JKM 12, freight 1.60: Panama 10.05 vs Europe 9.933705 -> +0.116295 -> Asia
    assert outcomes[0][1] == "Asia"
    assert spreads[0][1] == pytest.approx(0.116295, abs=1e-6)
    # JKM 11, freight 1.60: Panama 9.05 -> -0.883705 -> Europe
    assert outcomes[0][0] == "Europe"
    assert spreads[0][0] == pytest.approx(-0.883705, abs=1e-6)
    # JKM 12, Panama freight 3.00: Panama 8.65 is now worse than Cape 9.55,
    # so the cargo switches to the Cape: 9.55 - 9.933705 = -0.383705 -> Europe
    assert outcomes[1][1] == "Europe"
    assert spreads[1][1] == pytest.approx(-0.383705, abs=1e-6)


def test_decision_grid_shows_cancel():
    # HH at 10: FOB variable 11.50 is above every netback in the grid -> Cancel everywhere
    outcomes, _ = arb_calc.decision_grid(dict(BASE_INPUTS, henry_hub=10.0), [11.0, 12.0], [1.6])
    assert outcomes == [["Cancel", "Cancel"]]
