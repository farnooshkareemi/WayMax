"""RAG node: enriches each sourced flight with an estimated checked-baggage fee.

Sits between sourcing and optimization in the graph. For each flight in
raw_flight_data, looks up the airline's baggage policy in the local Chroma
knowledge base (see src/rag/retriever.py) and attaches a rough per-bag fee
estimate -- plus the source document it came from, so a user can verify or
challenge the number rather than trust an unlabeled figure -- so the
optimizer's budget math can account for it, addressing the "hidden non-API
costs" strategy described in README.md.

If no policy is found for an airline (not yet in the knowledge base) or the
RAG layer fails for any reason, flights are passed through unmodified with a
fee estimate of 0.0 rather than blocking the pipeline -- this node degrades
gracefully like sourcing_node does for its own API calls.
"""

import logging
from typing import Dict, Any

from src.metrics import get_current_run, node_timer
from src.rag.retriever import estimate_checked_bag_fee_detailed

logger = logging.getLogger(__name__)


def rag_node(state: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("Starting RAG node")

    run_metrics = get_current_run()
    timer = node_timer(run_metrics, "rag") if run_metrics else None
    if timer:
        timer.__enter__()

    raw_flight_data = state.get("raw_flight_data", [])
    enriched_flights = []
    # sourcing_errors has no LangGraph reducer, so this node must read and
    # extend whatever sourcing_node already put there, not overwrite it -
    # otherwise a real sourcing failure would silently disappear once RAG runs.
    sourcing_errors = list(state.get("sourcing_errors", []))
    # RAG lookups fail together (e.g. torch/Chroma unavailable) or not at all -
    # log the first failure per run with a traceback, then only debug-log the
    # rest, so one root cause doesn't produce N duplicate warnings/tracebacks
    # for an N-flight result set. Only a real exception counts as a sourcing
    # error here - "no baggage policy found for this airline" is a legitimate
    # empty result (see retriever.py), not a failure.
    logged_failure = False

    for flight in raw_flight_data:
        airline = flight.get("name")
        try:
            detailed = estimate_checked_bag_fee_detailed(airline)
        except Exception as e:
            if not logged_failure:
                logger.warning("RAG lookup failed for '%s' (further failures this run logged at debug level)", airline, exc_info=True)
                sourcing_errors.append(f"Baggage fee estimate unavailable: {e}")
                logged_failure = True
            else:
                logger.debug("RAG lookup failed for '%s'", airline, exc_info=True)
            detailed = None

        enriched = dict(flight)
        enriched["baggage_fee_estimate"] = detailed["fee"] if detailed else 0.0
        enriched["baggage_fee_source_url"] = detailed["source_url"] if detailed else None
        enriched_flights.append(enriched)

        if detailed:
            logger.debug("Baggage fee estimate for %s: %s (source: %s)", airline, detailed["fee"], detailed["source_url"])
        else:
            logger.debug("No baggage policy found for '%s', assuming 0.0", airline)

    if timer:
        timer.__exit__(None, None, None)

    return {
        "raw_flight_data": enriched_flights,
        "sourcing_errors": sourcing_errors,
        "next_node": "optimizer",
    }
