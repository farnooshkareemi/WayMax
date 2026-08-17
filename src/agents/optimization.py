import logging
from typing import Dict, Any
from datetime import datetime
import re
import math
from src.config import load_config
from src.metrics import get_current_run, node_timer

logger = logging.getLogger(__name__)


def optimizer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimization node that finds the cheapest combination of flights and hotels
    within the user's budget, accurately calculating the duration of the stay and rooms needed.
    """
    logger.info("Starting optimizer node")

    run_metrics = get_current_run()
    timer = node_timer(run_metrics, "optimizer") if run_metrics else None
    if timer:
        timer.__enter__()

    config = load_config().optimizer

    max_budget = state.get("max_budget")
    raw_flight_data = state.get("raw_flight_data", [])
    raw_hotel_data = state.get("raw_hotel_data", [])
    travel_dates = state.get("travel_dates", "")

    # --- NEW: Grab travelers to calculate hotel rooms ---
    travelers = state.get("travelers") or 1
    # Assuming N people per room (config-driven), we round up (e.g., 3 people = 2 rooms)
    rooms_needed = math.ceil(travelers / config.rooms_per_traveler_divisor)

    # 1. Parse dates to calculate the total number of nights
    num_nights = config.default_nights_fallback  # Default fallback if parsing fails
    if travel_dates:
        dates = re.findall(r'\d{4}-\d{2}-\d{2}', travel_dates)
        if len(dates) >= 2:
            try:
                start_date = datetime.strptime(dates[0], "%Y-%m-%d")
                end_date = datetime.strptime(dates[1], "%Y-%m-%d")
                calculated_nights = (end_date - start_date).days
                if calculated_nights > 0:
                    num_nights = calculated_nights
            except ValueError:
                pass  # Fallback to 1 if parsing fails

    best_combination = None
    lowest_total_price = float("inf")
    combinations_evaluated = 0

    # If max_budget is not set, treat it as infinite for optimization purposes
    budget_limit = float(max_budget) if max_budget is not None else float("inf")

    # 2. Iterate through options to find the best valid combination
    for flight in raw_flight_data:
        for hotel in raw_hotel_data:
            combinations_evaluated += 1
            # Flight price is already the total for ALL passengers from the Duffel API
            flight_price = flight.get("price", 0.0)
            hotel_nightly_rate = hotel.get("price_per_night", hotel.get("price", 0.0))

            # --- RAG: one checked bag per traveler, using the RAG-estimated fee ---
            baggage_fee_per_bag = flight.get("baggage_fee_estimate", 0.0)
            total_baggage_cost = baggage_fee_per_bag * travelers

            # --- NEW: Calculate true total price based on duration AND rooms needed ---
            total_hotel_price = hotel_nightly_rate * num_nights * rooms_needed
            total_price = flight_price + total_hotel_price + total_baggage_cost

            if total_price <= budget_limit:
                if total_price < lowest_total_price:
                    lowest_total_price = total_price
                    best_combination = {
                        "flight": flight,
                        "hotel": hotel,
                        "nights_staying": num_nights,
                        "flight_cost": flight_price,
                        "hotel_total_cost": total_hotel_price,
                        "baggage_cost": total_baggage_cost,
                        "total_price": round(total_price, 2),
                        "within_budget": True
                    }

    # Fallback: If no combination was within budget, return the absolute cheapest options available
    if not best_combination and raw_flight_data and raw_hotel_data:
        cheapest_flight = min(raw_flight_data, key=lambda x: x.get("price", 0.0))
        cheapest_hotel = min(raw_hotel_data, key=lambda x: x.get("price_per_night", x.get("price", 0.0)))

        f_price = cheapest_flight.get("price", 0.0)
        h_rate = cheapest_hotel.get("price_per_night", cheapest_hotel.get("price", 0.0))

        # Apply the same rooms_needed and baggage logic to the fallback
        fallback_hotel_total = h_rate * num_nights * rooms_needed
        fallback_baggage_total = cheapest_flight.get("baggage_fee_estimate", 0.0) * travelers
        total_p = f_price + fallback_hotel_total + fallback_baggage_total

        best_combination = {
            "flight": cheapest_flight,
            "hotel": cheapest_hotel,
            "nights_staying": num_nights,
            "flight_cost": f_price,
            "hotel_total_cost": fallback_hotel_total,
            "baggage_cost": fallback_baggage_total,
            "total_price": round(total_p, 2),
            "within_budget": False
        }

    # Terminal confirmation of rich data extraction
    if best_combination:
        logger.info(
            "Optimizer selected best itinerary for %s traveler(s) (%s room(s)) totaling %s",
            travelers, rooms_needed, best_combination["total_price"],
        )
        logger.debug(
            "--> Selected Flight: %s departing at %s",
            best_combination["flight"].get("flight_number", "N/A"),
            best_combination["flight"].get("departure_time", "N/A"),
        )
        logger.debug(
            "--> Selected Hotel: %s located at %s",
            best_combination["hotel"].get("name", "N/A"),
            best_combination["hotel"].get("address", "N/A"),
        )
    else:
        logger.info("Optimizer failed to find any valid combinations.")

    if run_metrics:
        run_metrics.set_optimizer_quality(
            combinations_evaluated=combinations_evaluated,
            best_total_price=best_combination.get("total_price") if best_combination else None,
            within_budget=best_combination.get("within_budget") if best_combination else None,
        )
    if timer:
        timer.__exit__(None, None, None)

    return {
        "final_itinerary": best_combination,
        "next_node": "end",
    }