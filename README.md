# 🚢 LNG Arbitrage Dashboard: Sabine Pass, Europe or Asia?

A Streamlit dashboard that answers one trading-desk question:

> **A US LNG cargo is loading at Sabine Pass. Should it go to Europe or to Asia right now, and by how much does the winner win?**

It also answers the offtaker's question behind it: **lift the cargo, or cancel it?**

![Dashboard: verdict and route map](docs/dashboard.jpg)

---

## What it does

1. **Pulls market prices** (delayed): Henry Hub, TTF and EURUSD, plus the latest JKM settlement.
2. **Opens an "Evaluate a cargo" pop-up**. The gas prices are prefilled from the market and editable. Freight is entered in one of two modes:
   - **Simple:** USD/MMBtu per route.
   - **Detailed:** a charter model (charter rate × round-trip days, Panama tolls, cargo size, boil-off), with a freight build-up table.
3. **Gives the verdict straight away**, e.g. `LIFT → ASIA, wins by $0.90/MMBtu (via Panama)`, `LIFT → EUROPE`, `INDIFFERENT` or `CANCEL`.
4. **Draws the routes** on a world map: Sabine Pass → North-West Europe, → North Asia via Panama, → North Asia via the Cape of Good Hope. Each route is labelled with its netback and the winner is highlighted.
5. **Shows the full breakdown**: netbacks (hub price − regas − boil-off loss − freight), FOB cost and margins.
6. **Stress-tests the decision**:
   - **breakeven charts** give the exact JKM and TTF levels where the cargo flips destination;
   - a **decision map** colours every JKM × freight combination by outcome.
7. **Records what was done**: the sidebar keeps a summary of the evaluation, with every price labelled "market" or "your input".
8. **Builds its own arb history**: every 5 minutes it re-prices the market and appends one row to a CSV log.

![Evaluate a cargo: detailed freight model](docs/evaluate_popup.jpg)

![Sensitivity: breakevens and decision map](docs/sensitivity.jpg)

---

## The economics

All values in **USD/MMBtu**, per MMBtu **loaded**.

| Step | Formula |
|---|---|
| TTF in dollars | `TTF (EUR/MWh) × EURUSD ÷ 3.412` (1 MWh = 3.412 MMBtu) |
| Cost of the cargo at Sabine Pass | `FOB variable = 115% × Henry Hub` (feed gas, the only avoidable cost)<br>`FOB full = FOB variable + liquefaction fee` |
| Freight (Detailed mode) | `(charter rate × round-trip days + canal tolls) ÷ cargo size`. The ship is paid out **and** back; Panama is transited twice |
| Boil-off (Detailed mode) | `boil-off rate per day × laden days` (e.g. 0.10%/day × 14 days = 1.4%) |
| Netback | `(hub price − regas) × (1 − boil-off) − freight` |
| Asia route | **Panama** or the **Cape**, whichever gives the higher netback (Panama can be switched off) |
| Destination | `spread = Netback Asia − Netback Europe`. Below the threshold ($0.10 by default), the verdict is **Indifferent** |
| Lift or cancel | The liquefaction fee is **sunk**, so the cargo is cancelled only if the best netback is below **115% HH**. A cargo can lose money after the fee and still be worth lifting |
| Breakeven JKM | `regas Asia + (netback Europe + freight) ÷ (1 − boil-off)`, using the cheapest open Asia route |

*Netback = what the cargo is worth back at Sabine Pass after regasification, boil-off and shipping.*

**Why boil-off matters:** a longer voyage loses more cargo. In one test case, the simple model says *Asia by $0.12* but the detailed model says *Europe by $0.11*: the 25-day Asia voyage burns 2.5% of the cargo against 1.4% to Europe.

---

## Built like a desk tool

