"""Tests for src.agents.optimization.optimizer_node.

Pure logic, no I/O — covers budget-fits, no-fit fallback, room rounding, and
date-parsing edge cases.
"""

from src.agents.optimization import optimizer_node
from src.metrics import new_run


def _base_state(**overrides):
    state = {
        "max_budget": 1000.0,
        "raw_flight_data": [{"price": 200.0, "flight_number": "AB123", "departure_time": "2026-09-20 10:00"}],
        "raw_hotel_data": [{"price_per_night": 50.0, "name": "Test Hotel"}],
        "travel_dates": "2026-09-20 to 2026-09-25",
        "travelers": 1,
    }
    state.update(overrides)
    return state


def test_selects_combination_within_budget():
    out = optimizer_node(_base_state())
    itinerary = out["final_itinerary"]
    # 5 nights, 1 room: 200 + 50*5*1 = 450
    assert itinerary["within_budget"] is True
    assert itinerary["total_price"] == 450.0
    assert itinerary["nights_staying"] == 5
    assert out["next_node"] == "end"


def test_falls_back_to_cheapest_when_over_budget():
    out = optimizer_node(_base_state(max_budget=100.0))
    itinerary = out["final_itinerary"]
    assert itinerary["within_budget"] is False
    assert itinerary["total_price"] == 450.0  # same combo, just flagged as over budget


def test_rooms_needed_rounds_up_for_odd_traveler_count():
    # 3 travelers / 2-per-room divisor -> ceil(1.5) = 2 rooms
    out = optimizer_node(_base_state(travelers=3))
    itinerary = out["final_itinerary"]
    # 200 + 50*5*2 = 700
    assert itinerary["total_price"] == 700.0


def test_missing_dates_falls_back_to_default_nights():
    out = optimizer_node(_base_state(travel_dates=""))
    itinerary = out["final_itinerary"]
    assert itinerary["nights_staying"] == 1  # default_nights_fallback from config


def test_malformed_dates_falls_back_to_default_nights():
    out = optimizer_node(_base_state(travel_dates="not-a-date to also-not-a-date"))
    itinerary = out["final_itinerary"]
    assert itinerary["nights_staying"] == 1


def test_empty_flight_and_hotel_lists_return_no_itinerary():
    out = optimizer_node(_base_state(raw_flight_data=[], raw_hotel_data=[]))
    assert out["final_itinerary"] is None


def test_no_max_budget_treats_budget_as_unlimited():
    out = optimizer_node(_base_state(max_budget=None))
    itinerary = out["final_itinerary"]
    assert itinerary["within_budget"] is True


def test_records_metrics_when_run_is_active():
    metrics = new_run()
    optimizer_node(_base_state())
    assert metrics.optimizer is not None
    assert metrics.optimizer.combinations_evaluated == 1
    assert metrics.optimizer.best_total_price == 450.0
    assert metrics.optimizer.within_budget is True
    assert len(metrics.node_timings) == 1
    assert metrics.node_timings[0].node == "optimizer"
