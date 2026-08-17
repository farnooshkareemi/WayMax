import sys
import os
import platform
import json
import datetime
import requests
import streamlit as st
from streamlit_star_rating import st_star_rating
from streamlit_searchbox import st_searchbox
from langchain_core.messages import HumanMessage, AIMessage

# 1. WINDOWS PYTORCH DLL HOTFIX
if platform.system() == "Windows":
    import ctypes
    from importlib.util import find_spec
    try:
        if (spec := find_spec("torch")) and spec.origin and os.path.exists(
            dll_path := os.path.join(os.path.dirname(spec.origin), "lib", "c10.dll")
        ):
            ctypes.CDLL(os.path.normpath(dll_path))
    except Exception as e:
        st.warning(f"Could not preload PyTorch DLL: {e}")

# 2. Ensure root directory is on sys.path so src imports work
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.config import load_config
ui_config = load_config().ui
hotels_config = load_config().sourcing.hotels


def _search_booking_destinations(query: str) -> list[tuple[str, dict]]:
    """Live Booking.com Autocomplete lookup, called by st_searchbox as the user types.

    Returns (label_shown_in_dropdown, value_passed_back_on_select) pairs. The
    selected value carries the resolved dest_id forward into state, so hotel
    sourcing never has to guess a destination from a city name again.
    """
    if not query or len(query) < 2:
        return []

    headers = {
        "x-rapidapi-key": os.getenv("Sky_Scanner_Key"),
        "x-rapidapi-host": hotels_config.host,
    }
    try:
        res = requests.get(
            hotels_config.autocomplete_url,
            headers=headers,
            params={"location": query, "language_code": hotels_config.language_code},
            timeout=hotels_config.autocomplete_timeout_seconds,
        )
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"DEBUG: Destination Autocomplete failed for '{query}': {e}")
        return []  # searchbox just shows no results; doesn't crash the form

    results = data.get("data", [])
    if not isinstance(results, list):
        return []

    # Prefer city-level matches (dest_type also includes district, airport,
    # landmark, region, country) - hotel search wants a city dest_id.
    city_results = [item for item in results if item.get("dest_type") == "city"]
    options = []
    for item in city_results or results:
        dest_id = item.get("dest_id")
        if not dest_id:
            continue
        label = item.get("label") or item.get("label1") or query
        city_name = item.get("label1") or label
        options.append((label, {"dest_id": str(dest_id), "city_name": city_name}))

    return options

# 3. Streamlit Page Config
st.set_page_config(page_title=ui_config.page_title, page_icon=ui_config.page_icon, layout=ui_config.layout)

