"""
charts.py: builds the map and charts (Plotly figures).

Display only: no formulas, no data fetching. Every number shown here was
already calculated in arb_calc.py; this file only decides how to draw it.

Plotly builds a "figure" from "traces": each trace is one thing drawn
(a line, some points, some text). app.py then shows the figure with
st.plotly_chart.
"""

import plotly.graph_objects as go

import config

# Colours (same palette as the light theme in .streamlit/config.toml)
ACCENT = "#1D9E75"        # green: the winning route, the "spread" lines
NAVY = "#0C2340"          # the chosen port and the destinations, dark text
DIM = "#9AA4B2"           # grey: the other routes
CLOSED = "#C5CBD5"        # light grey: a closed route (dashed)
OPEN_GREEN = "#1D9E75"    # a passage that is open
CLOSED_RED = "#E24B4A"    # a passage that is closed / avoided / disrupted
LAND = "#E6EAF1"
BORDERS = "#CDD3DD"
OCEAN = "#F1F5FA"         # a faint blue-grey, so the globe stands out from the white card
MONO = "JetBrains Mono, SF Mono, Menlo, Consolas, monospace"
SANS = "Inter, -apple-system, Helvetica Neue, Arial, sans-serif"


def highlighted_routes(result):
    """Which routes to highlight on the map, from the verdict.

    Europe wins      -> the best Europe route, e.g. {"nwe"}
    Asia wins        -> the best Asia route, e.g. {"asia_panama"}
    Indifferent      -> both
    CANCEL           -> none (the cargo doesn't sail)
    """
    if result["decision"] == "CANCEL":
        return set()
    if result["winner"] == "Europe":
        return {result["europe_route"]}
    if result["winner"] == "Asia":
        return {result["asia_route"]}
    return {result["europe_route"], result["asia_route"]}   # Indifferent


def halfway_point(points):
    """The point of a line closest to halfway along it (where its label goes).

    Measured roughly in map degrees, which is enough to place a label. A jump of
    more than 180 degrees of longitude means the line crosses the date line, so
    the short way round is used.
    """
    # The length of each piece of the line (Pythagoras on degrees)
    lengths = []
    for (lat1, lon1), (lat2, lon2) in zip(points[:-1], points[1:]):   # each point and the next
        lat_step = abs(lat2 - lat1)
        lon_step = abs(lon2 - lon1)
        if lon_step > 180:
            lon_step = 360 - lon_step
        lengths.append((lat_step ** 2 + lon_step ** 2) ** 0.5)

    # Walk along the line until half the total length is covered
    travelled = 0
    for index, length in enumerate(lengths):
        travelled += length
        if travelled >= sum(lengths) / 2:
            return points[index + 1]
    return points[-1]


def add_points(figure, points, names, hover, colour, size, symbol="circle", text_position=None):
    """Draw a group of points (ports or passages). With text_position, also write their names."""
    figure.add_trace(go.Scattergeo(
        lat=[point[0] for point in points],
        lon=[point[1] for point in points],
        mode="markers+text" if text_position else "markers",
        text=names,
        textposition=text_position,
        hovertext=hover,
        hoverinfo="text",
        marker={"size": size, "color": colour, "symbol": symbol,
                "line": {"width": 1, "color": "#FFFFFF"}},
        textfont={"color": NAVY, "size": 11, "family": SANS},
    ))


