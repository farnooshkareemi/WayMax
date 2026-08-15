import sys
import os
import platform
import json
import datetime
import streamlit as st
from streamlit_star_rating import st_star_rating
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

# 3. Streamlit Page Config
st.set_page_config(page_title="WayMax", page_icon="✈️", layout="centered") 

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
CURRENCIES = [
    "€ EUR", "$ USD", "£ GBP", "¥ JPY", "C$ CAD", 
    "A$ AUD", "CHF CHF", "¥ CNY", "₹ INR", "R$ BRL", "د.إ AED"
]

# --- MAIN PAGE ---
st.title("✈️ WayMax")
st.caption("AI-powered travel planning and itinerary optimization")
st.write("") 

# --- CENTRAL SEARCH INTERFACE ---
st.subheader("Your Next Adventure?")

col1, col2 = st.columns(2)
with col1:
    origin_input = st.text_input("Origin", placeholder="e.g., Turin, TRN, or Italy")
with col2:
    dest_input = st.text_input("Destination", placeholder="e.g., Istanbul, IST, or Turkey")

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
    budget_input = st.number_input(budget_label, min_value=100, max_value=20000, value=1000, step=50)
with col7:
    travelers_input = st.number_input("Travelers", min_value=1, max_value=10, value=1, step=1)
with col8:
    st.write("Min Hotel Stars")
    raw_stars = st.feedback("stars", key="min_stars")
    stars_input = (raw_stars + 1) if raw_stars is not None else 3

st.write("")

# --- FLIGHT PREFERENCES ---
st.write("**Flight Preferences**")
col_f1, col_f2 = st.columns(2)
with col_f1:
    direct_flights_input = st.checkbox("✈️ Direct Flights Only (No Layovers)", value=False)
with col_f2:
    max_flight_hours = st.slider("⏳ Max Flight Duration (Hours)", min_value=1, max_value=30, value=10)

submit_button = st.button("Plan My Trip", use_container_width=True, type="primary")
st.divider()

# Initialize session state for chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

if submit_button:
    # --- VALIDATION CHECK ---
    if not origin_input or not dest_input or not currency_input or not start_date or not end_date:
        st.error("⚠️ Please fill out all required fields (Origin, Destination, Dates, and Currency) before planning your trip.")
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
            "destination_city": None,
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