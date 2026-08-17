"""Tests for src.agents.sourcing.sourcing_node.

RapidAPI calls are mocked via the fixtures in conftest.py — no real network
traffic or API keys required.
"""

from unittest.mock import patch

import pytest

from src.agents.sourcing import sourcing_node
from src.config import load_config
from src.metrics import new_run


@pytest.fixture(autouse=True)
def isolate_cities_cache(tmp_path):
    """Point the hotel dest_id cache at a throwaway path for these tests.

    sourcing_node persists newly-resolved dest_ids back to cities.json; without
    this, running the suite would write a real cities.json into the repo root
    on every test run. load_config() is lru_cached (one shared singleton for
    the whole process), so this saves/restores the attribute by hand rather
    than relying on monkeypatch, and is scoped to this module only so it
    doesn't affect test_config.py's assertions about the real config value.
    """
    hotels_config = load_config().sourcing.hotels
    original_path = hotels_config.cities_cache_path
    hotels_config.cities_cache_path = str(tmp_path / "cities.json")
    yield
    hotels_config.cities_cache_path = original_path


def test_missing_constraints_returns_empty_and_ends():
    out = sourcing_node({"origin": None, "destination": "JFK", "travel_dates": None})
    assert out["raw_flight_data"] == []
    assert out["raw_hotel_data"] == []
    assert out["next_node"] == "end"


def test_malformed_dates_returns_empty_and_ends():
    out = sourcing_node({"origin": "LHR", "destination": "JFK", "travel_dates": "garbage"})
    assert out["raw_flight_data"] == []
    assert out["raw_hotel_data"] == []
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
    directly and never call the Autocomplete endpoint or touch cities.json."""
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

    assert not any("auto-complete" in url for url in calls)
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