def route_map(result):
    """World map: the chosen port's routes, labelled with their netbacks, plus every
    port and passage.

    The winning route is thick green, the other open routes thin grey, and closed
    routes dashed. Passages are green when open, red when closed (hover for the name).
    """
    port_key = result["port"]
    port = config.LOAD_PORTS[port_key]
    winners = highlighted_routes(result)
    figure = go.Figure()

    # 1. The chosen port's routes. Non-winners first, so the winner is drawn on top.
    #    sorted(..., key=...) puts False (not a winner) before True (a winner).
    drawing_order = sorted(port["routes"], key=lambda route_key: route_key in winners)
    for route_key in drawing_order:
        route = port["routes"][route_key]
        is_open = result["route_open"][route_key]
        if route_key in winners:
            colour, width, dash = ACCENT, 4, "solid"
        elif not is_open:
            colour, width, dash = CLOSED, 2, "dash"
        else:
            colour, width, dash = DIM, 2, "solid"

        points = config.ROUTE_LINES[port_key][route_key]
        destination = "Europe" if route["destination"] == "nwe" else "Asia"
        name = f"{destination} {route['label']}"
        if is_open:
            label = f"{name}<br>${result['route_netbacks'][route_key]:.2f}"
        else:
            label = f"{name}<br>CLOSED"
        figure.add_trace(go.Scattergeo(
            lat=[point[0] for point in points],
            lon=[point[1] for point in points],
            mode="lines",
            line={"width": width, "color": colour, "dash": dash},
            hovertext=f"{label.replace('<br>', ' · ')} · {route['distance_nm']:,} nm",
            hoverinfo="text",
        ))

        # The label sits halfway along the route's line
        middle = halfway_point(points)
        figure.add_trace(go.Scattergeo(
            lat=[middle[0]], lon=[middle[1]], mode="text", text=[label],
            textfont={"color": colour if route_key in winners else "#5F6B7A",
                      "size": 11, "family": MONO},
            hoverinfo="skip",
        ))

    # 2. Passages: switchable ones coloured by status, the always-open ones in grey
    switchable = list(config.PASSAGES.values())
    passage_open = [result["passage_open"][key] for key in config.PASSAGES]
    add_points(figure,
               [passage["point"] for passage in switchable],
               names=None,
               hover=[f"{passage['name']}: {'open' if is_open else 'CLOSED'}"
                      for passage, is_open in zip(switchable, passage_open)],
               colour=[OPEN_GREEN if is_open else CLOSED_RED for is_open in passage_open],
               size=11, symbol="diamond")
    add_points(figure,
               list(config.OTHER_PASSAGE_POINTS.values()),
               names=None,
               hover=[f"{name}: always open" for name in config.OTHER_PASSAGE_POINTS],
               colour=DIM, size=8, symbol="diamond")

    # 3. The other load ports (small grey), then the destinations and the chosen port (amber)
    others = [key for key in config.LOAD_PORTS if key != port_key]
    add_points(figure,
               [config.LOAD_PORTS[key]["point"] for key in others],
               names=None,
               hover=[config.LOAD_PORTS[key]["name"] for key in others],
               colour=DIM, size=6)
    add_points(figure,
               [port["point"], config.PORT_GATE, config.PORT_TOKYO_BAY],
               names=[port["name"], "Gate", "Tokyo Bay"],
               hover=[f"{port['name']} (load port)", "Gate, Rotterdam (TTF)", "Tokyo Bay (JKM)"],
               colour=NAVY, size=9,
               text_position=["top center", "top center", "top center"])

    # The map itself: dark land, no frame, cropped from Cape Horn to Hammerfest
    figure.update_geos(
        projection_type="natural earth",
        showland=True, landcolor=LAND,
        showocean=True, oceancolor=OCEAN,
        showcountries=True, countrycolor=BORDERS,
        coastlinecolor=BORDERS, showlakes=False, showframe=False,
        lataxis_range=[-60, 75],
        bgcolor="rgba(0,0,0,0)",
    )
    figure.update_layout(
        height=460,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        hoverlabel={"font": {"family": MONO}},
    )
    return figure


# ---------------------------------------------------------------------------
# Breakeven chart (V2): how the spread moves with one price
# ---------------------------------------------------------------------------

GRID = "#EEF1F6"
TEXT = "#1B2A3D"
GREEN = "#0F6E56"
RED = "#A32D2D"
BAND = "#9AA4B2"          # the grey "indifferent" band and the zero line


def chart_range(current, breakeven, pct=config.SENSITIVITY_RANGE_PCT):
    """Pick the price range to draw: +/- pct around today, widened to show the breakeven."""
    low = current * (1 - pct)
    high = current * (1 + pct)
    margin = current * 0.05
    return min(low, breakeven - margin), max(high, breakeven + margin)


