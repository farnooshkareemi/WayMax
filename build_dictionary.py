import os
import time
import json
import requests
from dotenv import load_dotenv

# Load your RapidAPI key from your .env file
load_dotenv()

RAPIDAPI_KEY = os.getenv("Sky_Scanner_Key")
HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "booking-data.p.rapidapi.com"
}
URL = "https://booking-data.p.rapidapi.com/booking-app/search/auto-complete"

# --- THE ULTIMATE 100+ GLOBAL CITIES LIST ---
TOP_CITIES = [
    # Europe
    "Paris", "London", "Rome", "Milan", "Turin", "Venice", "Florence", "Naples",
    "Barcelona", "Madrid", "Amsterdam", "Berlin", "Munich", "Frankfurt", "Vienna",
    "Zurich", "Geneva", "Athens", "Lisbon", "Prague", "Budapest", "Dublin",
    "Edinburgh", "Stockholm", "Copenhagen", "Oslo", "Helsinki", "Warsaw", "Krakow",
    "Brussels", "Nice", "Marseille", "Lyon",
    
    # Asia
    "Tokyo", "Kyoto", "Osaka", "Seoul", "Singapore", "Bangkok", "Phuket",
    "Hong Kong", "Macau", "Taipei", "Beijing", "Shanghai", "Guangzhou",
    "Kuala Lumpur", "Ho Chi Minh City", "Hanoi", "Manila", "Jakarta", "Bali",
    "Mumbai", "Delhi", "Jaipur", "Chennai", "Colombo", "Kathmandu", "Tehran",
    
    # Middle East & Africa
    "Dubai", "Abu Dhabi", "Istanbul", "Antalya", "Doha", "Riyadh", "Mecca",
    "Medina", "Tel Aviv", "Jerusalem", "Cairo", "Marrakech", "Casablanca",
    "Cape Town", "Johannesburg", "Nairobi",
    
    # North America
    "New York", "Los Angeles", "Miami", "San Francisco", "Las Vegas", "Chicago",
    "Washington D.C.", "Boston", "Seattle", "Honolulu", "Orlando", "New Orleans",
    "Toronto", "Vancouver", "Montreal", "Cancun", "Mexico City",
    
    # South America
    "Rio de Janeiro", "Sao Paulo", "Buenos Aires", "Lima", "Bogota", "Santiago",
    "Cusco", "Quito",
    
    # Oceania
    "Sydney", "Melbourne", "Brisbane", "Perth", "Auckland", "Queenstown"
]

def mine_city_ids():
    city_map = {}
    
    print(f"🚀 Starting Miner for {len(TOP_CITIES)} cities...\n")
    
    for city in TOP_CITIES:
        print(f"Searching for {city}...")
        
        try:
            response = requests.get(URL, headers=HEADERS, params={"query": city}, timeout=15)
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
            
        # VERY IMPORTANT: Sleep for 1.5 seconds between calls so RapidAPI 
        # doesn't block you for sending too many requests too fast (HTTP 429).
        time.sleep(1.5)

    # Save the results to a JSON file
    with open("cities.json", "w") as f:
        json.dump(city_map, f, indent=4)
        
    print(f"\n🎉 Done! Successfully mapped {len(city_map)} cities to 'cities.json'.")

if __name__ == "__main__":
    mine_city_ids()