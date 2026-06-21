from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from operator import add

class WaymaxState(TypedDict):
    """State schema for the Waymax travel optimizer multi-agent system."""
    chat_history: Annotated[List[BaseMessage], add]
    destination: Optional[str]
    max_budget: Optional[float]
    travel_dates: Optional[str]
    raw_flight_data: List[dict]
    raw_hotel_data: List[dict]
    final_itinerary: Optional[dict]
    next_node: str
