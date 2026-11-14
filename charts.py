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