def breakeven_chart(prices, spreads, current_price, current_spread, breakeven,
                    threshold, price_label, unit_prefix="$"):
    """Line chart: spread (Asia - Europe) as one price moves, everything else fixed.

    Marks the breakeven (spread = 0), the +/- threshold "indifferent" band,
    and where we are now.
    """
    figure = go.Figure()

    # Shaded band: inside it, the verdict is "Indifferent"
    figure.add_hrect(y0=-threshold, y1=threshold, fillcolor=BAND, opacity=0.18,
                     line_width=0)
    figure.add_hline(y=0, line={"color": BAND, "width": 1})

    # The spread line
    figure.add_trace(go.Scatter(
        x=prices, y=spreads, mode="lines",
        line={"color": ACCENT, "width": 2.5},
        hovertemplate=f"{price_label} %{{x:.2f}}<br>Spread %{{y:+.2f}} $/MMBtu<extra></extra>",
    ))

    # Breakeven: dashed vertical line with its value
    figure.add_vline(x=breakeven, line={"color": TEXT, "width": 1, "dash": "dash"})
    figure.add_annotation(x=breakeven, y=1, yref="paper", yanchor="bottom", showarrow=False,
                          text=f"Breakeven {unit_prefix}{breakeven:.2f}",
                          font={"color": TEXT, "family": MONO, "size": 12})

    # Today: a dot on the line
    figure.add_trace(go.Scatter(
        x=[current_price], y=[current_spread], mode="markers+text",
        marker={"size": 10, "color": ACCENT, "line": {"width": 2, "color": "#FFFFFF"}},
        text=[f"Now {unit_prefix}{current_price:.2f}"], textposition="middle right",
        textfont={"color": ACCENT, "family": MONO, "size": 12},
        hoverinfo="skip",
    ))

    # Which side wins: labels in the corners
    figure.add_annotation(x=0.01, y=0.97, xref="paper", yref="paper", showarrow=False,
                          xanchor="left", text="ASIA WINS ↑",
                          font={"color": GREEN, "family": MONO, "size": 11})
    figure.add_annotation(x=0.01, y=0.03, xref="paper", yref="paper", showarrow=False,
                          xanchor="left", text="EUROPE WINS ↓",
                          font={"color": RED, "family": MONO, "size": 11})

    figure.update_layout(
        height=320,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        font={"color": TEXT, "family": SANS, "size": 11},
        xaxis={"title": price_label, "gridcolor": GRID, "zeroline": False},
        yaxis={"title": "Spread Asia − Europe ($/MMBtu)", "gridcolor": GRID, "zeroline": False},
    )
    return figure


# ---------------------------------------------------------------------------
# Decision heatmap (V2): which way the cargo goes, for every JKM x Asia freight
# ---------------------------------------------------------------------------

# One colour per outcome (same order as arb_calc.OUTCOMES)
OUTCOME_COLOURS = {
    "Europe": "#3D7DD8",        # blue
    "Asia": "#E8A33D",          # amber-orange
    "Indifferent": "#C5CBD5",   # light slate
    "Cancel": "#E24B4A",        # red
}
OUTCOME_ORDER = ["Europe", "Asia", "Indifferent", "Cancel"]


def heatmap_freight_range(current_freight, points=config.HEATMAP_POINTS):
    """Asia freight levels to try: from half today's level to double (at least +$2)."""
    low = current_freight * 0.5
    high = max(current_freight * 2, current_freight + 2)
    return [low + (high - low) * i / (points - 1) for i in range(points)]


def decision_heatmap(jkm_values, freight_values, outcomes, spreads,
                     current_jkm, current_freight, route_name):
    """Grid of coloured cells: the outcome for each JKM (x) and Asia freight (y).

    A heatmap needs numbers, so each outcome becomes a code (Europe=0, Asia=1,
    Indifferent=2, Cancel=3) and the colour scale maps each code to its colour.
    """
    codes = [[OUTCOME_ORDER.index(cell) for cell in row] for row in outcomes]

    # A "stepped" colour scale: each code gets one flat colour (no gradients)
    steps = []
    for code, name in enumerate(OUTCOME_ORDER):
        start, end = code / len(OUTCOME_ORDER), (code + 1) / len(OUTCOME_ORDER)
        steps += [[start, OUTCOME_COLOURS[name]], [end, OUTCOME_COLOURS[name]]]

    # What appears when hovering a cell: its outcome and spread
    hover_text = [[f"{outcomes[r][c]} · spread {spreads[r][c]:+.2f}"
                   for c in range(len(jkm_values))] for r in range(len(freight_values))]

    figure = go.Figure(go.Heatmap(
        x=jkm_values, y=freight_values, z=codes,
        zmin=-0.5, zmax=len(OUTCOME_ORDER) - 0.5,   # centres each code in its colour step
        colorscale=steps, showscale=False,
        text=hover_text,
        hovertemplate="JKM %{x:.2f} · Asia freight %{y:.2f}<br>%{text}<extra></extra>",
    ))

    # Today's evaluation: a white cross
    figure.add_trace(go.Scatter(
        x=[current_jkm], y=[current_freight], mode="markers+text",
        marker={"symbol": "x", "size": 14, "color": NAVY, "line": {"width": 1, "color": "#FFFFFF"}},
        text=["Now"], textposition="top right",
        textfont={"color": NAVY, "family": MONO, "size": 12},
        hoverinfo="skip", showlegend=False,
    ))

    # Legend: one invisible point per outcome, just to show the colour keys
    for name in OUTCOME_ORDER:
        figure.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers", name=name,
            marker={"size": 12, "symbol": "square", "color": OUTCOME_COLOURS[name]},
        ))

    figure.update_layout(
        height=420,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT, "family": SANS, "size": 11},
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
        xaxis={"title": "JKM ($/MMBtu)", "showgrid": False},
        yaxis={"title": f"Asia freight {route_name} ($/MMBtu)", "showgrid": False},
    )
    return figure


