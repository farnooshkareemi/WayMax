from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from operator import add

class WaymaxState(TypedDict):
    """State schema for the Waymax travel optimizer multi-agent system."""
    chat_history: Annotated[List[BaseMessage], add]
    origin: Optional[str]             # <-- Added this so flights work perfectly!
    destination: Optional[str]
    destination_city: Optional[str]   # <-- Added this so hotels work perfectly!
    max_budget: Optional[float]
    travel_dates: Optional[str]
    travelers: Optional[int]          # <-- NEW: Added this to track the number of people!
    min_hotel_stars: Optional[int]    # <-- NEW: Added this to enforce the UI star rating filter!
    direct_only: Optional[bool]
    max_flight_hours: Optional[int]
    raw_flight_data: List[dict]
    raw_hotel_data: List[dict]
    final_itinerary: Optional[dict]
    next_node: str