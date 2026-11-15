"""
Tests for charts.py: the map highlights the right route.

(We don't test how the map LOOKS; that's checked by eye in the browser.
We test the decision of what to highlight, which is easy to get wrong.)
"""

import charts


def make_result(decision, winner, asia_route="Panama"):
    """A minimal fake result with only what the map needs."""
    return {
        "decision": decision, "winner": winner, "asia_route": asia_route,
        "netback_europe": 27.90, "netback_asia_panama": 28.80, "netback_asia_cape": 27.93,
    }


def test_asia_win_highlights_the_chosen_route():
    assert charts.highlighted_routes(make_result("LIFT", "Asia", "Cape")) == {"cape"}


def test_europe_win_highlights_nwe():
    assert charts.highlighted_routes(make_result("LIFT", "Europe")) == {"nwe"}


def test_indifferent_highlights_both():
    assert charts.highlighted_routes(make_result("LIFT", "Indifferent", "Panama")) == {"nwe", "panama"}


def test_cancel_highlights_nothing():
    assert charts.highlighted_routes(make_result("CANCEL", "Asia")) == set()


def test_map_draws_the_winner_thick():
    figure = charts.route_map(make_result("LIFT", "Asia", "Panama"), {"panama_available": True})
    line_widths = [trace.line.width for trace in figure.data if trace.mode == "lines"]
    assert sorted(line_widths) == [2, 2, 4]   # two grey routes, one thick winner


def test_closed_panama_is_dashed():
    figure = charts.route_map(make_result("LIFT", "Europe", "Cape"), {"panama_available": False})
    dashes = [trace.line.dash for trace in figure.data if trace.mode == "lines"]
    assert "dash" in dashes


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
