"""Sanity checks that config/config.yaml loads and validates against src.config's
schema, guarding against config/code drift."""

from src.config import load_config


def test_config_loads_without_error():
    config = load_config()
    assert config is not None


def test_llm_section():
    config = load_config()
    assert config.llm.model == "gemini-2.5-flash"


def test_sourcing_flights_section():
    flights = load_config().sourcing.flights
    assert flights.host == "skyscanner-flights4.p.rapidapi.com"
    assert flights.result_limit == 5
    assert flights.timeout_seconds == 30


def test_sourcing_hotels_section():
    hotels = load_config().sourcing.hotels
    assert hotels.host == "booking-data.p.rapidapi.com"
    assert hotels.result_limit == 5
    assert hotels.cities_cache_path == "cities.json"


def test_optimizer_section():
    optimizer = load_config().optimizer
    assert optimizer.rooms_per_traveler_divisor == 2
    assert optimizer.default_nights_fallback == 1


def test_ui_section_has_expected_ranges():
    ui = load_config().ui
    assert ui.budget.min == 100
    assert ui.budget.max == 20000
    assert ui.travelers.default == 1
    assert len(ui.currencies) > 0


def test_build_dictionary_section_has_cities():
    build_dict = load_config().build_dictionary
    assert len(build_dict.top_cities) > 50
    assert "Paris" in build_dict.top_cities
