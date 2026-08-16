"""RAG node: enriches each sourced flight with an estimated checked-baggage fee.

Sits between sourcing and optimization in the graph. For each flight in
raw_flight_data, looks up the airline's baggage policy in the local Chroma
knowledge base (see src/rag/retriever.py) and attaches a rough per-bag fee
estimate so the optimizer's budget math can account for it -- addressing the
"hidden non-API costs" strategy described in README.md.

If no policy is found for an airline (not yet in the knowledge base) or the
RAG layer fails for any reason, flights are passed through unmodified with a
fee estimate of 0.0 rather than blocking the pipeline -- this node degrades
gracefully like sourcing_node does for its own API calls.
"""

from typing import Dict, Any

from src.metrics import get_current_run, node_timer
from src.rag.retriever import estimate_checked_bag_fee


def rag_node(state: Dict[str, Any]) -> Dict[str, Any]:
    print("--- STARTING RAG NODE ---")

    run_metrics = get_current_run()
    timer = node_timer(run_metrics, "rag") if run_metrics else None
    if timer:
        timer.__enter__()

    raw_flight_data = state.get("raw_flight_data", [])
    enriched_flights = []

    for flight in raw_flight_data:
        airline = flight.get("name")
        try:
            fee = estimate_checked_bag_fee(airline)
        except Exception as e:
            print(f"DEBUG: RAG lookup failed for '{airline}': {e}")
            fee = None

        enriched = dict(flight)
        enriched["baggage_fee_estimate"] = fee if fee is not None else 0.0
        enriched_flights.append(enriched)

        if fee is not None:
            print(f"DEBUG: Baggage fee estimate for {airline}: {fee}")
        else:
            print(f"DEBUG: No baggage policy found for '{airline}', assuming 0.0")

    if timer:
        timer.__exit__(None, None, None)

    return {
        "raw_flight_data": enriched_flights,
        "next_node": "optimizer",
    }
