import os
import requests
import re
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv
from src.config import load_config

load_dotenv()

def sourcing_node(state: Dict[str, Any]) -> Dict[str, Any]:
    print("--- STARTING SOURCING NODE ---")
    config = load_config().sourcing

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
        print("DEBUG: Missing constraints. Returning empty data.")
        return {"raw_flight_data": raw_flight_data, "raw_hotel_data": raw_hotel_data, "next_node": "end"}

    try:
        check_in_date = travel_dates.split(" to ")[0].strip()
        check_out_date = travel_dates.split(" to ")[1].strip() 
        
        d1 = datetime.strptime(check_in_date, "%Y-%m-%d")
        d2 = datetime.strptime(check_out_date, "%Y-%m-%d")
        nights = (d2 - d1).days
        if nights <= 0:
            nights = 1
    except Exception as e:
        print(f"DEBUG: Date parsing error: {e}")
        return {"raw_flight_data": raw_flight_data, "raw_hotel_data": raw_hotel_data, "next_node": "end"}

    # -----------------------------------------
    # 1. RAPIDAPI SKYSCANNER FLIGHTS
    # -----------------------------------------
    try:
        print(f"DEBUG: Requesting Crawlio API from {origin} to {destination} on {check_in_date} for {travelers} traveler(s)...")
        
        RAPIDAPI_KEY = os.getenv("Sky_Scanner_Key")
        RAPIDAPI_HOST = config.flights.host

        flight_url = config.flights.url
        querystring = {
            "origin": origin,
            "destination": destination,
            "date": check_in_date,
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

        itineraries = []
        if isinstance(data, dict):
            for key in ["itineraries", "results", "flights", "offers", "legs", "data"]:
                if isinstance(data.get(key), list):
                    itineraries = data.get(key)
                    break
            if not itineraries:
                for key, value in data.items():
                    if isinstance(value, list) and len(value) > 0:
                        itineraries = value
                        break
            if not itineraries:
                for key, value in data.items():
                    if isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if isinstance(sub_value, list) and len(sub_value) > 0:
                                itineraries = sub_value
                                break

        for itin in itineraries:
            if len(raw_flight_data) >= config.flights.result_limit:
                break
                
            legs = itin.get("legs", [])
            if not legs:
                continue
                
            first_leg = legs[0]
            segments = first_leg.get("segments", [])
            
            if direct_only and len(segments) > 1:
                continue
                
            dep_time = first_leg.get("dep", "TBD")
            arr_time = first_leg.get("arr", "TBD")

            if dep_time != "TBD" and arr_time != "TBD":
                dep_clean = str(dep_time).replace("T", " ")[:16]
                arr_clean = str(arr_time).replace("T", " ")[:16]
                
                try:
                    duration_mins = first_leg.get("duration")
                    if duration_mins:
                        flight_hours = int(duration_mins) / 60.0
                    else:
                        dt_format = "%Y-%m-%d %H:%M"
                        d1_fl = datetime.strptime(dep_clean, dt_format)
                        d2_fl = datetime.strptime(arr_clean, dt_format)
                        flight_hours = (d2_fl - d1_fl).total_seconds() / 3600.0

                    if flight_hours > max_flight_hours:
                        continue 
                except Exception as e:
                    print(f"DEBUG: Duration calculation failed: {e}")

                dep_time = dep_clean
                arr_time = arr_clean

            total_price = 0.0
            if "price" in itin:
                p = itin["price"]
                raw_price = str(p.get("amount", p) if isinstance(p, dict) else p)
                clean_price = re.sub(r'[^\d.]', '', raw_price)
                if clean_price:
                    total_price = float(clean_price)
            
            airline = "Unknown Airline"
            carriers = itin.get("carriers", [])
            if carriers and len(carriers) > 0:
                airline = carriers[0].get("name", carriers[0]) if isinstance(carriers[0], dict) else carriers[0]
            
            flight_num = "TBD"
            if segments and len(segments) > 0:
                flight_num = segments[0].get("flight", "TBD")

            raw_flight_data.append({
                "name": str(airline),
                "price": total_price,
                "flight_number": str(flight_num),
                "departure_time": dep_time,
                "arrival_time": arr_time,
                "cabin_class": "Economy"
            })
            
        print(f"DEBUG: Successfully parsed {len(raw_flight_data)} live Skyscanner flights!")
        
    except Exception as e:
        print(f"DEBUG: RapidAPI Flight Exception: {e}")

    # -----------------------------------------
    # 2. RAPIDAPI BOOKING DATA (HOTELS)
    # -----------------------------------------
    try:
        hotel_headers = {
            "x-rapidapi-key": os.getenv("Sky_Scanner_Key"),
            "x-rapidapi-host": config.hotels.host
        }

        # --- HYBRID MAPPING STRATEGY ---
        import json
        LOCAL_DEST_MAP = {}
        try:
            with open(config.hotels.cities_cache_path, "r") as f:
                LOCAL_DEST_MAP = json.load(f)
        except Exception as e:
            print(f"DEBUG: Failed to load cities.json cache: {e}")
        
        dest_key = str(destination).strip().upper()
        dest_id = LOCAL_DEST_MAP.get(dest_key)
        dest_type = "city"
        
        if dest_id:
            print(f"DEBUG: Local cache hit! '{destination}' resolved to {dest_id}")
        else:
            print(f"DEBUG: Cache miss for '{destination}'. Calling Autocomplete API...")
            auto_url = config.hotels.autocomplete_url
            auto_query = {"query": destination}

            try:
                auto_res = requests.get(auto_url, headers=hotel_headers, params=auto_query, timeout=config.hotels.autocomplete_timeout_seconds)
                auto_res.raise_for_status()
                auto_data = auto_res.json()
                
                results = auto_data.get("data", auto_data.get("result", []))
                if isinstance(results, list) and len(results) > 0:
                    for item in results:
                        if item.get("search_type") == "city" or "dest_id" in item:
                            dest_id = item.get("dest_id") or item.get("id")
                            dest_type = item.get("search_type", "city")
                            break
                    if not dest_id:
                        dest_id = results[0].get("dest_id", results[0].get("id"))
                
                if dest_id:
                    print(f"DEBUG: Autocomplete resolved '{destination}' to {dest_id}")
            except Exception as e:
                print(f"DEBUG: Autocomplete API failed: {e}")

        # --- EXECUTE HOTEL SEARCH ---
        if not dest_id:
            print(f"DEBUG: Could not resolve destination ID for '{destination}'. Skipping hotels.")
        else:
            print(f"DEBUG: Requesting Booking Data API for {destination} stays... (Min Stars: {min_stars})")
            
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
                    
            print(f"DEBUG: Successfully parsed {len(raw_hotel_data)} live Booking.com hotels!")

    except Exception as e:
        print(f"DEBUG: RapidAPI Hotel Exception: {e}")

    return {
        "raw_flight_data": raw_flight_data,
        "raw_hotel_data": raw_hotel_data,
        "next_node": "optimizer"
    }