# --- BACKGROUND IMAGE CSS ---
st.markdown("""
    <style>
    .stApp {
        background-image: linear-gradient(rgba(15, 17, 22, 0.75), rgba(15, 17, 22, 0.75)), 
                          url("https://images.unsplash.com/photo-1436491865332-7a61a109cc05?q=80&w=2000&auto=format&fit=crop");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }
    
    .main-container {
        background-color: rgba(0, 0, 0, 0.4);
        padding: 30px;
        border-radius: 15px;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# 4. Cache the LangGraph application
@st.cache_resource
def load_graph():
    from src.main import app
    return app

with st.spinner("Initializing WayMax Engine..."):
    app = load_graph()

# --- SUPPORTING DATA ---
CURRENCIES = ui_config.currencies

# --- MAIN PAGE ---
st.title(f"{ui_config.page_icon} {ui_config.page_title}")
st.caption("AI-powered travel planning and itinerary optimization")
st.write("") 

# --- CENTRAL SEARCH INTERFACE ---
st.subheader("Your Next Adventure?")

col1, col2 = st.columns(2)
with col1:
    origin_input = st.text_input("Origin", placeholder="e.g., Turin, TRN, or Italy")
with col2:
    # Live search against Booking.com's Autocomplete API - the user picks an
    # exact match, so its dest_id can be used directly by hotel sourcing
    # instead of being re-guessed from free text downstream.
    dest_selection = st_searchbox(
        _search_booking_destinations,
        placeholder="e.g., Istanbul, Turkey",
        label="Destination",
        key="destination_searchbox",
    )
    dest_input = dest_selection["city_name"] if dest_selection else None

col3, col4 = st.columns(2)
today = datetime.date.today()
with col3:
    start_date = st.date_input("From", value=None, min_value=today, format="YYYY-MM-DD")
with col4:
    min_end = start_date if start_date else today
    end_date = st.date_input("Till", value=None, min_value=min_end, format="YYYY-MM-DD")

col5, col6, col7, col8 = st.columns(4)
with col5:
    currency_input = st.selectbox("Currency", options=CURRENCIES, index=None, placeholder="Choose...")
with col6:
    currency_symbol = currency_input.split(" ")[0] if currency_input else ""
    budget_label = f"Budget ({currency_symbol})" if currency_symbol else "Budget"
    budget_input = st.number_input(
        budget_label,
        min_value=ui_config.budget.min,
        max_value=ui_config.budget.max,
        value=ui_config.budget.default,
        step=ui_config.budget.step,
    )
with col7:
    travelers_input = st.number_input(
        "Travelers",
        min_value=ui_config.travelers.min,
        max_value=ui_config.travelers.max,
        value=ui_config.travelers.default,
        step=ui_config.travelers.step,
    )
with col8:
    st.write("Min Hotel Stars")
    raw_stars = st.feedback("stars", key="min_stars")
    stars_input = (raw_stars + 1) if raw_stars is not None else ui_config.min_hotel_stars_default

st.write("")

# --- FLIGHT PREFERENCES ---
st.write("**Flight Preferences**")
col_f1, col_f2 = st.columns(2)
with col_f1:
    direct_flights_input = st.checkbox("✈️ Direct Flights Only (No Layovers)", value=False)
with col_f2:
    max_flight_hours = st.slider(
        "⏳ Max Flight Duration (Hours)",
        min_value=ui_config.max_flight_hours.min,
        max_value=ui_config.max_flight_hours.max,
        value=ui_config.max_flight_hours.default,
    )

submit_button = st.button("Plan My Trip", use_container_width=True, type="primary")
st.divider()

# Initialize session state for chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

if submit_button:
    # --- VALIDATION CHECK ---
    if not origin_input or not dest_selection or not currency_input or not start_date or not end_date:
        st.error("⚠️ Please fill out all required fields, including selecting a Destination from the search results, before planning your trip.")
    else:
        dates_str = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d')}"
        currency_code = currency_input.split(" ")[1]
        
        star_pref_str = f" with at least a {stars_input}-star hotel" if stars_input > 0 else ""
        prompt = (
            f"I want to book a trip from {origin_input} to {dest_input} "
            f"from {dates_str} for {travelers_input} people with a budget of "
            f"{budget_input} {currency_code}{star_pref_str}."
        )
        
        st.session_state["messages"].append({"role": "user", "content": prompt})
        
        formatted_chat_history = []
        for msg in st.session_state["messages"]:
            if msg["role"] == "user":
                formatted_chat_history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                formatted_chat_history.append(AIMessage(content=msg["content"]))

        # Passes the integer directly to the LangGraph state
        min_stars = stars_input if stars_input > 0 else None

        initial_state = {
            "chat_history": formatted_chat_history,
            "origin": None,
            "destination": None,
            "destination_city": dest_selection["city_name"],
            "hotel_dest_id": dest_selection["dest_id"],
            "max_budget": None,
            "travel_dates": None,
            "travelers": travelers_input,
            "min_hotel_stars": min_stars,
            "direct_only": direct_flights_input,
            "max_flight_hours": max_flight_hours, # <-- Added slider value
            "raw_flight_data": [],
            "raw_hotel_data": [],
            "final_itinerary": None,
            "next_node": ""
        }

        with st.status("🤖 WayMax Agents Executing...", expanded=True) as status:
            st.write("⏳ Supervisor parsing constraints and dates...")
            st.write("⏳ Sourcing Node retrieving live APIs (Flight & Hotel)...")
            st.write("⏳ Optimizer crunching combinations against budget...")
            
            output = app.invoke(initial_state)
            
            status.update(label="✅ Optimization Complete!", state="complete", expanded=False)

        final_itinerary = output.get("final_itinerary")

        if final_itinerary:
            flight = final_itinerary.get("flight", {})
            hotel = final_itinerary.get("hotel", {})
            
            # --- EXPANDED DATA EXTRACTION ---
            airline = flight.get("name", "Unknown Carrier")
            flight_num = flight.get("flight_number", "TBD")
            dep_time = flight.get("departure_time", "TBD")
            arr_time = flight.get("arrival_time", "TBD")
            cabin_class = flight.get("cabin_class", "Economy")
            
            hotel_name = hotel.get("name", "Unknown Hotel")
            hotel_rate = hotel.get("price_per_night", "N/A")
            hotel_address = hotel.get("address", "Location details unavailable")
            hotel_rating = hotel.get("rating", "N/A")
            room_type = hotel.get("room_type", "Standard Room")
            
            duration = final_itinerary.get("nights_staying", "N/A")
            total_price = final_itinerary.get("total_price", 0.0)
            flight_cost = final_itinerary.get("flight_cost", 0.0)
            hotel_total_cost = final_itinerary.get("hotel_total_cost", 0.0)
            within_budget = final_itinerary.get("within_budget", False)

            # --- INTERACTIVE TABS ---
            tab_overview, tab_flight, tab_hotel = st.tabs(["Itinerary Overview", "Flight Details", "Hotel Details"])
            
            with tab_overview:
                if within_budget:
                    st.success("✅ **Optimized Plan & Within Budget**")
                else:
                    st.warning("⚠️ **Exceeds Budget Constraint**")
                
                col_ov1, col_ov2, col_ov3 = st.columns(3)
                col_ov1.metric("TOTAL COST", f"{currency_symbol}{total_price:,.2f}")
                col_ov2.metric("FLIGHT COST", f"{currency_symbol}{flight_cost:,.2f}")
                col_ov3.metric("HOTEL COST", f"{currency_symbol}{hotel_total_cost:,.2f}")

            with tab_flight:
                st.subheader("🛫 Outbound Flight")
                st.write(f"**Carrier:** {airline} | **Flight No:** {flight_num}")
                st.write(f"**Class:** {cabin_class}")
                
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    st.write("**Departure:**")
                    st.write(f"📍 {origin_input}")
                    st.write(f"🕒 {dep_time}")
                with f_col2:
                    st.write("**Arrival:**")
                    st.write(f"📍 {dest_input}")
                    st.write(f"🕒 {arr_time}")
                    
                st.divider()
                st.write(f"**Total Flight Cost ({travelers_input} Travelers):** {currency_symbol}{flight_cost:,.2f}")

            with tab_hotel:
                st.subheader("🏨 Accommodation")
                
                star_display = f"{'⭐' * int(hotel_rating)}" if isinstance(hotel_rating, (int, float)) and hotel_rating > 0 else "(Unrated)"
                
                st.write(f"**Hotel:** {hotel_name} {star_display}")
                st.write(f"**Address:** 🗺️ {hotel_address}")
                st.write(f"**Room Type:** 🛏️ {room_type}")
                
                h_col1, h_col2 = st.columns(2)
                with h_col1:
                    st.write(f"**Check-in:** {start_date}")
                    st.write(f"**Duration:** {duration} nights")
                with h_col2:
                    st.write(f"**Check-out:** {end_date}")
                    st.write(f"**Rate:** {currency_symbol}{hotel_rate:,.2f} / night")
                    
                st.divider()
                st.write(f"**Total Hotel Cost:** {currency_symbol}{hotel_total_cost:,.2f}")

        else:
            # Check if the failure was specifically due to no flights being found
            raw_flights = output.get("raw_flight_data", [])
            raw_hotels = output.get("raw_hotel_data", [])
            
            if not raw_flights and direct_flights_input:
                st.error("**No Direct Flights Found:** We couldn't find any direct flights for this route on these dates. Try unchecking 'Direct Flights Only' or searching for a different route.")
            elif not raw_flights:
                st.error("**No Flights Found:** We couldn't find any available flights for this route. Please check your origin/destination codes and dates or increase your Max Flight Duration.")
            elif not raw_hotels:
                st.error("**No Hotels Found:** We couldn't find any hotels matching your star rating constraint. Try lowering your minimum stars.")
            else:
                st.error("**Budget Exceeded or No Valid Plan:** We found flights and hotels, but couldn't create a combination that fits your constraints. Try increasing your budget.")