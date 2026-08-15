import os
import time
import json
import requests
from dotenv import load_dotenv
from src.config import load_config

# Load your RapidAPI key from your .env file
load_dotenv()

config = load_config().build_dictionary

RAPIDAPI_KEY = os.getenv("Sky_Scanner_Key")
HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": config.host
}
URL = config.autocomplete_url
TOP_CITIES = config.top_cities

def mine_city_ids():
    city_map = {}

    print(f"🚀 Starting Miner for {len(TOP_CITIES)} cities...\n")

    for city in TOP_CITIES:
        print(f"Searching for {city}...")

        try:
            response = requests.get(URL, headers=HEADERS, params={"query": city}, timeout=config.request_timeout_seconds)
            response.raise_for_status()
            data = response.json()
            
            dest_id = None
            results = data.get("data", data.get("result", []))
            
            if isinstance(results, list) and len(results) > 0:
                # Find the first item tagged as a 'city'
                for item in results:
                    if item.get("search_type") == "city":
                        dest_id = item.get("dest_id") or item.get("id")
                        break
                # Fallback if no specific 'city' tag exists
                if not dest_id:
                    dest_id = results[0].get("dest_id", results[0].get("id"))
            
            if dest_id:
                # Map the uppercase city name to the ID
                city_map[city.upper()] = str(dest_id)
                print(f"   ✅ Found: {dest_id}")
            else:
                print(f"   ❌ No ID found.")
                
        except Exception as e:
            print(f"   ⚠️ API Error: {e}")
            
        # VERY IMPORTANT: Sleep between calls so RapidAPI
        # doesn't block you for sending too many requests too fast (HTTP 429).
        time.sleep(config.sleep_between_calls_seconds)

    # Save the results to a JSON file
    with open(config.output_path, "w") as f:
        json.dump(city_map, f, indent=4)

    print(f"\n🎉 Done! Successfully mapped {len(city_map)} cities to '{config.output_path}'.")

if __name__ == "__main__":
    mine_city_ids()