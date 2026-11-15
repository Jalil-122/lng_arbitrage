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

# Contract months (V3, M+1 pricing). Yahoo names each delivery month like
# "TTFF27.NYM": product "TTF" + month letter "F" (January) + year "27" + ".NYM".
CONTRACT_PREFIX_HENRY_HUB = "NG"
CONTRACT_PREFIX_TTF = "TTF"
CONTRACT_SUFFIX = ".NYM"
MONTH_CODES = "FGHJKMNQUVXZ"   # the standard futures letters, January (F) to December (Z)

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
# 3b. Detailed freight model (V2): defaults, all editable in the pop-up
# ---------------------------------------------------------------------------
# Freight = charter rate x ROUND-TRIP days (+ canal tolls) / cargo size.
# Boil-off = share of the cargo that evaporates on the LADEN (loaded) leg.

DEFAULT_CARGO_MMBTU = 3_500_000      # MMBtu loaded (a standard ~174,000 m3 carrier)
DEFAULT_CHARTER_RATE = 80_000        # USD per day for the ship
DEFAULT_BOIL_OFF_PCT_PER_DAY = 0.10  # % of the cargo lost per laden day

DEFAULT_DAYS_NWE = 14                # one-way days, Sabine Pass -> North-West Europe
DEFAULT_DAYS_PANAMA = 25             # one-way days, Sabine Pass -> North Asia via Panama
DEFAULT_DAYS_CAPE = 40               # one-way days, Sabine Pass -> North Asia via Cape

DEFAULT_PANAMA_TOLL = 500_000        # USD per Panama Canal transit (paid going AND coming back)


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


# ---------------------------------------------------------------------------
# 7. Route map (V2): coordinates as (latitude, longitude)
# ---------------------------------------------------------------------------
# Each route is a list of points the line passes through, so it follows a
# realistic sea lane instead of cutting across land.

PORT_SABINE_PASS = (29.73, -93.87)   # Cheniere's export terminal, Louisiana
PORT_GATE = (51.95, 4.05)            # Gate LNG terminal, Rotterdam (North-West Europe)
PORT_TOKYO_BAY = (35.20, 139.90)     # Tokyo Bay (North Asia, JKM)

ROUTE_POINTS = {
    "nwe": [
        PORT_SABINE_PASS, (25.5, -88.0), (24.3, -82.0), (27.0, -79.5),   # Gulf, Florida Strait
        (36.0, -60.0), (46.0, -25.0), (49.5, -6.0), (50.8, 1.0),         # Atlantic, English Channel
        PORT_GATE,
    ],
    "panama": [
        PORT_SABINE_PASS, (25.0, -89.0), (21.6, -85.9), (12.0, -80.5),   # Gulf, Yucatan Channel
        (9.35, -79.92), (8.85, -79.50),                                   # Panama Canal
        (6.0, -85.0), (15.0, -120.0), (25.0, -160.0), (32.0, 170.0),     # Pacific
        PORT_TOKYO_BAY,
    ],
    "cape": [
        PORT_SABINE_PASS, (25.5, -88.0), (24.3, -82.0), (27.0, -79.5),   # Gulf, Florida Strait
        (10.0, -40.0), (-10.0, -20.0), (-30.0, 0.0), (-35.0, 18.5),      # Atlantic, Cape of Good Hope
        (-30.0, 50.0), (-10.0, 85.0), (5.5, 95.0), (1.25, 103.8),        # Indian Ocean, Malacca
        (10.0, 110.0), (22.0, 118.0), (30.0, 128.0),                     # South China Sea
        PORT_TOKYO_BAY,
    ],
}

# Where each route's netback label is written on the map
ROUTE_LABEL_POINTS = {"nwe": (43.0, -42.0), "panama": (14.0, -118.0), "cape": (-27.0, 42.0)}


# ---------------------------------------------------------------------------
# 8. Sensitivity charts (V2)
# ---------------------------------------------------------------------------

SENSITIVITY_RANGE_PCT = 0.25   # charts show the price from -25% to +25% around today's level
SENSITIVITY_POINTS = 61        # how many points each line is drawn with
HEATMAP_POINTS = 41            # cells per axis in the decision heatmap (41 x 41)