- **One data module.** Every price enters through [`market_data.py`](market_data.py), as a standard `Quote` (value, unit, source, timestamp, status). No other file knows the vendor exists. Moving from yfinance to **Bloomberg, ICE or Platts** means changing that one file.
- **Every price carries its source, timestamp and a status light.** 🟢 fresh (under 20 min) · 🟡 delayed (20 to 60 min) · 🔴 stale (over 60 min, or the fetch failed). A price converted from two inputs (TTF in USD) takes the older timestamp and the worse light.
- **Never crashes on bad data.** If a feed is down, the app shows red lights, and the trader can still evaluate a cargo by typing prices. The map and charts still work.
- **Clear separation:**
  - formulas: [`arb_calc.py`](arb_calc.py)
  - data: [`market_data.py`](market_data.py)
  - charts: [`charts.py`](charts.py), which draws only and does no maths
  - history: [`arb_log.py`](arb_log.py)
  - screens: [`app.py`](app.py)
  - settings: [`config.py`](config.py)
- **Self-built history.** One CSV row per price refresh: 28 columns covering prices, timestamps, statuses, costs, netbacks, route, verdict and margins. Exactly one row per fetch, even with several browser tabs open.
- **Tested.** 42 automated tests, including:
  - hand-calculated arb cases;
  - the freight and boil-off worked example;
  - breakevens, checked to give a spread of exactly zero;
  - decision-map cells, including a route switch from Panama to the Cape;
  - the status-light rules, offline behaviour and the log.

---

## Data sources and limitations

| Data | Source | Note |
|---|---|---|
| Henry Hub (`NG=F`) | yfinance | Delayed, front month |
| TTF (`TTF=F`) | yfinance | Delayed, front month, EUR/MWh |
| EURUSD (`EURUSD=X`) | yfinance | Delayed |
| JKM (`JKM=F`) | yfinance | **Daily settlement only** (CME JKM futures, settled on Platts). Used as an editable prefill |
| Freight, voyage days, charter rate, regas, fees | Trader input | No free market feed. Detailed-mode defaults are editable placeholders |

- yfinance data is **delayed and unofficial**: indicative only, **not for trading**.
- Front-month prices everywhere. A real cargo loading in month M usually prices on M+1.
- The history only builds while the app is open in a browser.
- Boil-off is applied on the laden leg only. Bunker fuel, port costs and the Suez route are not modelled.
- Map routes are simplified sea lanes, not exact shipping tracks.

---

## Run it

Requires Python 3.12+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The dashboard opens at `http://localhost:8501`.

Run the tests:

```bash
pytest
```

---

## Project structure

```
lng_arbitrage/
├── app.py                 # Screens: pop-up, sidebar summary, map, breakdown, charts, live market, log
├── market_data.py         # THE data module: fetches prices, returns Quote objects
├── arb_calc.py            # Pure formulas: netbacks, freight & boil-off, breakevens, decision grid
├── charts.py              # Plotly route map, breakeven charts, decision heatmap (display only)
├── arb_log.py             # CSV history: one row per price refresh
├── config.py              # Tickers, default costs, voyage defaults, map coordinates, thresholds
├── .streamlit/config.toml # Dark trading-terminal theme
├── tests/                 # 42 pytest tests
├── docs/                  # Screenshots
├── SPEC.md                # Full specification (V1 and V2: scope, formulas, screens, done criteria)
└── requirements.txt       # Pinned library versions
```

---

## Roadmap

| Version | Scope | Status |
|---|---|---|
| **V1** | Calculator with market data, cargo evaluation pop-up, status lights, auto refresh and refresh log | ✅ Done |
| **V2** | Freight & boil-off model, dark terminal design, route map, breakeven charts, decision heatmap | ✅ Done |
| **V3** | Historical arb analysis from the refresh log, M+1 delivery-month pricing | Planned |

---

## About

Built by **Jalil Bennani**, a former gas trader (TTF, biomethane), now studying for the Master in Financial Analysis at London Business School. It's a learning project in Python, built around a question I used to answer on the desk.

*Indicative tool for education and portfolio purposes. Not investment advice.*
