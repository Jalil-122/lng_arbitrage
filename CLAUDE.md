# CLAUDE.md: LNG Arbitrage Dashboard

## Project context

- **Owner:** a former gas trader (TTF, biomethane), now on the LBS Master in Financial Analysis and **learning Python**. They know the market well; Python is new to them.
- **Goal:** a CV project. A Streamlit dashboard that answers "should a US LNG cargo from Sabine Pass go to Europe or Asia right now, and by how much?"
- **Full scope and formulas:** see [SPEC.md](SPEC.md). SPEC.md is the source of truth. If code and spec disagree, ask before changing either.
- **Versions:** V1 (calculator, live data, "Evaluate a cargo" pop-up) is **done**. V2 (freight & boil-off model, dark terminal design, route map, sensitivity charts; SPEC.md section 12) is **done**: all criteria in SPEC.md 12.6 checked. V3 (historical arb analysis from free monthly history: FRED + Yahoo, and M+1 delivery pricing; SPEC.md section 13) is **done**: all criteria in SPEC.md 13.7 checked. **V4** (nine real load ports, real sea distances, Suez/Panama/Cape/Hormuz passages; SPEC.md section 14) is **done**: all criteria in SPEC.md 14.7 checked. **Published** on Streamlit Community Cloud: https://lng-arbitrage.streamlit.app/ (repo is public; every push to `main` redeploys it). Design: parchment cards (SPEC.md 14.8).
- **GitHub:** https://github.com/Jalil-122/lng_arbitrage. After committing, `git push` uploads (the owner's token is saved in the macOS Keychain; never handle tokens).

## Architecture rules (desk-tool design)

- **One data module.** `market_data.py` is the only file that knows where prices come from. It returns `Quote` objects (name, value, unit, source, timestamp, status). No other file imports yfinance or any data vendor.
- **Swappable vendor.** Moving to Bloomberg, ICE or Platts must mean editing `market_data.py` only.
- **Separation:** `arb_calc.py` holds the formulas (no fetching, no display), `app.py` holds the screens (no formulas), `arb_log.py` writes and reads the CSV log, and `config.py` holds the defaults and thresholds.
- **Every price shown carries its source and timestamp.** Never display a number without them.
- **Never crash on bad data.** A failed fetch shows a stale light; it never causes an error page.
- Units: everything is in USD/MMBtu inside the calculations. Convert TTF at the edge (EUR/MWh × EURUSD ÷ 3.412).

## How to work with me (rules)

1. **Keep code simple and commented. I'm a beginner.**
   - Use plain Python: functions, dicts, simple dataclasses. Avoid clever one-liners, decorators beyond what Streamlit needs, metaclasses and deep class hierarchies.
   - Give every function a short docstring saying what it does in plain words.
   - Comment the *why*, and put the trading meaning next to the formulas (e.g. `# netback = what the cargo is worth back at Sabine Pass`).
   - Use clear variable names (`netback_europe`, not `nb_eu`).
2. **Explain each change in plain words before making it.** Before editing any file, say what you are about to change, why, and which file. Keep it short, with no jargon you haven't explained.
3. **Build one small step at a time.** One step means one small, testable change. After each step, tell me how to run or check it, then stop and wait for me before moving on.
4. Don't add libraries, files or features that aren't in SPEC.md without asking first.
5. When you teach a new Python or Streamlit idea for the first time, add a one- or two-line explanation.

## V3 build order (done)

1. M+1 contract months: month-code logic + contract quotes in `market_data.py`, with tests (SPEC 13.4).
2. Pop-up "Delivery pricing" switch (Front month / M+1) + TTF M+1 row in the live market panel.
3. History data: FRED (`PNGASEUUSDM`, `PNGASUSUSDM`) + Yahoo JKM monthly average in `market_data.py`, cached 24h, tested offline with fake data.
4. Historical arb, win rates, seasonality in `arb_calc.py`, with hand-calculated tests.
5. Tabs + History tab: period selector and arb-over-time chart.
6. Win-rate and seasonality charts, sources note, CSV download.
7. Check every item in SPEC.md 13.7, refresh README and screenshots.

## V2 build order (done)

1. Freight & boil-off model: `arb_calc.py` functions + tests (worked example in SPEC 12.3), Simple mode unchanged.
2. Pop-up: Simple / Detailed freight switch, freight build-up table, sidebar summary update.
3. Design: dark terminal theme (`.streamlit/config.toml`) and page layout order (SPEC 12.4).
4. Add Plotly; `charts.py` with the route map; place it under the verdict.
5. Breakeven lines (JKM and TTF), with a breakeven test.
6. Decision heatmap.
7. Check every item in SPEC.md 12.6, refresh the README screenshots.

## V1 build order (done)

1. Set up `venv`, `requirements.txt` (streamlit, yfinance, pandas, pytest) and `.gitignore` (venv, `__pycache__`, `data/arb_log.csv`).
2. `config.py`: defaults and thresholds from SPEC.md.
3. `arb_calc.py` + `tests/test_arb_calc.py`: the formulas, tested by hand calculation.
4. `market_data.py`: the `Quote` object and the yfinance fetch with status logic, tried from the terminal first.
5. `app.py`: sidebar inputs and the verdict banner.
6. `app.py`: price panel with source, timestamp and status lights.
7. `app.py`: netback comparison and margins.
8. `arb_log.py` + auto refresh every 5 minutes + log table and download.
9. Check every item in SPEC.md section 11.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate   # create/activate the environment
pip install -r requirements.txt                      # install libraries
streamlit run app.py                                 # run the dashboard
pytest                                               # run the tests
```

## Notes

- Python 3.14 is installed. If a library has no build for 3.14, fall back to Python 3.12 in the venv.
- yfinance data is delayed and unofficial. Label it as such everywhere.
- Commit after each working step, with a short message in plain words.
