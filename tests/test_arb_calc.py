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
