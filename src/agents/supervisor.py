import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from src.state import WaymaxState
from src.config import load_config
from src.metrics import get_current_run, node_timer
import datetime

load_dotenv()

logger = logging.getLogger(__name__)

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

llm_config = load_config().llm
llm = ChatGoogleGenerativeAI(model=llm_config.model)
structured_llm = llm.with_structured_output(TravelConstraints, include_raw=True)

def supervisor_node(state: WaymaxState) -> Dict[str, Any]:
    logger.info("Starting supervisor node")

    run_metrics = get_current_run()
    timer = node_timer(run_metrics, "supervisor") if run_metrics else None
    if timer:
        timer.__enter__()

    chat_history = state.get("chat_history", [])

    if not chat_history:
        if timer:
            timer.__exit__(None, None, None)
        return {"origin": None, "destination": None, "destination_city": None, "max_budget": None, "travel_dates": None, "travelers": None, "next_node": "end"}

    try:
        result = structured_llm.invoke(chat_history)
        response = result["parsed"]
        raw_message = result.get("raw")

        if run_metrics and raw_message is not None:
            usage = getattr(raw_message, "usage_metadata", None) or {}
            run_metrics.add_llm_usage(
                model=llm_config.model,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                total_tokens=usage.get("total_tokens"),
            )

        origin = response.origin
        destination = response.destination
        destination_city = response.destination_city
        max_budget = response.max_budget
        travel_dates = response.travel_dates
        travelers = response.travelers
        logger.debug(
            "LLM extracted -> Orig: %s, Dest: %s, City: %s, Dates: %s, Travelers: %s",
            origin, destination, destination_city, travel_dates, travelers,
        )
    except Exception:
        logger.warning("Error during LLM extraction", exc_info=True)
        origin, destination, destination_city, max_budget, travel_dates, travelers = None, None, None, None, None, None

    if destination is not None:
        next_node = "sourcing"
    else:
        next_node = "end"

    if timer:
        timer.__exit__(None, None, None)

    return {
        "origin": origin,
        "destination": destination,
        "destination_city": destination_city,
        "max_budget": max_budget,
        "travel_dates": travel_dates,
        "travelers": travelers,
        "next_node": next_node,
    }