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
