"""
Tests for charts.py: the map highlights the right route.

(We don't test how the map LOOKS; that's checked by eye in the browser.
We test the decision of what to highlight, which is easy to get wrong.)
"""

import arb_calc
import charts
import config

SUEZ_AVOIDED = {"panama": True, "suez": False, "hormuz": False}


def port_result(port_key, passage_open=SUEZ_AVOIDED, jkm=12.00, henry_hub=3.00, threshold=0.10):
    """A real result from arb_calc for a port, with 1.00 $/MMBtu freight on every route."""
    routes = config.LOAD_PORTS[port_key]["routes"]
    return arb_calc.calculate_port_arb(
        port_key=port_key, ttf_eur_mwh=35.00, eurusd=1.10, jkm=jkm,
        route_freight={route_key: 1.00 for route_key in routes},
        regas_europe=0.45, regas_asia=0.35, passage_open=passage_open,
        henry_hub=henry_hub, liquefaction_fee=2.50, threshold=threshold,
    )


def test_asia_win_highlights_the_chosen_route():
    # Europe 11.2837 - 0.45 - 1.00 = 9.83 ; Asia 12 - 0.35 - 1.00 = 10.65 -> Asia, via Panama
    # (Panama is the first open Asia route with the best netback; Suez is closed)
    result = port_result("sabine_pass")
    assert result["winner"] == "Asia"
    assert charts.highlighted_routes(result) == {result["asia_route"]}


def test_europe_win_highlights_the_europe_route():
    result = port_result("sabine_pass", jkm=10.00)
    assert result["winner"] == "Europe"
    assert charts.highlighted_routes(result) == {"nwe"}


def test_indifferent_highlights_both():
    result = port_result("sabine_pass", threshold=5.0)
    assert result["winner"] == "Indifferent"
    assert charts.highlighted_routes(result) == {"nwe", result["asia_route"]}


def test_cancel_highlights_nothing():
    assert charts.highlighted_routes(port_result("sabine_pass", henry_hub=20.0)) == set()


def test_map_draws_the_winner_thick():
    figure = charts.route_map(port_result("sabine_pass"))
    line_widths = [trace.line.width for trace in figure.data if trace.mode == "lines"]
    assert sorted(line_widths) == [2, 2, 2, 4]   # Sabine Pass has 4 routes: one thick winner


def test_closed_suez_is_dashed():
    figure = charts.route_map(port_result("sabine_pass"))
    dashes = [trace.line.dash for trace in figure.data if trace.mode == "lines"]
    assert dashes.count("dash") == 1             # only the Suez route is closed


def test_map_works_for_every_port():
    for port_key in config.LOAD_PORTS:
        figure = charts.route_map(port_result(port_key))
        lines = [trace for trace in figure.data if trace.mode == "lines"]
        assert len(lines) == len(config.LOAD_PORTS[port_key]["routes"])


def test_arb_over_time_has_one_coloured_bar_set_per_outcome():
    import pandas as pd
    table = pd.DataFrame({
        "month": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"]),
        "spread": [1.40, -0.60, 0.80],
        "outcome": ["Asia", "Europe", "Asia"],
        "netback_europe": [8.65, 10.65, 9.0],
        "netback_asia": [10.05, 10.05, 9.8],
        "asia_route": ["Panama", "Panama", "Cape"],
    })
    figure = charts.arb_over_time_chart(table, threshold=0.10)

    bars = {trace.name: trace for trace in figure.data}
    assert set(bars) == {"Europe", "Asia"}                  # no empty Indifferent/Cancel traces
    assert len(bars["Asia"].y) == 2                         # two Asia months
    assert bars["Asia"].marker.color == charts.OUTCOME_COLOURS["Asia"]


def test_win_rate_chart_stacks_the_four_outcomes():
    import pandas as pd
    by_year = pd.DataFrame({"year": [2025, 2026], "Europe": [50.0, 0.0], "Asia": [50.0, 0.0],
                            "Indifferent": [0.0, 50.0], "Cancel": [0.0, 50.0]})
    figure = charts.win_rate_by_year_chart(by_year)
    assert [trace.name for trace in figure.data] == charts.OUTCOME_ORDER
    assert figure.layout.barmode == "stack"


def test_seasonality_colours_follow_the_sign():
    import pandas as pd
    season = pd.DataFrame({"month_number": [1, 2], "month_name": ["Jan", "Feb"],
                           "average_spread": [0.725, -0.60], "months": [2, 2]})
    figure = charts.seasonality_chart(season)
    assert list(figure.data[0].marker.color) == [charts.OUTCOME_COLOURS["Asia"],
                                                 charts.OUTCOME_COLOURS["Europe"]]


def test_halfway_point_on_a_straight_line():
    # Three equal steps of 10 degrees: halfway (15) is first passed at the third point
    assert charts.halfway_point([(0, 0), (0, 10), (0, 20), (0, 30)]) == (0, 20)


def test_halfway_point_across_the_date_line():
    # 170 -> -170 is a 20-degree step (the short way), not 340
    assert charts.halfway_point([(0, 150), (0, 170), (0, -170), (0, -150)]) == (0, -170)
