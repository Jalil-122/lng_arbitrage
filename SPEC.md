# LNG Arbitrage Dashboard: Specification

## 1. Purpose

A Streamlit dashboard that answers one desk question:

> **Should a US LNG cargo loading at Sabine Pass go to Europe or Asia right now, and by how much does the winner win?**

It also says whether the cargo should be lifted at all, or cancelled.

The tool is built like a trading desk tool. Every price passes through **one data module**, so a desk could swap yfinance for Bloomberg, ICE or Platts by changing only that module.

## 2. Roadmap

| Version | Scope |
|---|---|
| **V1** ✅ done | Calculator with live delayed prices (HH, TTF, EURUSD), JKM daily settlement as an editable prefill, "Evaluate a cargo" pop-up, auto refresh, a status light for each price, and a refresh log |
| **V2** ✅ done (section 12) | Freight & boil-off model, dark trading-terminal design, route map, sensitivity charts (breakeven lines, decision heatmap) |
| V3 | Historical arb analysis from the refresh log (and a scheduled logger if continuous history is needed). M+1 delivery-month pricing. |

Sections 1–11 describe V1. Section 12 describes V2 and overrides V1 where they differ.

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

---

## 12. V2 specification

### 12.1 V2 decisions (agreed)

| Topic | Decision |
|---|---|
| Scope | Freight & boil-off model, design overhaul, route map, sensitivity charts |
| Build order | 1. Freight & boil-off model → 2. Design → 3. Route map → 4. Charts |
| Freight input | **Two modes with a switch** in the pop-up: **Simple** (type $/MMBtu per route, as in V1, no boil-off) and **Detailed** (built from the charter model below) |
| Voyage cost basis | **Round trip** (laden + ballast): the charterer pays for the ship to come back |
| Boil-off | Applied on the **laden leg only**, in Detailed mode. Ballast boil-off (heel) is ignored |
| Design | **Dark trading terminal**: dark background, compact numbers, green/red accents |
| Charts | **Breakeven lines** and **decision heatmap**. (Tornado chart not in V2.) |
| New library | **Plotly** (interactive charts and map), added to `requirements.txt` |
| Not in V2 | M+1 delivery-month pricing (moved to V3), Suez route, fuel/bunker costs beyond boil-off |

### 12.2 Detailed freight model: inputs and defaults (all editable)

| Input | Default | Unit |
|---|---|---|
| Cargo size (loaded) | 3,500,000 | MMBtu |
| Charter rate | 80,000 | USD/day |
| Boil-off rate | 0.10 | % of cargo per laden day |
| One-way days, Sabine Pass → NWE | 14 | days |
| One-way days, Sabine Pass → North Asia via Panama | 25 | days |
| One-way days, Sabine Pass → North Asia via Cape | 40 | days |
| Panama Canal toll | 500,000 | USD per transit |

### 12.3 Formulas (Detailed mode)

All per **loaded** MMBtu.

```
round_trip_days   = 2 × one_way_days
charter_cost      = charter_rate × round_trip_days                      (USD)
canal_cost        = panama_toll × 2   (Panama route only: laden + ballast transits)
freight           = (charter_cost + canal_cost) ÷ cargo_size            (USD/MMBtu)

boil_off_fraction = boil_off_rate_per_day × one_way_days                (laden leg only)

netback           = (hub_price − regas) × (1 − boil_off_fraction) − freight
```

Why: boil-off means fewer MMBtu arrive than were loaded, so the cargo sells less gas
(and pays regas on less gas) while the freight bill is the same.

In **Simple** mode, `boil_off_fraction = 0`, so the netback formula is exactly V1's.

Worked example with the defaults:

| Route | Round trip | Charter | Toll | Freight | Boil-off |
|---|---|---|---|---|---|
| NWE | 28 d | $2.24m | – | $0.640 | 1.4% |
| Asia via Panama | 50 d | $4.00m | $1.00m | $1.429 | 2.5% |
| Asia via Cape | 80 d | $6.40m | – | $1.829 | 4.0% |

The Panama vs Cape choice, the verdict and lift/cancel are unchanged (section 6),
using these netbacks.

### 12.4 Screens (changes from V1)

**Pop-up "Evaluate a cargo"**
- Section 2 "Freight" gets a **Simple / Detailed** switch.
- Detailed shows: cargo size, charter rate, boil-off rate, one-way days per route, Panama toll.
- After Evaluate, a small **freight build-up table** shows per route: round-trip days, charter cost, toll, freight $/MMBtu, boil-off %.

**Sidebar summary**: shows the freight mode, and in Detailed mode the voyage inputs and the resulting freight and boil-off per route.

**Netback tables**: add a "Boil-off loss" line when boil-off is above zero.

**Design (dark trading terminal)**
- Streamlit dark theme set in `.streamlit/config.toml`, with a terminal accent colour.
- Compact, aligned numbers; green = favourable, red = unfavourable; consistent spacing and section headers.
- The page reads top to bottom: verdict → route map → netbacks → margins → sensitivity → live market → log.

**Route map**
- World map (Plotly) with three routes from Sabine Pass: to NWE (Gate terminal, Rotterdam), to Tokyo Bay via the Panama Canal, and to Tokyo Bay via the Cape of Good Hope (passing Singapore/Malacca).
- Each route is labelled with its netback. The **winning route is highlighted** (thicker, accent colour); the others are dimmed. A closed Panama is drawn dashed and grey.

**Sensitivity charts** (computed from the current evaluation)
- **Breakeven lines**: the Asia − Europe spread as JKM moves (other inputs fixed), with the **breakeven JKM** (spread = 0) and the ± threshold band marked. The same chart for TTF.
- **Decision heatmap**: JKM on one axis, Asia freight (best route, $/MMBtu) on the other; each cell coloured by the outcome: Europe / Asia / Indifferent / Cancel. The current evaluation is marked on the grid.

**Log**: unchanged columns. In Detailed mode, the logged freight is the calculated $/MMBtu, and the logged netbacks include boil-off.

### 12.5 File changes (V2)

```
arb_calc.py      + voyage freight and boil-off functions; netback gains an optional boil-off
config.py        + voyage defaults, map coordinates, chart ranges
app.py           + freight mode switch, freight table, map, charts, new layout
charts.py        NEW: builds the Plotly map and charts (display only, no formulas)
.streamlit/config.toml   NEW: dark theme
requirements.txt + plotly
tests/           + tests for the freight/boil-off maths and the breakeven calculation
```

### 12.6 Done criteria for V2

1. In Detailed mode, freight and boil-off match the worked example in 12.3 (covered by tests).
2. In Simple mode, every V1 result is unchanged (all V1 tests still pass).
3. The pop-up switches between Simple and Detailed, and the freight build-up table shows after Evaluate.
4. The app uses the dark terminal theme, and the page follows the order in 12.4.
5. The route map shows the three routes, labelled with netbacks, the winner highlighted, and Panama dashed when closed.
6. The breakeven chart marks the breakeven JKM, which matches a hand calculation (covered by a test).
7. The heatmap colours each cell by outcome and marks the current evaluation.
8. Everything still works offline (typed prices) and `market_data.py` is still the only file importing yfinance.
