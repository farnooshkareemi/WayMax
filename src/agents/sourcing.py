import logging
import os
import requests
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv
from src.config import load_config
from src.metrics import get_current_run, node_timer

load_dotenv()

logger = logging.getLogger(__name__)


def sourcing_node(state: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("Starting sourcing node")
    config = load_config().sourcing

    run_metrics = get_current_run()
    timer = node_timer(run_metrics, "sourcing") if run_metrics else None
    if timer:
        timer.__enter__()

    origin = state.get("origin")
    destination = state.get("destination")
    travel_dates = state.get("travel_dates")

    # --- GRAB UI CONSTRAINTS FROM STATE ---
    min_stars = state.get("min_hotel_stars")
    direct_only = state.get("direct_only", False)
    max_flight_hours = state.get("max_flight_hours", config.flights.default_max_flight_hours)

    travelers = state.get("travelers") or 1
    raw_flight_data = []
    raw_hotel_data = []
    nights = 1

    if not all([origin, destination, travel_dates]):
        logger.debug("Missing constraints. Returning empty data.")
        if timer:
            timer.__exit__(None, None, None)
        return {"raw_flight_data": raw_flight_data, "raw_hotel_data": raw_hotel_data, "next_node": "end"}

    try:
        check_in_date = travel_dates.split(" to ")[0].strip()
        check_out_date = travel_dates.split(" to ")[1].strip()

        d1 = datetime.strptime(check_in_date, "%Y-%m-%d")
        d2 = datetime.strptime(check_out_date, "%Y-%m-%d")
        nights = (d2 - d1).days
        if nights <= 0:
            nights = 1
    except Exception:
        logger.warning("Date parsing error", exc_info=True)
        if timer:
            timer.__exit__(None, None, None)
        return {"raw_flight_data": raw_flight_data, "raw_hotel_data": raw_hotel_data, "next_node": "end"}

    # -----------------------------------------
    # 1. RAPIDAPI SKYSCANNER FLIGHTS (round trip)
    # -----------------------------------------
    try:
        logger.debug(
            "Requesting round-trip flights from %s to %s, %s -> %s, for %s traveler(s)...",
            origin, destination, check_in_date, check_out_date, travelers,
        )

        RAPIDAPI_KEY = os.getenv("Sky_Scanner_Key")
        RAPIDAPI_HOST = config.flights.host

        flight_url = config.flights.roundtrip_url
        querystring = {
            "origin": origin,
            "destination": destination,
            "date": check_in_date,
            "return_date": check_out_date,
            "limit": str(config.flights.request_limit),
            "adults": str(travelers),
            "currency": config.flights.currency,
            "cabin": config.flights.cabin_class,
            "market": config.flights.market,
            "locale": config.flights.locale
        }

        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": RAPIDAPI_HOST
        }

        flight_res = requests.get(flight_url, headers=headers, params=querystring, timeout=config.flights.timeout_seconds)
        flight_res.raise_for_status()
        data = flight_res.json()

        results = data.get("results", []) if isinstance(data, dict) else []

        def _leg_hours(leg: dict) -> float:
            """Leg duration in hours, from dur_min or falling back to dep/arr timestamps."""
            dur_min = leg.get("dur_min")
            if dur_min:
                return float(dur_min) / 60.0
            dt_format = "%Y-%m-%dT%H:%M:%S"
            d1_fl = datetime.strptime(leg["dep"], dt_format)
            d2_fl = datetime.strptime(leg["arr"], dt_format)
            return (d2_fl - d1_fl).total_seconds() / 3600.0

        for result in results:
            if len(raw_flight_data) >= config.flights.result_limit:
                break

            legs = result.get("legs", [])
            if len(legs) < 2:
                # Not a full round trip (outbound + inbound) - skip, don't misprice it.
                continue

            outbound_leg, inbound_leg = legs[0], legs[1]

            # direct_only and max_flight_hours are enforced per-leg: a traveler
            # asking for "direct" or a duration cap means each leg individually,
            # not the combined outbound+inbound trip.
            if direct_only and (outbound_leg.get("stops", 0) > 0 or inbound_leg.get("stops", 0) > 0):
                continue

            try:
                if _leg_hours(outbound_leg) > max_flight_hours or _leg_hours(inbound_leg) > max_flight_hours:
                    continue
            except Exception:
                logger.debug("Duration calculation failed, excluding itinerary", exc_info=True)
                continue

            outbound_segments = outbound_leg.get("segments", [])
            inbound_segments = inbound_leg.get("segments", [])

            total_price = float(result.get("price_raw", 0.0))

            airline = "Unknown Airline"
            carriers = result.get("carriers", [])
            if carriers:
                airline = carriers[0]

            outbound_flight_num = outbound_segments[0].get("flight", "TBD") if outbound_segments else "TBD"
            inbound_flight_num = inbound_segments[0].get("flight", "TBD") if inbound_segments else "TBD"

            raw_flight_data.append({
                "name": str(airline),
                "price": total_price,
                "flight_number": str(outbound_flight_num),
                "departure_time": str(outbound_leg.get("dep", "TBD")).replace("T", " ")[:16],
                "arrival_time": str(outbound_leg.get("arr", "TBD")).replace("T", " ")[:16],
                "return_flight_number": str(inbound_flight_num),
                "return_departure_time": str(inbound_leg.get("dep", "TBD")).replace("T", " ")[:16],
                "return_arrival_time": str(inbound_leg.get("arr", "TBD")).replace("T", " ")[:16],
                "cabin_class": "Economy"
            })

        logger.info("Successfully parsed %d live round-trip flights", len(raw_flight_data))

        if run_metrics:
            run_metrics.add_api_call(
                "flights_search", ok=True,
                status_code=flight_res.status_code,
                results_returned=len(raw_flight_data),
            )

    except Exception as e:
        logger.warning("RapidAPI Flight Exception", exc_info=True)
        if run_metrics:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            run_metrics.add_api_call("flights_search", ok=False, status_code=status_code)

    # -----------------------------------------
    # 2. RAPIDAPI BOOKING DATA (HOTELS)
    # -----------------------------------------
    try:
        hotel_headers = {
            "x-rapidapi-key": os.getenv("Sky_Scanner_Key"),
            "x-rapidapi-host": config.hotels.host
        }

        dest_type = "city"
        dest_id = state.get("hotel_dest_id")

        if dest_id:
            # Resolved once already, at the source: the user picked this exact
            # destination from a live search box in the UI. No guessing needed.
            logger.debug("Using UI-resolved hotel_dest_id: %s", dest_id)
            if run_metrics:
                run_metrics.add_api_call("hotels_dest_lookup", ok=True, cache_hit=True)
        else:
            # Fallback for invocations that don't go through the UI (e.g. a
            # chat-only prompt with no destination_searchbox selection): resolve
            # live against Autocomplete. Booking.com's dest_id is keyed by city
            # name, not IATA airport code, so always resolve using
            # destination_city, falling back to destination only if the LLM
            # extraction didn't populate it.
            dest_query_name = state.get("destination_city") or destination
            logger.debug("No hotel_dest_id in state. Calling Autocomplete API for '%s'...", dest_query_name)
            auto_url = config.hotels.autocomplete_url
            auto_query = {"location": dest_query_name, "language_code": config.hotels.language_code}

            try:
                auto_res = requests.get(auto_url, headers=hotel_headers, params=auto_query, timeout=config.hotels.autocomplete_timeout_seconds)
                auto_res.raise_for_status()
                auto_data = auto_res.json()

                results = auto_data.get("data", [])
                if isinstance(results, list) and len(results) > 0:
                    # Prefer city-level matches (dest_type also includes district,
                    # airport, landmark, region, country) - hotel search wants a
                    # city dest_id.
                    for item in results:
                        if item.get("dest_type") == "city":
                            dest_id = item.get("dest_id")
                            dest_type = "city"
                            break
                    if not dest_id:
                        dest_id = results[0].get("dest_id")
                        dest_type = results[0].get("dest_type", "city")

                if dest_id:
                    logger.debug("Autocomplete resolved '%s' to %s", dest_query_name, dest_id)
                if run_metrics:
                    run_metrics.add_api_call(
                        "hotels_dest_lookup", ok=True,
                        status_code=auto_res.status_code, cache_hit=False,
                    )
            except Exception as e:
                logger.warning("Autocomplete API failed", exc_info=True)
                if run_metrics:
                    status_code = getattr(getattr(e, "response", None), "status_code", None)
                    run_metrics.add_api_call("hotels_dest_lookup", ok=False, status_code=status_code, cache_hit=False)

        # --- EXECUTE HOTEL SEARCH ---
        if not dest_id:
            logger.debug("Could not resolve destination ID for '%s'. Skipping hotels.", destination)
        else:
            logger.debug("Requesting Booking Data API for %s stays... (Min Stars: %s)", destination, min_stars)
            
            hotel_url = config.hotels.search_url
            hotel_query = {
                "dest_id": dest_id,
                "dest_type": dest_type,
                "units": config.hotels.units,
                "temperature_unit": config.hotels.temperature_unit,
                "arrival_date": check_in_date,
                "departure_date": check_out_date,
                "adults": str(travelers),
                "room_qty": str(config.hotels.room_qty),
                "currency_code": config.hotels.currency
            }

            hotel_res = requests.get(hotel_url, headers=hotel_headers, params=hotel_query, timeout=config.hotels.search_timeout_seconds)
            hotel_res.raise_for_status()
            hotel_json = hotel_res.json()
            
            properties = []
            if isinstance(hotel_json, dict):
                for key in ["data", "result", "results", "properties"]:
                    if isinstance(hotel_json.get(key), list):
                        properties = hotel_json.get(key)
                        break

            # --- FILTER HOTELS DYNAMICALLY ---
            for prop in properties:
                if len(raw_hotel_data) >= config.hotels.result_limit:
                    break
                    
                hotel_stars = prop.get("propertyClass", 0)
                
                if min_stars and hotel_stars < min_stars:
                    continue

                name = prop.get("name", "Unknown Hotel")
                
                price = 0.0
                price_breakdown = prop.get("priceBreakdown", {})
                if price_breakdown:
                    gross_price = price_breakdown.get("grossPrice", {})
                    price = float(gross_price.get("value", 0.0))
                    
                # Dynamically fetch real address if available
                address = prop.get("address", f"Central {destination}")
                
                if price > 0:
                    raw_hotel_data.append({
                        "name": str(name),
                        "price_per_night": round(price / nights, 2),
                        "address": address,
                        "rating": int(hotel_stars),
                        "room_type": "Standard Room"
                    })
                    
            logger.info("Successfully parsed %d live Booking.com hotels", len(raw_hotel_data))

            if run_metrics:
                run_metrics.add_api_call(
                    "hotels_search", ok=True,
                    status_code=hotel_res.status_code,
                    results_returned=len(raw_hotel_data),
                )

    except Exception as e:
        logger.warning("RapidAPI Hotel Exception", exc_info=True)
        if run_metrics:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            run_metrics.add_api_call("hotels_search", ok=False, status_code=status_code)

    if timer:
        timer.__exit__(None, None, None)

    return {
        "raw_flight_data": raw_flight_data,
        "raw_hotel_data": raw_hotel_data,
        "next_node": "optimizer"
    }