# ---------------------------------------------------------------------------
# History (V3): the arb month by month
# ---------------------------------------------------------------------------

def arb_over_time_chart(table, threshold):
    """Bar chart: one bar per month, height = spread (Asia - Europe), colour = outcome.

    table: the monthly table from arb_calc.historical_arb.
    The shaded band around zero is the "Indifferent" zone (+/- threshold).
    """
    figure = go.Figure()
    figure.add_hrect(y0=-threshold, y1=threshold, fillcolor=BAND, opacity=0.18, line_width=0)
    figure.add_hline(y=0, line={"color": BAND, "width": 1})

    # One bar trace per outcome, so each gets its colour and its legend entry
    for name in OUTCOME_ORDER:
        months = table[table["outcome"] == name]
        if months.empty:
            continue
        figure.add_trace(go.Bar(
            x=months["month"], y=months["spread"], name=name,
            marker={"color": OUTCOME_COLOURS[name]},
            # customdata: extra columns the hover text can use (%{customdata[0]} = 1st column)
            customdata=months[["netback_europe", "netback_asia", "asia_route"]],
            hovertemplate=("%{x|%b %Y} · " + name + "<br>Spread %{y:+.2f}"
                           "<br>Netback Europe %{customdata[0]:.2f}"
                           "<br>Netback Asia %{customdata[1]:.2f} (%{customdata[2]})"
                           "<extra></extra>"),
        ))

    figure.update_layout(
        height=380,
        bargap=0.15,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT, "family": SANS, "size": 11},
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
        xaxis={"gridcolor": GRID, "zeroline": False},
        yaxis={"title": "Spread Asia − Europe ($/MMBtu)", "gridcolor": GRID, "zeroline": False},
    )
    return figure


def history_layout(figure, y_title, height=320):
    """The common look of the History charts (saves repeating it twice)."""
    figure.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT, "family": SANS, "size": 11},
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
        xaxis={"gridcolor": GRID, "zeroline": False},
        yaxis={"title": y_title, "gridcolor": GRID, "zeroline": False},
    )
    return figure


def win_rate_by_year_chart(by_year):
    """Stacked bars: for each year, the % of months won by each outcome (adds up to 100%).

    by_year: the table from arb_calc.win_rates_by_year.
    """
    figure = go.Figure()
    for name in OUTCOME_ORDER:
        figure.add_trace(go.Bar(
            x=by_year["year"], y=by_year[name], name=name,
            marker={"color": OUTCOME_COLOURS[name]},
            hovertemplate="%{x} · " + name + " %{y:.0f}% of months<extra></extra>",
        ))
    # "stack": the outcomes sit on top of each other. Plotly then lists a stacked
    # legend backwards; traceorder="normal" keeps it Europe, Asia, Indifferent, Cancel.
    figure.update_layout(barmode="stack", legend_traceorder="normal")
    figure.update_xaxes(dtick=1)            # one label per year
    return history_layout(figure, "% of months")


def seasonality_chart(season):
    """Bars: the average spread for each calendar month (amber = Asia, blue = Europe).

    season: the table from arb_calc.seasonality.
    """
    colours = [OUTCOME_COLOURS["Asia"] if spread > 0 else OUTCOME_COLOURS["Europe"]
               for spread in season["average_spread"]]
    figure = go.Figure(go.Bar(
        x=season["month_name"], y=season["average_spread"],
        marker={"color": colours},
        customdata=season["months"],
        hovertemplate="%{x} · average spread %{y:+.2f}<br>based on %{customdata} months<extra></extra>",
    ))
    figure.add_hline(y=0, line={"color": BAND, "width": 1})
    return history_layout(figure, "Average spread Asia − Europe ($/MMBtu)")
