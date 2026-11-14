"""
arb_log.py: the app's diary of refreshes.

Every time new prices are fetched, one row is added to data/arb_log.csv
with every price (and its timestamp and status), every input, and every
result. Over time this file becomes the app's own arb history (used in V3).

A CSV file is a plain-text table: one line per row, values separated by
commas. It opens directly in Excel.
"""

import os

import pandas as pd

import config


# The columns of the log, in order (SPEC.md section 9)
LOG_COLUMNS = [
    "refresh_time_utc",
    "hh", "hh_ts", "hh_status",
    "ttf_eur_mwh", "ttf_ts", "ttf_status",
    "eurusd", "eurusd_ts", "eurusd_status",
    "ttf_usd", "jkm",
    "freight_nwe", "freight_panama", "freight_cape",
    "regas_eu", "regas_asia", "liq_fee", "panama_available",
    "fob_variable", "fob_full",
    "netback_eu", "netback_asia", "asia_route",
    "spread", "verdict", "margin_variable", "margin_full",
]


def time_text(timestamp):
    """Write a time as text for the CSV, e.g. '2026-11-13 21:59:00 UTC' (or '' if missing)."""
    if timestamp is None:
        return ""
    return timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")


def verdict_text(result):
    """One short label for the decision, e.g. 'LIFT Asia', 'LIFT Indifferent', 'CANCEL'."""
    if result["decision"] == "CANCEL":
        return "CANCEL"
    return f"LIFT {result['winner']}"


def build_log_row(refresh_time, prices, inputs, result):
    """Collect everything about one refresh into a dictionary (one CSV row).

    refresh_time: when the prices were fetched
    prices: the dictionary of Quotes from market_data.get_market_prices()
    inputs: the sidebar inputs
    result: the output of arb_calc.calculate_arb()
    """
    hh = prices["henry_hub"]
    ttf = prices["ttf"]
    eurusd = prices["eurusd"]

    return {
        "refresh_time_utc": time_text(refresh_time),
        "hh": hh.value, "hh_ts": time_text(hh.timestamp), "hh_status": hh.status,
        "ttf_eur_mwh": ttf.value, "ttf_ts": time_text(ttf.timestamp), "ttf_status": ttf.status,
        "eurusd": eurusd.value, "eurusd_ts": time_text(eurusd.timestamp), "eurusd_status": eurusd.status,
        "ttf_usd": round(result["ttf_usd"], 4),
        "jkm": inputs["jkm"],
        "freight_nwe": inputs["freight_nwe"],
        "freight_panama": inputs["freight_panama"],
        "freight_cape": inputs["freight_cape"],
        "regas_eu": inputs["regas_europe"],
        "regas_asia": inputs["regas_asia"],
        "liq_fee": inputs["liquefaction_fee"],
        "panama_available": inputs["panama_available"],
        "fob_variable": round(result["fob_variable"], 4),
        "fob_full": round(result["fob_full"], 4),
        "netback_eu": round(result["netback_europe"], 4),
        "netback_asia": round(result["netback_asia"], 4),
        "asia_route": result["asia_route"],
        "spread": round(result["spread"], 4),
        "verdict": verdict_text(result),
        "margin_variable": round(result["margin_variable"], 4),
        "margin_full": round(result["margin_full"], 4),
    }


def append_row(row, path=config.LOG_FILE_PATH):
    """Add one row to the end of the CSV log, creating the file (and folder) if needed."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)   # create data/ if it doesn't exist yet

    file_is_new = not os.path.exists(path)

    table = pd.DataFrame([row], columns=LOG_COLUMNS)
    # mode="a" = append to the end; header only the first time (when the file is new)
    table.to_csv(path, mode="a", header=file_is_new, index=False)


def read_log(path=config.LOG_FILE_PATH):
    """Read the whole log as a table. Returns an empty table if there's no log yet."""
    if not os.path.exists(path):
        return pd.DataFrame(columns=LOG_COLUMNS)
    return pd.read_csv(path)
