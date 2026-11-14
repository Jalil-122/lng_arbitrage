# LNG Arbitrage Dashboard: Specification

## 1. Purpose

A Streamlit dashboard that answers one desk question:

> **Should a US LNG cargo loading at Sabine Pass go to Europe or Asia right now, and by how much does the winner win?**

It also says whether the cargo should be lifted at all, or cancelled.

The tool is built like a trading desk tool. Every price passes through **one data module**, so a desk could swap yfinance for Bloomberg, ICE or Platts by changing only that module.

## 2. Roadmap

| Version | Scope |
|---|---|
| **V1** (this spec) | Calculator with live delayed prices (HH, TTF, EURUSD), JKM daily settlement as an editable prefill, user inputs (freight, fees), auto refresh, a status light for each price, and a refresh log |
| V2 | Route map (Sabine to NWE, Sabine to Asia via Panama and via Cape), sensitivity charts, freight built up from charter rate × voyage days, boil-off, M+1 delivery-month pricing |
| V3 | Historical arb analysis from the refresh log (and a scheduled logger if continuous history is needed) |

Anything listed under V2 or V3 is **out of scope for V1**.

## 3. V1 decisions (agreed)

| Topic | Decision |
|---|---|
| Contract months | Front month for HH, TTF and JKM. A note on screen says so. |
| TTF display | Both the raw EUR/MWh and the converted USD/MMBtu |
| Outcomes | Three: **Europe**, **Asia**, or **Cancel** (offtaker view, liquefaction fee treated as sunk) |
| Freight | One USD/MMBtu input per route |
| Asia route | The app picks the cheaper of Panama and Cape and shows both. A "Panama unavailable" toggle forces Cape. Suez is ignored. |
| Boil-off | Left out in V1 |
| Indifference threshold | If the Europe–Asia spread is below **$0.10/MMBtu**, the verdict is "Indifferent" |
| Refresh | Every **5 minutes** |
| Status light | Fresh means the quote is under 20 min old, delayed 20–60 min, stale over 60 min or a failed fetch |
| Log storage | CSV file `data/arb_log.csv`, one row per refresh |
| Deployment | Local in V1. The code avoids anything that would block a later move to Streamlit Community Cloud. |
| Python environment | `venv` + `requirements.txt` (Python 3.14 detected on the machine) |
| JKM source | Yahoo `JKM=F` gives only a **daily settlement** (CME JKM futures, settled on Platts), not live trades. It **prefills** the sidebar JKM box; the trader can type over it. If Yahoo has nothing, the box falls back to the $30.00 default. A truly live JKM needs a paid feed (Platts/ICE/CME), which would change only `market_data.py`. |

## 4. Data sources (V1)

All prices are in **USD/MMBtu** unless stated otherwise.

| Price | Source in V1 | Ticker / input | Native unit |
|---|---|---|---|
| Henry Hub (front month) | yfinance (delayed) | `NG=F` | USD/MMBtu |
| TTF (front month) | yfinance (delayed) | `TTF=F` | EUR/MWh |
| EURUSD | yfinance (delayed) | `EURUSD=X` | USD per EUR |
| JKM (front month) | yfinance daily settlement, used as an editable sidebar prefill | `JKM=F` | USD/MMBtu |
| Freight, Sabine to NWE | User input | sidebar | USD/MMBtu |
| Freight, Sabine to North Asia via Panama | User input | sidebar | USD/MMBtu |
| Freight, Sabine to North Asia via Cape | User input | sidebar | USD/MMBtu |
| Liquefaction fee | User input | sidebar | USD/MMBtu |
| Regas, Europe | User input | sidebar | USD/MMBtu |
| Regas, Asia | User input | sidebar | USD/MMBtu |

