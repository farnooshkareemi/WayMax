"""Shared fixtures for the WayMax test suite.

Everything here is offline: no real network calls or LLM invocations. Flight
and hotel API responses are mocked MagicMocks shaped like real RapidAPI
payloads (see src/agents/sourcing.py for the parsing logic they exercise);
the Gemini structured-output call is mocked at the src.agents.supervisor
module level.
"""

import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def reset_metrics_run():
    """Ensure no metrics run leaks between tests (src.metrics keeps a module-level
    'current run' singleton that node instrumentation attaches to)."""
    from src import metrics
    metrics._current_run = None
    yield
    metrics._current_run = None


@pytest.fixture
def mock_flight_response():
    """A RapidAPI Skyscanner roundtrip-shaped response with a single direct itinerary."""
    resp = MagicMock(status_code=200)
    resp.raise_for_status = lambda: None
    resp.json = lambda: {
        "results": [
            {
                "price_raw": 200,
                "carriers": ["TestAir"],
                "legs": [
                    {
                        "dep": "2026-09-20T10:00:00",
                        "arr": "2026-09-20T12:00:00",
                        "dur_min": 120,
                        "stops": 0,
                        "segments": [{"flight": "AB123"}],
                    },
                    {
                        "dep": "2026-09-25T14:00:00",
                        "arr": "2026-09-25T16:00:00",
                        "dur_min": 120,
                        "stops": 0,
                        "segments": [{"flight": "AB456"}],
                    },
                ],
            }
        ]
    }
    return resp


@pytest.fixture
def mock_hotel_autocomplete_response():
    """Shaped after the real /booking/autocomplete response: a flat 'data' list
    of items keyed by dest_id/dest_type/label (not 'search_type'/'id')."""
    resp = MagicMock(status_code=200)
    resp.raise_for_status = lambda: None
    resp.json = lambda: {
        "data": [{"dest_type": "city", "dest_id": "123", "label": "Test City, Test Country", "label1": "Test City"}],
        "totalResultCount": 1,
        "status": True,
    }
    return resp


@pytest.fixture
def mock_hotel_search_response():
    resp = MagicMock(status_code=200)
    resp.raise_for_status = lambda: None
    resp.json = lambda: {
        "data": [
            {
                "id": 217618,
                "propertyClass": 4,
                "name": "Test Hotel",
                "priceBreakdown": {"grossPrice": {"value": 250}},
                "address": "Somewhere",
            }
        ]
    }
    return resp


@pytest.fixture
def mock_requests_get(mock_flight_response, mock_hotel_autocomplete_response, mock_hotel_search_response):
    """A side_effect function for patching requests.get, routing by URL substring
    to the appropriate mocked response (flights vs. hotel autocomplete vs. hotel search)."""

    def _fake_get(url, headers=None, params=None, timeout=None):
        if "skyscanner" in url:
            return mock_flight_response
        if "autocomplete" in url:
            return mock_hotel_autocomplete_response
        return mock_hotel_search_response

    return _fake_get
