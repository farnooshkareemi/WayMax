from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from src.state import WaymaxState
import datetime

load_dotenv()

current_year = datetime.datetime.now().year
current_date = datetime.datetime.now().strftime("%Y-%m-%d")

class TravelConstraints(BaseModel):
    """Extracted travel constraints from user chat history."""
    origin: Optional[str] = Field(
        None, 
        description="The 3-letter IATA SPECIFIC AIRPORT code for the origin city. CRITICAL: Never use generic metropolitan codes (e.g., use 'MXP' or 'LIN' for Milan, NEVER 'MIL'. Use 'JFK' for New York, NEVER 'NYC'). Always return the primary airport as uppercase."
    )
    destination: Optional[str] = Field(
        None, 
        description="The 3-letter IATA SPECIFIC AIRPORT code for the destination city. CRITICAL: Never use generic metropolitan codes (e.g., use 'IST' for Istanbul, NEVER 'ISL'. Use 'LHR' for London, NEVER 'LON'). Always return the primary airport as uppercase."
    )
    destination_city: Optional[str] = Field(
        None, 
        description="The full, properly capitalized name of the destination city (e.g., 'New York', 'Barcelona')."
    )
    max_budget: Optional[float] = Field(
        None, description="The maximum budget constraint for the trip as a float"
    )
    travel_dates: Optional[str] = Field(
        None, description=f"The dates for the trip (e.g., '{current_year}-08-01 to {current_year}-08-08'). CRITICAL: Today is {current_date}. You MUST use {current_year} or future years for all dates."
    )
    travelers: Optional[int] = Field(
        1, description="The number of people traveling. Defaults to 1 if not explicitly stated."
    )

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
structured_llm = llm.with_structured_output(TravelConstraints)

def supervisor_node(state: WaymaxState) -> Dict[str, Any]:
    print("--- STARTING SUPERVISOR NODE ---")
    chat_history = state.get("chat_history", [])

    if not chat_history:
        return {"origin": None, "destination": None, "destination_city": None, "max_budget": None, "travel_dates": None, "travelers": None, "next_node": "end"}

    try:
        response = structured_llm.invoke(chat_history)
        origin = response.origin
        destination = response.destination
        destination_city = response.destination_city
        max_budget = response.max_budget
        travel_dates = response.travel_dates
        travelers = response.travelers
        print(f"DEBUG: LLM Extracted -> Orig: {origin}, Dest: {destination}, City: {destination_city}, Dates: {travel_dates}, Travelers: {travelers}")
    except Exception as e:
        print(f"DEBUG: Error during LLM extraction: {e}")
        origin, destination, destination_city, max_budget, travel_dates, travelers = None, None, None, None, None, None

    if destination is not None:
        next_node = "sourcing"
    else:
        next_node = "end"

    return {
        "origin": origin,
        "destination": destination,
        "destination_city": destination_city,
        "max_budget": max_budget,
        "travel_dates": travel_dates,
        "travelers": travelers,
        "next_node": next_node,
    }