Every price carries a **source label** and a **timestamp**:
- yfinance prices: source `"yfinance (delayed)"`, timestamp = time of the last traded bar returned (not the time we fetched it).
- JKM settlement: source `"yfinance (daily settlement)"`, timestamp = the settlement date. It is always more than an hour old, so it always shows 🔴. That is honest: it is yesterday's price.
- User inputs: source `"User input"`, timestamp = when the value was last changed in the sidebar.
- The price panel shows two JKM rows: **JKM settlement** (what Yahoo says) and **JKM used** (what the calculation uses: the settlement, or the trader's own number).

## 5. Data module design (the swappable layer)

One module, `market_data.py`, is the **only** place in the code that knows where prices come from.

Every price it returns is a `Quote` with the same fields:

| Field | Example |
|---|---|
| `name` | `"TTF"` |
| `value` | `34.20` |
| `unit` | `"EUR/MWh"` |
| `source` | `"yfinance (delayed)"` |
| `timestamp` | `2026-11-14 13:45 UTC` |
| `status` | `"fresh"` / `"delayed"` / `"stale"` |

Rules:
- The rest of the app (calculations, screens, log) only ever sees `Quote` objects. It never imports yfinance.
- To switch to Bloomberg, ICE or Platts, a desk writes a new fetch function in `market_data.py` that returns the same `Quote` objects. Nothing else changes.
- If a fetch fails, the module returns the last known value with status `stale`, or an empty value with status `stale` if there is none. The app must never crash on a failed fetch.

## 6. Formulas

Notation: all values in USD/MMBtu.

**Unit conversion**
```
TTF_usd = TTF_eur_mwh × EURUSD ÷ 3.412        (1 MWh = 3.412 MMBtu)
```

**US FOB cost at Sabine Pass**
```
FOB_variable = 1.15 × HH                        (cost of the gas, the only cost still avoidable)
FOB_full     = 1.15 × HH + liquefaction_fee     (full cost including the sunk fee)
```

**Netbacks (value of the cargo at Sabine Pass)**
```
Netback_Europe       = TTF_usd − freight_NWE    − regas_Europe
Netback_Asia_Panama  = JKM     − freight_Panama − regas_Asia
Netback_Asia_Cape    = JKM     − freight_Cape   − regas_Asia
Netback_Asia         = max(Panama, Cape)    if Panama is available
                     = Cape                 if the "Panama unavailable" toggle is on
```

**Destination verdict**
```
Spread = Netback_Asia − Netback_Europe
If |Spread| < 0.10  → "Indifferent"
If Spread > 0       → "Asia wins by |Spread|"
If Spread < 0       → "Europe wins by |Spread|"
```

**Lift or cancel (offtaker view)**
```
Best_netback    = max(Netback_Europe, Netback_Asia)
Margin_variable = Best_netback − FOB_variable     (decides lift vs cancel)
Margin_full     = Best_netback − FOB_full         (shows whether the cargo makes money after the fee)

If Margin_variable < 0 → "CANCEL: netback does not cover 115% HH"
Else                   → "LIFT and send to <winner>"
```

## 7. Inputs ("Evaluate a cargo" pop-up)

All inputs are entered in a **pop-up** opened by the "🚢 Evaluate a cargo" button.
Gas prices are **prefilled from the market** and editable. Costs are prefilled with
the last values used (or the defaults below on first use).

| Input | Default | Min | Step |
|---|---|---|---|
| Henry Hub | Live market (yfinance) | 0 | 0.05 |
| TTF (EUR/MWh) | Live market (yfinance) | 0 | 0.50 |
| EURUSD | Live market (yfinance) | 0 | 0.0050 |
| JKM front month | Yahoo daily settlement (fallback 30.00) | 0 | 0.05 |
| Liquefaction fee | 2.50 | 0 | 0.05 |
| Freight, NWE | 0.90 | 0 | 0.05 |
| Freight, Asia via Panama | 1.60 | 0 | 0.05 |
| Freight, Asia via Cape | 2.10 | 0 | 0.05 |
| Regas, Europe | 0.45 | 0 | 0.05 |
| Regas, Asia | 0.35 | 0 | 0.05 |
| Panama unavailable (toggle) | off | | |
| Indifference threshold | 0.10 | 0 | 0.05 |

## 8. Screen layout (single page)

**Header**
- Title and note: "Front-month prices. yfinance data is delayed and indicative only."
- Two buttons: **🚢 Evaluate a cargo** (opens the pop-up) and **🔄 Refresh prices**.

**Pop-up "Evaluate a cargo"**
- Sections: gas prices (prefilled from market), freight (3 routes + "Panama unavailable"), fees (regas Europe, regas Asia, liquefaction), settings (indifference threshold).
- An **Evaluate** button shows the verdict banner **inside the pop-up** at once.
- A **Close** button returns to the page, which now shows that evaluation.

**Sidebar: read-only summary of the last evaluation** (no inputs)
- When it was evaluated, and the verdict.
- Prices used, each labelled "market" or "your input".
- Costs used: freight per route, Panama status, regas, liquefaction fee.
- Results: netbacks, chosen Asia route, FOB, margins.
- Before any evaluation, it shows the *indicative* case (market prices + default costs).

**1. Verdict banner** (top, large), for the last evaluation
- Example: `LIFT → ASIA, wins by $0.42/MMBtu (via Cape)`, or `CANCEL`, or `LIFT → INDIFFERENT`.
- Coloured: green when lifting, red when cancelling, grey when indifferent.
- Says when it was evaluated, or that it is indicative (no evaluation yet).

**2. Netback comparison**: two columns, Europe and Asia
- Each shows a small cost stack: hub price, minus freight, minus regas, equals netback.
- The Asia column shows Panama and Cape side by side and highlights the chosen route.

**3. FOB and margins**
- FOB variable, FOB full, margin over variable cost, margin over full cost.

**4. Live market panel** (refreshes every 5 minutes): one row per price
| Status | Price | Value | Unit | Source | Timestamp | Age |
|---|---|---|---|---|---|---|
- Status is shown as a light: 🟢 fresh, 🟡 delayed, 🔴 stale.
- TTF appears twice: EUR/MWh (raw) and USD/MMBtu (converted). JKM shows its daily settlement.

**5. Refresh log** (the market arb history)
- Each refresh logs the **live market** prices with the **latest cost assumptions** (from the last evaluation, or defaults).
- The last 20 rows of `data/arb_log.csv`.
- A button to download the full CSV.

## 9. Refresh and log

- Every 5 minutes the app fetches prices again, recalculates, and appends **one row** to `data/arb_log.csv`.
- The "Refresh now" button does the same thing on demand.
- Columns in each log row:
  `refresh_time_utc, hh, hh_ts, hh_status, ttf_eur_mwh, ttf_ts, ttf_status, eurusd, eurusd_ts, eurusd_status, ttf_usd, jkm, freight_nwe, freight_panama, freight_cape, regas_eu, regas_asia, liq_fee, panama_available, fob_variable, fob_full, netback_eu, netback_asia, asia_route, spread, verdict, margin_variable, margin_full`
- Known limitations (accepted for V1):
  - Streamlit only refreshes while the page is open in a browser, so history only builds while the app is running.
  - ~~Two open browser tabs would log twice.~~ Fixed in V1: before writing, the app checks the log's last row, so one price fetch = one row, whatever the number of tabs.
  - On Streamlit Cloud the CSV would be wiped on restart. That will be dealt with before any deployment.

## 10. File structure (V1)

```
lng_arbitrage/
├── app.py              # Streamlit screens only: pop-up, sidebar summary, display
├── market_data.py      # THE data module: fetches prices, returns Quote objects
├── arb_calc.py         # Pure calculations: formulas in section 6, no fetching, no display
├── arb_log.py          # Appends one row per refresh to the CSV and reads it back
├── config.py           # Defaults, tickers, thresholds, refresh interval, in one place
├── tests/
│   └── test_arb_calc.py  # Checks the formulas with hand-calculated examples
├── data/
│   └── arb_log.csv     # Created automatically (not committed to git)
├── requirements.txt
├── SPEC.md
└── CLAUDE.md
```

## 11. Done criteria for V1

1. `streamlit run app.py` opens the dashboard with no errors.
2. HH, TTF and EURUSD load from yfinance, each with a source, timestamp and status light.
3. Evaluating a cargo in the pop-up shows the verdict in the pop-up, then updates the page and the sidebar summary.
4. The verdict matches a hand calculation for at least one test case (covered by `tests/test_arb_calc.py`).
5. The "Panama unavailable" toggle switches the Asia route to Cape.
6. The app refreshes itself every 5 minutes, and each refresh adds one row to `data/arb_log.csv`.
7. If there is no internet, the app still opens, shows stale lights, and does not crash.
8. No file other than `market_data.py` imports yfinance.
