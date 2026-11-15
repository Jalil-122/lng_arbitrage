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

# Monthly history (V3). FRED = the St. Louis Fed's free data site; no account needed.
# Both series are IMF monthly averages, already in USD/MMBtu.
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
FRED_SERIES_EUROPE = "PNGASEUUSDM"      # Europe natural gas (IMF, TTF-based)
FRED_SERIES_HENRY_HUB = "PNGASUSUSDM"   # US natural gas, Henry Hub (IMF)
SOURCE_FRED = "FRED (IMF, monthly)"
SOURCE_YFINANCE_MONTHLY = "yfinance (monthly average of daily settlements)"
HISTORY_CACHE_SECONDS = 24 * 60 * 60    # keep history 24 hours: it only changes once a month
HISTORY_TIMEOUT_SECONDS = 20            # give up on a download after 20 seconds

SOURCE_YFINANCE = "yfinance (delayed)"   # label shown next to every yfinance price
SOURCE_YFINANCE_DAILY = "yfinance (CME futures, daily settlement)"   # label for once-a-day prices (JKM)
# JKM=F is the CME JKM FUTURES front month (settled on Platts), not the Platts spot
# assessment itself. The two can differ by $1-2 (e.g. 12 Nov 2026: futures ~31.35,
# Reuters spot reference ~29.67), so the app labels it as futures.
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
DEFAULT_CHARTER_RATE = 52_000        # USD per day for the ship. Source: one-year time-charter
                                     # rate ~$51,800/day, late Oct 2026 (IndexBox). Spot varies by
                                     # route: ~$25,400 US Gulf->Europe, ~$58,900 US Gulf->Japan,
                                     # ~$32,800 Australia->Japan. It spiked to $160k-300k in the
                                     # March 2026 Hormuz crisis. Update it from a broker report.
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
# 7. Route map (V2, all ports since V4): coordinates as (latitude, longitude)
# ---------------------------------------------------------------------------
# The two destination terminals. (The load ports' points are in section 9.)
PORT_GATE = (51.95, 4.05)            # Gate LNG terminal, Rotterdam (North-West Europe, TTF)
PORT_TOKYO_BAY = (35.20, 139.90)     # Tokyo Bay (North Asia, JKM)

