from src.agents.sourcing import sourcing_node

# Create a dummy state with all required variables
test_state = {
    "origin": "LHR",
    "destination": "JFK",
    "travel_dates": "2026-09-20 to 2026-09-25"
}

print("Initiating test run...")
output = sourcing_node(test_state)

print("\n--- FINAL OUTPUT ---")
print(f"Flights Found: {len(output.get('raw_flight_data', []))}")
print(f"Hotels Found: {len(output.get('raw_hotel_data', []))}")
print(f"Routing to: {output.get('next_node')}")
