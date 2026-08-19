"""Query interface for the baggage-fees RAG knowledge base.

Given an airline name (as returned by sourcing_node's flight parsing), finds
the most relevant baggage-policy document and extracts a usable per-bag fee
estimate for the optimizer to add to the flight's total cost.
"""

import re
from typing import Optional, TypedDict

from src.config import load_config
from src.rag.knowledge_base import build_baggage_collection, get_chroma_client


class BaggagePolicyMatch(TypedDict):
    airline: str
    text: str
    source_url: str
    distance: float


_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        _collection = build_baggage_collection(get_chroma_client())
    return _collection


def retrieve_baggage_policy(airline_name: str) -> Optional[BaggagePolicyMatch]:
    """Retrieve the closest-matching baggage policy document for a given
    airline name. Returns None if the collection is empty, airline_name is
    falsy, or the closest match is farther than config.rag.max_match_distance
    away — callers should treat a None result as "no baggage cost data
    available", not as an error.

    Vector similarity search always returns the closest match in the
    collection, however distant - without a threshold, an airline with no
    real policy in the (currently 3-airline) knowledge base would silently
    be assigned an unrelated airline's fees (e.g. "Turkish Airlines" matching
    to Ryanair) instead of correctly reporting no match.
    """
    if not airline_name:
        return None

    config = load_config().rag
    collection = _get_collection()
    if collection.count() == 0:
        return None

    result = collection.query(query_texts=[airline_name], n_results=config.top_k)
    if not result["ids"] or not result["ids"][0]:
        return None

    distance = result["distances"][0][0]
    if distance > config.max_match_distance:
        return None

    return BaggagePolicyMatch(
        airline=result["metadatas"][0][0]["airline"],
        text=result["documents"][0][0],
        source_url=result["metadatas"][0][0]["source_url"],
        distance=distance,
    )


class BaggageFeeEstimate(TypedDict):
    fee: float
    source_url: str
    source_text: str


def estimate_checked_bag_fee_detailed(airline_name: str) -> Optional[BaggageFeeEstimate]:
    """Return a rough single-checked-bag fee estimate (EUR) for the given
    airline, parsed from the retrieved policy text's price range, along with
    the source document it was drawn from. Returns None if no policy text or
    no parseable price range was found.

    This is intentionally a rough estimate for budget-impact purposes, not a
    precise fare lookup -- real per-bag pricing depends on route, season and
    booking channel, as the source documents themselves state. The source_url
    is what lets a user verify or challenge that estimate themselves rather
    than trust an unlabeled number.
    """
    match = retrieve_baggage_policy(airline_name)
    if match is None:
        return None

    price_range = re.search(r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)', match["text"])
    if not price_range:
        return None

    low, high = float(price_range.group(1)), float(price_range.group(2))
    fee = round((low + high) / 2, 2)
    return BaggageFeeEstimate(fee=fee, source_url=match["source_url"], source_text=match["text"])


def estimate_checked_bag_fee(airline_name: str) -> Optional[float]:
    """Backwards-compatible wrapper returning just the fee (see
    estimate_checked_bag_fee_detailed for the source_url/source_text too)."""
    detailed = estimate_checked_bag_fee_detailed(airline_name)
    return detailed["fee"] if detailed else None
