"""
Tests for arb_log.py.

tmp_path is a pytest feature: a fresh empty folder created just for
the test, so we never touch the real data/arb_log.csv.
"""

from datetime import datetime, timezone

import arb_calc
import arb_log
import market_data

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)

INPUTS = {
    "jkm": 12.00, "freight_nwe": 0.90, "freight_panama": 1.60, "freight_cape": 2.10,
    "regas_europe": 0.45, "regas_asia": 0.35, "liquefaction_fee": 2.50,
    "panama_available": True, "threshold": 0.10,
}


def make_prices():
    """Three fake Quotes (same base case as test_arb_calc.py)."""
    def quote(name, value):
        return market_data.Quote(name, value, "u", "yfinance (delayed)", NOW, "fresh")
    return {"henry_hub": quote("HH", 3.00), "ttf": quote("TTF", 35.00), "eurusd": quote("EURUSD", 1.10)}


def make_row():
    prices = make_prices()
    result = arb_calc.calculate_arb(
        henry_hub=3.00, ttf_eur_mwh=35.00, eurusd=1.10, **INPUTS
    )
    return arb_log.build_log_row(NOW, prices, INPUTS, result)


def test_row_has_every_column_and_right_values():
    row = make_row()
    assert list(row.keys()) == arb_log.LOG_COLUMNS
    assert row["verdict"] == "LIFT Asia"
    assert row["asia_route"] == "Panama"
    assert row["netback_asia"] == 10.05
    assert row["hh_ts"] == "2026-11-13 15:00:00 UTC"


def test_append_creates_file_then_adds_rows(tmp_path):
    log_file = tmp_path / "data" / "arb_log.csv"   # folder doesn't exist yet

    arb_log.append_row(make_row(), path=str(log_file))
    arb_log.append_row(make_row(), path=str(log_file))

    log = arb_log.read_log(path=str(log_file))
    assert len(log) == 2                               # two refreshes = two rows
    assert list(log.columns) == arb_log.LOG_COLUMNS    # header written once, correctly


def test_reading_missing_log_gives_empty_table(tmp_path):
    log = arb_log.read_log(path=str(tmp_path / "nothing.csv"))
    assert len(log) == 0
