from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
from operator import add

class WaymaxState(TypedDict):
    """State schema for the Waymax travel optimizer multi-agent system."""
    chat_history: Annotated[List[BaseMessage], add]
    origin: Optional[str]             # <-- Added this so flights work perfectly!
    destination: Optional[str]
    destination_city: Optional[str]   # <-- Added this so hotels work perfectly!
    hotel_dest_id: Optional[str]      # <-- Booking.com dest_id, resolved once by the UI's live search box
    max_budget: Optional[float]
    travel_dates: Optional[str]
    travelers: Optional[int]          # <-- NEW: Added this to track the number of people!
    min_hotel_stars: Optional[int]    # <-- NEW: Added this to enforce the UI star rating filter!
    direct_only: Optional[bool]
    max_flight_hours: Optional[int]
    raw_flight_data: List[dict]  # each dict gains "baggage_fee_estimate" after the rag node runs
    raw_hotel_data: List[dict]
    sourcing_errors: List[str]   # human-readable notes when a sourcing/RAG API call actually
                                  # failed, vs. a search that genuinely returned zero results -
                                  # lets the UI distinguish "no flights exist" from "couldn't reach
                                  # the provider" instead of showing the same empty-results message
    final_itinerary: Optional[dict]
    next_node: str