# The line drawn for each route: a list of points the ship passes, so the line
# follows real sea lanes instead of cutting across land. Generated once with
# searoute (the same tool as the distances, section 9), then simplified to a few
# points per route. Display only: the maths uses distance_nm, not these points.
# Note: Kitimat sits at the end of a fjord; its lines add ~60 nm to reach the
# shipping lane, so its distances in section 9 are slightly understated (~0.7%).
ROUTE_LINES = {
    "sabine_pass": {
        "nwe": [(29.7, -93.9), (24.2, -81.8), (25.1, -80.0), (27.4, -79.3), (27.7, -77.1), (38.1, -62.0), (45.3, -45.0), (48.9, -28.8), (49.9, -2.9), (52.0, 4.1)],
        "asia_panama": [(29.7, -93.9), (21.6, -85.9), (8.8, -79.5), (7.0, -80.2), (7.4, -82.8), (18, -105.5), (22.3, -111.0), (28.0, -116.1), (35.3, -129.4), (42.1, -145.4), (45.9, -158.7), (50, -180), (40, 150), (35.2, 139.9)],
        "asia_suez": [(29.7, -93.9), (24.2, -81.8), (34.6, -51.5), (36.2, -38.9), (36.0, -5.8), (37.5, 11), (31.7, 32.1), (28.4, 33.2), (12.4, 43.7), (13.3, 53.6), (5.8, 80.1), (6.5, 90), (5.8, 98.1), (1.1, 103.6), (19, 120), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
        "asia_cape": [(29.7, -93.9), (24.3, -82.7), (19.8, -68.9), (13.6, -61.6), (2.9, -42.9), (-4.7, -34.9), (-24.7, -4.4), (-33.6, 14.1), (-35, 18), (-35, 22), (-33.1, 42.9), (-29.3, 59.9), (-23.3, 76.1), (-13.1, 95.1), (-5.2, 106.8), (3.7, 109.8), (7.5, 109.9), (19, 120), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
    },
    "corpus_christi": {
        "nwe": [(27.9, -97.2), (24.2, -81.8), (25.1, -80.0), (27.4, -79.3), (27.7, -77.1), (38.1, -62.0), (45.3, -45.0), (48.9, -28.8), (49.9, -2.9), (52.0, 4.1)],
        "asia_panama": [(27.9, -97.2), (21.6, -85.9), (8.8, -79.5), (7.4, -79.7), (7.4, -82.8), (18, -105.5), (22.3, -111.0), (28.0, -116.1), (35.3, -129.4), (42.1, -145.4), (45.9, -158.7), (50, -180), (40, 150), (35.2, 139.9)],
        "asia_suez": [(27.9, -97.2), (24.2, -81.8), (34.6, -51.5), (36.2, -38.9), (36.0, -5.8), (37.5, 11), (31.7, 32.1), (28.4, 33.2), (12.4, 43.7), (13.3, 53.6), (5.8, 80.1), (6.5, 90), (5.8, 98.1), (1.1, 103.6), (19, 120), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
        "asia_cape": [(27.9, -97.2), (21.9, -86.1), (12, -61.9), (-27.1, 0.0), (-35, 18), (-35, 22), (-33.1, 42.9), (-29.3, 59.9), (-23.3, 76.1), (-13.1, 95.1), (-5.2, 106.8), (3.7, 109.8), (7.5, 109.9), (19, 120), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
    },
    "cove_point": {
        "nwe": [(38.4, -76.4), (36.8, -75.8), (42.3, -64.2), (49.2, -38.1), (50.4, -25.6), (49.9, -2.9), (52.0, 4.1)],
        "asia_panama": [(38.4, -76.4), (35.8, -75.1), (20, -73.9), (9.8, -80), (7.4, -79.7), (6.9, -81.4), (18, -105.5), (22.3, -111.0), (28.0, -116.1), (35.3, -129.4), (42.1, -145.4), (45.9, -158.7), (50, -180), (40, 150), (35.2, 139.9)],
        "asia_suez": [(38.4, -76.4), (36.8, -75.8), (40.3, -69.5), (42.3, -57.3), (42.9, -44.7), (41.2, -25.9), (36.0, -5.8), (37.5, 11), (31.7, 32.1), (28.4, 33.2), (12.4, 43.7), (13.3, 53.6), (5.8, 80.1), (6.5, 90), (5.8, 98.1), (1.1, 103.6), (19, 120), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
        "asia_cape": [(38.4, -76.4), (35.5, -74.6), (30.6, -61.3), (-8, -14.3), (-20.0, -2.6), (-30, 10), (-35, 18), (-33.5, 40.0), (-30.0, 57.4), (-24.9, 72.4), (-16.1, 90.0), (-5.2, 106.8), (3.7, 109.8), (7.5, 109.9), (19, 120), (23.1, 122.1), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
    },
    "point_fortin": {
        "nwe": [(10.2, -61.7), (11.5, -61.4), (20, -50), (37.8, -32.4), (43.2, -21.3), (52.0, 4.1)],
        "asia_panama": [(10.2, -61.7), (12.5, -66.0), (13, -70), (9.8, -80), (7.4, -79.7), (6.9, -81.4), (18, -105.5), (22.3, -111.0), (28.0, -116.1), (37.8, -134.5), (44.5, -152.4), (50, -180), (40, 150), (35.2, 139.9)],
        "asia_suez": [(10.2, -61.7), (11.5, -61.4), (20, -50), (25.6, -44.6), (28.3, -38.7), (32.6, -24.5), (34.3, -15.4), (37.2, 3.1), (37.5, 11), (31.7, 32.1), (28.4, 33.2), (12.4, 43.7), (13.3, 53.6), (5.8, 80.1), (6.5, 90), (5.8, 98.1), (1.1, 103.6), (19, 120), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
        "asia_cape": [(10.2, -61.7), (11, -61), (-5.2, -33.8), (-23.2, -7.0), (-31.9, 10.0), (-35, 18), (-33.5, 40.0), (-30.0, 57.4), (-24.9, 72.4), (-16.1, 90.0), (-6.3, 105.4), (-5.2, 106.8), (3.7, 109.8), (7.5, 109.9), (19, 120), (23.1, 122.1), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
    },
    "bonny": {
        "nwe": [(4.4, 7.2), (5, 2.5), (3.5, -7.5), (5.5, -11.5), (11, -17), (15, -18), (21, -18), (43.4, -10.1), (48.7, -5.5), (52.0, 4.1)],
        "asia_cape": [(4.4, 7.2), (1.0, 8.6), (-1.0, 8.0), (-6.0, 11.5), (-19, 11), (-22.9, 13.8), (-26.9, 14.5), (-35, 18), (-33.9, 36.4), (-31.3, 52.5), (-27.8, 64.7), (-22.5, 77.6), (-16.1, 90.0), (-6.3, 105.4), (-5.2, 106.8), (3.7, 109.8), (7.5, 109.9), (19, 120), (23.1, 122.1), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
    },
    "hammerfest": {
        "nwe": [(70.7, 23.6), (70, 17), (68, 12), (63.0, 4.2), (58.8, 4.8), (52.4, 3.0), (52.0, 4.1)],
        "asia_suez": [(70.7, 23.6), (70, 17), (67.8, 9.7), (58.7, -5.2), (54.4, -10.5), (36.8, -9.2), (36.0, -5.8), (37.5, 11), (31.7, 32.1), (28.4, 33.2), (23.6, 37), (13.7, 42.5), (12, 45), (13.3, 53.6), (5.8, 80.1), (6.5, 90), (5.8, 98.1), (1.1, 103.6), (19, 120), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
        "asia_panama": [(70.7, 23.6), (70, 17), (70.8, -8.7), (68.9, -22.8), (65.0, -36.9), (62.9, -39.0), (60, -40), (55.1, -45.6), (46.8, -52.7), (45, -55), (38.9, -69.4), (20, -73.9), (9.8, -80), (7.0, -80.2), (7.4, -82.8), (18, -105.5), (22.3, -111.0), (28.0, -116.1), (35.3, -129.4), (42.1, -145.4), (45.9, -158.7), (50, -180), (40, 150), (35.2, 139.9)],
        "asia_cape": [(70.7, 23.6), (70, 17), (67.8, 9.7), (58.7, -5.2), (54.4, -10.5), (43.1, -10.2), (21, -18), (11, -17), (-0.0, -10), (-35, 18), (-33.5, 40.0), (-30.0, 57.4), (-24.9, 72.4), (-16.1, 90.0), (-5.2, 106.8), (3.7, 109.8), (7.5, 109.9), (19, 120), (23.1, 122.1), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
    },
    "ras_laffan": {
        "nwe_suez": [(25.9, 51.6), (26.5, 56.5), (22.7, 60.4), (17.4, 56.9), (12, 45), (13.7, 42.5), (23.6, 37), (28.4, 33.2), (31.7, 32.1), (37.5, 11), (36.0, -5.8), (36.8, -9.2), (43, -9.5), (47.3, -6.7), (48.7, -5.5), (52.0, 4.1)],
        "nwe_cape": [(25.9, 51.6), (26.5, 56.5), (22.7, 60.4), (11.6, 52.3), (-15, 41.7), (-30, 32), (-33.5, 28.5), (-34.5, 26), (-35, 18), (-0.0, -10), (11, -17), (15, -18), (21, -18), (43.4, -10.1), (48.7, -5.5), (52.0, 4.1)],
        "asia": [(25.9, 51.6), (26.4, 56.8), (20.1, 64.5), (14.7, 68.8), (5.8, 80.1), (6.5, 90), (5.8, 98.1), (1.1, 103.6), (19, 120), (24.6, 123.4), (26.0, 127.8), (35.2, 139.9)],
    },
    "gladstone": {
        "nwe_suez": [(-23.8, 151.2), (-23.6, 151.8), (-20.8, 150.2), (-18.7, 147.1), (-10.4, 143.0), (-8.2, 126.3), (-9.1, 115.6), (-7.3, 105.2), (10, 60), (11.6, 52.3), (12.9, 50.9), (12.4, 43.7), (28.4, 33.2), (31.7, 32.1), (37.5, 11), (36.0, -5.8), (36.8, -9.2), (43, -9.5), (47.3, -6.7), (48.7, -5.5), (52.0, 4.1)],
        "nwe_panama": [(-23.8, 151.2), (-24.6, 153.6), (-20, 160), (-23, 167.7), (-20, -180), (-21, -175.5), (-20, -170), (-20, -160), (-10.0, -124.9), (7.0, -80.2), (9.8, -80), (18.5, -67.9), (30.1, -55.3), (40, -40), (46.1, -24.7), (48.3, -16.0), (50.3, -0.8), (52.0, 4.0)],
        "nwe_cape": [(-23.8, 151.2), (-24.6, 153.6), (-28.7, 153.8), (-37.7, 150.1), (-39.3, 146.4), (-38.7, 141), (-50, 130), (-50, 30), (-40, 20), (-35, 18), (-0.0, -10), (11, -17), (21, -18), (43.4, -10.1), (48.7, -5.5), (52.0, 4.1)],
        "asia": [(-23.8, 151.2), (-18.6, 153.6), (-10.4, 154.7), (10, 150), (35.2, 139.9)],
    },
    "kitimat": {
        "nwe_panama": [(54.0, -128.7), (54.3, -131.2), (52.2, -129.4), (44.7, -130.0), (37.7, -122.9), (34.4, -120.9), (33.2, -117.4), (27.5, -115.2), (24.7, -112.5), (18.0, -103.4), (16.5, -99.9), (15.6, -99.9), (6.9, -81.4), (7.4, -79.7), (9.8, -80), (18.5, -68.0), (30.1, -55.3), (40, -40), (46.1, -24.7), (48.3, -16.0), (50.3, -0.8), (52.0, 4.1)],
        "nwe_horn": [(54.0, -128.7), (54.3, -131.2), (52.2, -129.4), (44.7, -130.0), (37.7, -122.9), (34.4, -120.9), (30, -120), (17.2, -112.9), (-33.2, -92.9), (-52.6, -75.1), (-54.0, -71.0), (-52.8, -70.5), (-52.4, -68), (-45.8, -59.0), (-38.7, -51.9), (-31.2, -46.2), (-13, -36.2), (14.0, -26.1), (33.1, -17.2), (48.7, -5.5), (52.0, 4.1)],
        "asia": [(54.0, -128.7), (54.6, -134.0), (57.5, -136.7), (59.3, -140.4), (60.1, -146.8), (58.7, -150.8), (57.0, -151.9), (54.1, -164.3), (51.1, -168.1), (50.3, -179.5), (40, 150), (35.2, 139.9)],
    },
}


# ---------------------------------------------------------------------------
# 8. Sensitivity charts (V2)
# ---------------------------------------------------------------------------

SENSITIVITY_RANGE_PCT = 0.25   # charts show the price from -25% to +25% around today's level
SENSITIVITY_POINTS = 61        # how many points each line is drawn with
HEATMAP_POINTS = 41            # cells per axis in the decision heatmap (41 x 41)


# ---------------------------------------------------------------------------
# 9. Load ports, routes and passages (V4)
# ---------------------------------------------------------------------------
# DISTANCES (nautical miles, one way) were computed with "searoute" 1.6, a free
# sea-routing tool built on Eurostat's MARNET shipping-lane network, in Nov 2026.
# Check against published figures for US Gulf -> Japan (Riviera Maritime citing
# Sea-Distances.org, and S&P Global): Panama 9,306 vs 9,209 nm, Suez 14,624 vs
# 14,521 nm, Cape 15,825 vs 15,689 nm, i.e. within about 1%.
#
# Each port has a list of ROUTES. A route goes to one destination ("nwe" =
# North-West Europe, priced on TTF; "asia" = North Asia, priced on JKM) and
# lists the PASSAGES it uses. If any of those passages is closed, the route
# can't be used, and the app picks the best route that is still open.

DEFAULT_SHIP_SPEED_KNOTS = 16   # laden speed of an LNG carrier; 1 knot = 1 nautical mile per hour
                                # one-way days = distance / (speed x 24 hours)

DEFAULT_SUEZ_TOLL = 450_000     # USD per Suez transit. EDITABLE PLACEHOLDER: the Suez Canal
                                # Authority publishes no simple LNG figure, and its surcharges
                                # changed in July 2026 (circular 19/2026). Check before use.
# DEFAULT_PANAMA_TOLL (section 3b) stays 500,000: the 2024 Panama tariff gives about
# 620,000 laden (300,000 fixed + 1.85 USD/m3 x 174,000 m3) and less in ballast,
# before any slot-auction premium.

# The passages that can be switched open/closed in the pop-up.
# Passages not listed here (Cape of Good Hope, Cape Horn, Gibraltar, Malacca)
# are always open.
PASSAGES = {
    "panama": {
        "name": "Panama Canal",
        "default_open": True,    # open but congested: slots are auctioned in 2026
        "point": (9.10, -79.70),
    },
    "suez": {
        "name": "Suez Canal + Red Sea",
        "default_open": False,   # mostly avoided since the 2023-24 Houthi attacks
        "point": (30.0, 32.55),
    },
    "hormuz": {
        "name": "Strait of Hormuz",
        "default_open": False,   # largely blocked since the March 2026 Iran war
        "point": (26.55, 56.25),
    },
}

# Other passages, only drawn on the map (never closed in the app).
OTHER_PASSAGE_POINTS = {
    "Cape of Good Hope": (-34.8, 19.5),
    "Cape Horn": (-56.5, -67.3),
    "Strait of Malacca": (2.5, 101.3),
}

DEFAULT_LOAD_PORT = "sabine_pass"

# "us_hh_linked" = True for US ports: the cargo costs 115% Henry Hub + a
# liquefaction fee, and the buyer can cancel it (lift/cancel verdict).
# Non-US cargoes mostly sell on oil-linked long-term contracts with no cancel
# option, so they only get the destination verdict (Europe or Asia).
LOAD_PORTS = {
    "sabine_pass": {
        "name": "Sabine Pass", "country": "USA (Louisiana)", "us_hh_linked": True,
        "point": (29.73, -93.87),
        "routes": {
            "nwe":         {"destination": "nwe",  "label": "direct",        "distance_nm": 4979,  "passages": []},
            "asia_panama": {"destination": "asia", "label": "via Panama",    "distance_nm": 9306,  "passages": ["panama"]},
            "asia_suez":   {"destination": "asia", "label": "via Suez",      "distance_nm": 14624, "passages": ["suez"]},
            "asia_cape":   {"destination": "asia", "label": "via the Cape",  "distance_nm": 15825, "passages": []},
        },
    },
    "corpus_christi": {
        "name": "Corpus Christi", "country": "USA (Texas)", "us_hh_linked": True,
        "point": (27.88, -97.25),
        "routes": {
            "nwe":         {"destination": "nwe",  "label": "direct",        "distance_nm": 5110,  "passages": []},
            "asia_panama": {"destination": "asia", "label": "via Panama",    "distance_nm": 9377,  "passages": ["panama"]},
            "asia_suez":   {"destination": "asia", "label": "via Suez",      "distance_nm": 14755, "passages": ["suez"]},
            "asia_cape":   {"destination": "asia", "label": "via the Cape",  "distance_nm": 15936, "passages": []},
        },
    },
    "cove_point": {
        "name": "Cove Point", "country": "USA (Maryland)", "us_hh_linked": True,
        "point": (38.40, -76.39),
        "routes": {
            "nwe":         {"destination": "nwe",  "label": "direct",        "distance_nm": 3559,  "passages": []},
            "asia_panama": {"destination": "asia", "label": "via Panama",    "distance_nm": 9705,  "passages": ["panama"]},
            "asia_suez":   {"destination": "asia", "label": "via Suez",      "distance_nm": 13355, "passages": ["suez"]},
            "asia_cape":   {"destination": "asia", "label": "via the Cape",  "distance_nm": 15276, "passages": []},
        },
    },
    "point_fortin": {
        "name": "Point Fortin", "country": "Trinidad and Tobago", "us_hh_linked": False,
        "point": (10.18, -61.70),
        "routes": {
            "nwe":         {"destination": "nwe",  "label": "direct",        "distance_nm": 4097,  "passages": []},
            "asia_panama": {"destination": "asia", "label": "via Panama",    "distance_nm": 9023,  "passages": ["panama"]},
            "asia_suez":   {"destination": "asia", "label": "via Suez",      "distance_nm": 13391, "passages": ["suez"]},
            "asia_cape":   {"destination": "asia", "label": "via the Cape",  "distance_nm": 13721, "passages": []},
        },
    },
    "bonny": {
        "name": "Bonny Island", "country": "Nigeria", "us_hh_linked": False,
        "point": (4.40, 7.15),
        "routes": {
            "nwe":         {"destination": "nwe",  "label": "direct",        "distance_nm": 4450,  "passages": []},
            "asia_cape":   {"destination": "asia", "label": "via the Cape",  "distance_nm": 10912, "passages": []},
        },
    },
    "hammerfest": {
        "name": "Hammerfest", "country": "Norway", "us_hh_linked": False,
        "point": (70.69, 23.60),
        "routes": {
            "nwe":         {"destination": "nwe",  "label": "direct",        "distance_nm": 1376,  "passages": []},
            "asia_suez":   {"destination": "asia", "label": "via Suez",      "distance_nm": 12552, "passages": ["suez"]},
            "asia_panama": {"destination": "asia", "label": "via Panama",    "distance_nm": 13238, "passages": ["panama"]},
            "asia_cape":   {"destination": "asia", "label": "via the Cape",  "distance_nm": 15832, "passages": []},
        },
    },
    "ras_laffan": {
        "name": "Ras Laffan", "country": "Qatar", "us_hh_linked": False,
        "point": (25.92, 51.58),
        # Every Ras Laffan route crosses Hormuz: there is no way around it.
        # The app does not remove these routes when Hormuz is disrupted; it warns instead.
        "routes": {
            "nwe_suez":    {"destination": "nwe",  "label": "via Suez",      "distance_nm": 6421,  "passages": ["hormuz", "suez"]},
            "nwe_cape":    {"destination": "nwe",  "label": "via the Cape",  "distance_nm": 11204, "passages": ["hormuz"]},
            "asia":        {"destination": "asia", "label": "via Malacca",   "distance_nm": 6587,  "passages": ["hormuz"]},
        },
    },
    "gladstone": {
        "name": "Gladstone", "country": "Australia (Queensland)", "us_hh_linked": False,
        "point": (-23.77, 151.23),
        "routes": {
            "nwe_suez":    {"destination": "nwe",  "label": "via Suez",      "distance_nm": 11778, "passages": ["suez"]},
            "nwe_panama":  {"destination": "nwe",  "label": "via Panama",    "distance_nm": 12885, "passages": ["panama"]},
            "nwe_cape":    {"destination": "nwe",  "label": "via the Cape",  "distance_nm": 13387, "passages": []},
            "asia":        {"destination": "asia", "label": "direct",        "distance_nm": 3771,  "passages": []},
        },
    },
    "kitimat": {
        "name": "Kitimat (LNG Canada)", "country": "Canada (British Columbia)", "us_hh_linked": False,
        "point": (54.00, -128.70),
        "routes": {
            "nwe_panama":  {"destination": "nwe",  "label": "via Panama",    "distance_nm": 9342,  "passages": ["panama"]},
            "nwe_horn":    {"destination": "nwe",  "label": "via Cape Horn", "distance_nm": 14804, "passages": []},
            "asia":        {"destination": "asia", "label": "direct",        "distance_nm": 4150,  "passages": []},
        },
    },
}
