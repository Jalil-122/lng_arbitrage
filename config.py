"""
config.py: the project's settings sheet.

Every fixed number the app uses lives here, in one place.
To change a default (e.g. the liquefaction fee), change it here only.

Convention: names in CAPITALS are fixed settings. The program reads them
but never changes them while it runs.

All prices are in USD/MMBtu unless the name says otherwise.
"""

# ---------------------------------------------------------------------------
# 1. Market data tickers (yfinance)
# ---------------------------------------------------------------------------
# These are Yahoo Finance codes. Only market_data.py will use them.
# If a desk switches to Bloomberg/ICE/Platts, these are replaced there.

TICKER_HENRY_HUB = "NG=F"     # NYMEX Henry Hub natural gas, front month, USD/MMBtu
TICKER_TTF = "TTF=F"          # ICE Dutch TTF gas, front month, EUR/MWh
TICKER_EURUSD = "EURUSD=X"    # Euro to US dollar exchange rate (USD per 1 EUR)
TICKER_JKM = "JKM=F"          # CME JKM LNG futures (settled on Platts JKM), USD/MMBtu.
                              # Yahoo only has ONE price per day (the settlement), not live trades.

SOURCE_YFINANCE = "yfinance (delayed)"   # label shown next to every yfinance price
SOURCE_YFINANCE_DAILY = "yfinance (daily settlement)"   # label for once-a-day prices (JKM)
SOURCE_USER = "User input"               # label shown next to every sidebar input


# ---------------------------------------------------------------------------
# 2. Fixed formula constants
# ---------------------------------------------------------------------------

MMBTU_PER_MWH = 3.412    # 1 MWh = 3.412 MMBtu, used to convert TTF from EUR/MWh
HH_MULTIPLIER = 1.15     # US LNG contracts pay 115% of Henry Hub for the feed gas


# ---------------------------------------------------------------------------
# 3. Default sidebar inputs (placeholders, all editable in the app)
# ---------------------------------------------------------------------------

DEFAULT_JKM = 30.00                # JKM fallback: used only if Yahoo has no JKM settlement.
                                   # Normally the sidebar starts at Yahoo's daily settlement.
DEFAULT_LIQUEFACTION_FEE = 2.50    # Sabine Pass tolling fee (sunk for the offtaker)

DEFAULT_FREIGHT_NWE = 0.90         # Sabine Pass -> North-West Europe
DEFAULT_FREIGHT_PANAMA = 1.60      # Sabine Pass -> North Asia via the Panama Canal
DEFAULT_FREIGHT_CAPE = 2.10        # Sabine Pass -> North Asia via the Cape of Good Hope

DEFAULT_REGAS_EUROPE = 0.45        # Regasification fee at a European terminal (e.g. Gate)
DEFAULT_REGAS_ASIA = 0.35          # Regasification fee at a Japanese/Korean terminal

DEFAULT_PANAMA_AVAILABLE = True    # False = canal blocked, so the Asia route must go via Cape

INPUT_STEP = 0.05                  # how much each +/- click changes a sidebar input


# ---------------------------------------------------------------------------
# 4. Decision threshold
# ---------------------------------------------------------------------------

# If Europe and Asia netbacks are closer than this, the verdict is "Indifferent".
DEFAULT_INDIFFERENCE_THRESHOLD = 0.10


# ---------------------------------------------------------------------------
# 5. Refresh and status light
# ---------------------------------------------------------------------------

REFRESH_SECONDS = 5 * 60     # the app fetches prices again every 5 minutes

# Age of a price quote (in minutes) decides its status light:
#   under 20 min       -> fresh   (green)
#   20 to 60 min       -> delayed (yellow)
#   over 60 min / fail -> stale   (red)
FRESH_MAX_MINUTES = 20
DELAYED_MAX_MINUTES = 60


# ---------------------------------------------------------------------------
# 6. Refresh log
# ---------------------------------------------------------------------------

LOG_FILE_PATH = "data/arb_log.csv"   # one row added here at every refresh
LOG_ROWS_SHOWN = 20                  # how many recent rows the dashboard displays
