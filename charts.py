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

# Colours (same palette as the dark terminal theme in .streamlit/config.toml)
ACCENT = "#FFB000"        # amber: the winning route
DIM = "#5B6676"           # grey: the other routes
CLOSED = "#3A4250"        # dark grey: a closed route
LAND = "#1B222C"
BORDERS = "#2A323D"
MONO = "SF Mono, Menlo, Consolas, monospace"

ROUTE_NAMES = {"nwe": "NWE", "panama": "Asia via Panama", "cape": "Asia via Cape"}


def highlighted_routes(result):
    """Which routes to highlight on the map, from the verdict.

    Europe wins      -> {"nwe"}
    Asia wins        -> {"panama"} or {"cape"} (the route chosen)
    Indifferent      -> both: NWE and the best Asia route
    CANCEL           -> none (the cargo doesn't sail)
    """
    if result["decision"] == "CANCEL":
        return set()
    asia_route = result["asia_route"].lower()   # "Panama" -> "panama"
    if result["winner"] == "Europe":
        return {"nwe"}
    if result["winner"] == "Asia":
        return {asia_route}
    return {"nwe", asia_route}   # Indifferent


def route_netbacks(result):
    """The netback of each route, by route key."""
    return {
        "nwe": result["netback_europe"],
        "panama": result["netback_asia_panama"],
        "cape": result["netback_asia_cape"],
    }


def route_map(result, inputs):
    """World map: the three routes from Sabine Pass, labelled with their netbacks.

    The winning route is thick amber, the others thin grey,
    and a closed Panama Canal is drawn dashed.
    """
    winners = highlighted_routes(result)
    netbacks = route_netbacks(result)
    figure = go.Figure()

    # Draw the non-winning routes first, so the winner is drawn on top
    drawing_order = sorted(ROUTE_NAMES, key=lambda route: route in winners)

    for route in drawing_order:
        closed = route == "panama" and not inputs["panama_available"]
        if route in winners:
            colour, width, dash = ACCENT, 4, "solid"
        elif closed:
            colour, width, dash = CLOSED, 2, "dash"
        else:
            colour, width, dash = DIM, 2, "solid"

        points = config.ROUTE_POINTS[route]
        figure.add_trace(go.Scattergeo(
            lat=[point[0] for point in points],
            lon=[point[1] for point in points],
            mode="lines",
            line={"width": width, "color": colour, "dash": dash},
            hoverinfo="skip",
        ))

        # The label: route name and netback (or CLOSED)
        name = ROUTE_NAMES[route]
        label = f"{name}<br>CLOSED" if closed else f"{name}<br>${netbacks[route]:.2f}"
        label_lat, label_lon = config.ROUTE_LABEL_POINTS[route]
        figure.add_trace(go.Scattergeo(
            lat=[label_lat], lon=[label_lon], mode="text", text=[label],
            textfont={"color": colour if route in winners else "#9AA4B2",
                      "size": 13, "family": MONO},
            hoverinfo="skip",
        ))

    # The three ports
    ports = [("Sabine Pass", config.PORT_SABINE_PASS, "bottom center"),
             ("Gate", config.PORT_GATE, "top center"),
             ("Tokyo Bay", config.PORT_TOKYO_BAY, "top center")]
    figure.add_trace(go.Scattergeo(
        lat=[port[1][0] for port in ports],
        lon=[port[1][1] for port in ports],
        mode="markers+text",
        text=[port[0] for port in ports],
        textposition=[port[2] for port in ports],
        marker={"size": 8, "color": ACCENT, "line": {"width": 1, "color": "#0B0E13"}},
        textfont={"color": "#D9DEE5", "size": 11, "family": MONO},
        hoverinfo="skip",
    ))

    # The map itself: dark land, no frame, cropped to the useful latitudes
    figure.update_geos(
        projection_type="natural earth",
        showland=True, landcolor=LAND,
        showocean=True, oceancolor="#0B0E13",
        showcountries=True, countrycolor=BORDERS,
        coastlinecolor=BORDERS, showlakes=False, showframe=False,
        lataxis_range=[-50, 70],
        bgcolor="rgba(0,0,0,0)",
    )
    figure.update_layout(
        height=420,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return figure


# ---------------------------------------------------------------------------
# Breakeven chart (V2): how the spread moves with one price
# ---------------------------------------------------------------------------

GRID = "#1F2630"
TEXT = "#D9DEE5"
GREEN = "#2EBD85"
RED = "#F6465D"


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
    figure.add_hrect(y0=-threshold, y1=threshold, fillcolor="#5B6676", opacity=0.18,
                     line_width=0)
    figure.add_hline(y=0, line={"color": "#5B6676", "width": 1})

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
        marker={"size": 10, "color": ACCENT, "line": {"width": 2, "color": "#0B0E13"}},
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
        font={"color": TEXT, "family": MONO, "size": 11},
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
    "Indifferent": "#3A4250",   # slate
    "Cancel": "#F6465D",        # red
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
        marker={"symbol": "x", "size": 14, "color": "white", "line": {"width": 1, "color": "#0B0E13"}},
        text=["Now"], textposition="top right",
        textfont={"color": "white", "family": MONO, "size": 12},
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
        font={"color": TEXT, "family": MONO, "size": 11},
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0},
        xaxis={"title": "JKM ($/MMBtu)", "showgrid": False},
        yaxis={"title": f"Asia freight via {route_name} ($/MMBtu)", "showgrid": False},
    )
    return figure
