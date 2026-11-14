# 🚢 LNG Arbitrage Dashboard: Sabine Pass, Europe or Asia?

A Streamlit dashboard that answers one trading-desk question:

> **A US LNG cargo is loading at Sabine Pass. Should it go to Europe or to Asia right now, and by how much does the winner win?**

It also answers the offtaker's question behind it: **lift the cargo, or cancel it?**

![Dashboard](docs/dashboard.jpg)

---

## What it does

1. **Pulls market prices** (delayed): Henry Hub, TTF and EURUSD, plus the latest JKM settlement.
2. **Opens an "Evaluate a cargo" pop-up**. The gas prices are prefilled from the market and editable. The trader enters freight per route, regas and the liquefaction fee.
3. **Gives the verdict straight away**, e.g. `LIFT → ASIA, wins by $1.35/MMBtu (via Panama)`, `LIFT → EUROPE`, `INDIFFERENT` or `CANCEL`.
4. **Shows the full breakdown**: netbacks for Europe vs Asia, Panama vs Cape of Good Hope, FOB cost and margins.
5. **Records what was done**: the sidebar keeps a summary of the evaluation, with every price labelled "market" or "your input".
6. **Builds its own arb history**: every 5 minutes it re-prices the market and appends one row to a CSV log.

![Evaluate a cargo pop-up](docs/evaluate_popup.jpg)

---

## The economics

All values in **USD/MMBtu**.

| Step | Formula |
|---|---|
| TTF in dollars | `TTF (EUR/MWh) × EURUSD ÷ 3.412` (1 MWh = 3.412 MMBtu) |
| Cost of the cargo at Sabine Pass | `FOB variable = 115% × Henry Hub` (feed gas, the only avoidable cost)<br>`FOB full = FOB variable + liquefaction fee` |
| Netback Europe | `TTF − freight to NWE − regas Europe` |
| Netback Asia | `JKM − freight to North Asia − regas Asia`, via **Panama** or the **Cape**, whichever is cheaper (Panama can be switched off) |
| Destination | `spread = Netback Asia − Netback Europe`. Below the threshold ($0.10 by default), the verdict is **Indifferent** |
| Lift or cancel | The liquefaction fee is **sunk**, so the cargo is cancelled only if the best netback is below **115% HH**. A cargo can lose money after the fee and still be worth lifting. |

*Netback = what the cargo is worth back at Sabine Pass after shipping and regasification.*

---

## Built like a desk tool

- **One data module.** Every price enters through [`market_data.py`](market_data.py), as a standard `Quote` (value, unit, source, timestamp, status). No other file knows the vendor exists. Moving from yfinance to **Bloomberg, ICE or Platts** means changing that one file.
- **Every price carries its source, timestamp and a status light.** 🟢 fresh (under 20 min) · 🟡 delayed (20 to 60 min) · 🔴 stale (over 60 min, or the fetch failed). A price converted from two inputs (TTF in USD) takes the older timestamp and the worse light.
- **Never crashes on bad data.** If a feed is down, the app shows red lights and the last known value, and the trader can still type prices in by hand.
- **Clear separation:** formulas ([`arb_calc.py`](arb_calc.py)) · data ([`market_data.py`](market_data.py)) · history ([`arb_log.py`](arb_log.py)) · screens ([`app.py`](app.py)) · settings ([`config.py`](config.py)).
- **Self-built history.** One CSV row per price refresh: 28 columns covering prices, timestamps, statuses, costs, netbacks, route, verdict and margins. Exactly one row per fetch, even with several browser tabs open.
- **Tested.** 22 automated tests, including hand-calculated arb cases, the status-light rules, offline behaviour and the log.

---

## Data sources and limitations

| Data | Source | Note |
|---|---|---|
| Henry Hub (`NG=F`) | yfinance | Delayed, front month |
| TTF (`TTF=F`) | yfinance | Delayed, front month, EUR/MWh |
| EURUSD (`EURUSD=X`) | yfinance | Delayed |
| JKM (`JKM=F`) | yfinance | **Daily settlement only** (CME JKM futures, settled on Platts). Used as an editable prefill |
| Freight, regas, liquefaction fee | Trader input | No free market feed |

- yfinance data is **delayed and unofficial**: indicative only, **not for trading**.
- Front-month prices everywhere (V1). A real cargo loading in month M usually prices on M+1.
- The history only builds while the app is open in a browser.
- Boil-off and canal tolls (beyond freight) are not modelled yet.

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
├── app.py              # Screens: pop-up, sidebar summary, breakdown, live market, log
├── market_data.py      # THE data module: fetches prices, returns Quote objects
├── arb_calc.py         # Pure formulas: no fetching, no display
├── arb_log.py          # CSV history: one row per price refresh
├── config.py           # Tickers, default costs, thresholds, refresh interval
├── tests/              # 22 pytest tests
├── docs/               # Screenshots
├── SPEC.md             # Full specification (scope, formulas, screens)
└── requirements.txt    # Pinned library versions
```

---

## Roadmap

| Version | Scope | Status |
|---|---|---|
| **V1** | Calculator with market data, cargo evaluation pop-up, status lights, auto refresh and refresh log | ✅ Done |
| **V2** | Route map (Sabine Pass → NWE, → Asia via Panama / Cape), sensitivity charts, freight built from charter rates, boil-off, M+1 pricing, design overhaul | Planned |
| **V3** | Historical arb analysis from the refresh log | Planned |

---

## About

Built by **Jalil Bennani**, a former gas trader (TTF, biomethane), now studying for the Master in Financial Analysis at London Business School. It's a learning project in Python, built around a question I used to answer on the desk.

*Indicative tool for education and portfolio purposes. Not investment advice.*
