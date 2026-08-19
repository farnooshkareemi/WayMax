"""Tests for src.agents.sourcing.sourcing_node.

RapidAPI calls are mocked via the fixtures in conftest.py — no real network
traffic or API keys required.
"""

from unittest.mock import patch

from src.agents.sourcing import sourcing_node
from src.metrics import new_run


def test_missing_constraints_returns_empty_and_ends():
    out = sourcing_node({"origin": None, "destination": "JFK", "travel_dates": None})
    assert out["raw_flight_data"] == []
    assert out["raw_hotel_data"] == []
    assert out["sourcing_errors"] == []
    assert out["next_node"] == "end"


def test_malformed_dates_returns_empty_and_ends():
    out = sourcing_node({"origin": "LHR", "destination": "JFK", "travel_dates": "garbage"})
    assert out["raw_flight_data"] == []
    assert out["raw_hotel_data"] == []
    assert out["sourcing_errors"] == []
    assert out["next_node"] == "end"


def test_happy_path_parses_flights_and_hotels(mock_requests_get):
    with patch("src.agents.sourcing.requests.get", side_effect=mock_requests_get):
        out = sourcing_node({
            "origin": "LHR", "destination": "JFK",
            "travel_dates": "2026-09-20 to 2026-09-25",
        })

    assert len(out["raw_flight_data"]) == 1
    assert out["raw_flight_data"][0]["name"] == "TestAir"
    assert out["raw_flight_data"][0]["price"] == 200.0

    assert len(out["raw_hotel_data"]) == 1
    assert out["raw_hotel_data"][0]["name"] == "Test Hotel"
    # price_per_night = grossPrice / nights = 250 / 5
    assert out["raw_hotel_data"][0]["price_per_night"] == 50.0

    assert out["next_node"] == "optimizer"
    # A fully successful run must not report any sourcing errors - otherwise
    # the UI would wrongly tell the user something failed when it didn't.
    assert out["sourcing_errors"] == []


def test_flight_api_exception_is_recorded_as_a_sourcing_error(mock_requests_get):
    """A genuine API failure (not just zero results) must be distinguishable
    from a search that legitimately found nothing, so the UI can tell users
    'we couldn't reach the flight provider' instead of 'no flights exist'."""

    def _failing_get(url, headers=None, params=None, timeout=None):
        if "skyscanner" in url:
            raise ConnectionError("simulated network failure")
        return mock_requests_get(url, headers=headers, params=params, timeout=timeout)

    with patch("src.agents.sourcing.requests.get", side_effect=_failing_get):
        out = sourcing_node({
            "origin": "LHR", "destination": "JFK",
            "travel_dates": "2026-09-20 to 2026-09-25",
        })

    assert out["raw_flight_data"] == []
    assert len(out["sourcing_errors"]) == 1
    assert "Flight search failed" in out["sourcing_errors"][0]
    # The hotel call is independent and should still succeed.
    assert len(out["raw_hotel_data"]) == 1


def test_direct_only_passes_through_direct_flights(mock_requests_get):
    with patch("src.agents.sourcing.requests.get", side_effect=mock_requests_get):
        out = sourcing_node({
            "origin": "LHR", "destination": "JFK",
            "travel_dates": "2026-09-20 to 2026-09-25",
            "direct_only": True,  # fixture flight has 0 stops on both legs, so this should still pass through
        })
    assert len(out["raw_flight_data"]) == 1


def test_min_stars_filters_out_lower_rated_hotels(mock_requests_get):
    with patch("src.agents.sourcing.requests.get", side_effect=mock_requests_get):
        out = sourcing_node({
            "origin": "LHR", "destination": "JFK",
            "travel_dates": "2026-09-20 to 2026-09-25",
            "min_hotel_stars": 5,  # fixture hotel is propertyClass 4, should be filtered out
        })
    assert out["raw_hotel_data"] == []


def test_hotel_dest_id_short_circuits_autocomplete(mock_requests_get):
    """When the UI has already resolved hotel_dest_id, sourcing_node must use it
    directly and never call the Autocomplete endpoint."""
    calls = []

    def _tracking_get(url, headers=None, params=None, timeout=None):
        calls.append(url)
        return mock_requests_get(url, headers=headers, params=params, timeout=timeout)

    with patch("src.agents.sourcing.requests.get", side_effect=_tracking_get):
        out = sourcing_node({
            "origin": "LHR", "destination": "JFK",
            "travel_dates": "2026-09-20 to 2026-09-25",
            "hotel_dest_id": "999",
        })

    assert not any("autocomplete" in url for url in calls)
    assert len(out["raw_hotel_data"]) == 1


def test_records_metrics_when_run_is_active(mock_requests_get):
    metrics = new_run()
    with patch("src.agents.sourcing.requests.get", side_effect=mock_requests_get):
        sourcing_node({
            "origin": "LHR", "destination": "JFK",
            "travel_dates": "2026-09-20 to 2026-09-25",
        })

    call_names = [c.name for c in metrics.api_calls]
    assert "flights_search" in call_names
    assert "hotels_dest_lookup" in call_names
    assert "hotels_search" in call_names
    assert len(metrics.node_timings) == 1
    assert metrics.node_timings[0].node == "sourcing"
