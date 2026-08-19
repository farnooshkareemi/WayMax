"""Tests for the RAG layer (src/rag and src/agents/rag.py).

These tests build a real (tiny) Chroma collection with the real local
sentence-transformers embedding model, in an isolated temp directory per test
run. No network calls are made once the embedding model is cached locally by
sentence-transformers on first use (a one-time download, not part of the
per-test-run cost) -- this is the "least number of requests" tradeoff versus
mocking, chosen because a mocked embedding function can't validate that
semantic retrieval actually works.

NOTE: torch (a sentence-transformers dependency) currently fails to load on
some Windows setups with "WinError 1114" until the Microsoft Visual C++
Redistributable (x64) is installed/updated: https://aka.ms/vs/17/release/vc_redist.x64.exe
pytest.importorskip below skips this whole module cleanly if torch can't
import, rather than crashing the test run -- rag_node itself already degrades
gracefully (baggage_fee_estimate defaults to 0.0) when this happens, so the
rest of the pipeline and test suite are unaffected either way.
"""

import pytest

# torch raises OSError (not ImportError) on some Windows setups until the VC++
# Redistributable is installed, so pytest.importorskip's usual ImportError
# catch doesn't apply -- catch broadly and skip the whole module instead of
# letting pytest collection crash.
try:
    import torch  # noqa: F401
    import chromadb  # noqa: F401
except Exception as e:
    pytest.skip(
        f"torch/chromadb unavailable ({e}); see module docstring for the VC++ Redistributable fix",
        allow_module_level=True,
    )

from src.agents.rag import rag_node
from src.metrics import new_run
from src.rag import knowledge_base, retriever
from src.rag.knowledge_base import build_baggage_collection
from src.rag.retriever import estimate_checked_bag_fee, estimate_checked_bag_fee_detailed, retrieve_baggage_policy


@pytest.fixture
def temp_collection(tmp_path, monkeypatch):
    """Build the baggage-fees collection in a throwaway temp directory so
    tests never touch (or depend on) the repo's real persisted store."""
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    collection = build_baggage_collection(client)

    # Point the retriever's module-level cache at this test collection instead
    # of building/opening the real persisted one.
    monkeypatch.setattr(retriever, "_collection", collection)
    yield collection
    monkeypatch.setattr(retriever, "_collection", None)


def test_collection_contains_all_seed_documents(temp_collection):
    assert temp_collection.count() == 3  # Ryanair, EasyJet, Wizz Air


def test_retrieve_finds_exact_airline_match(temp_collection):
    match = retrieve_baggage_policy("Ryanair")
    assert match is not None
    assert match["airline"] == "Ryanair"
    assert "source_url" in match


def test_retrieve_returns_none_for_empty_airline(temp_collection):
    assert retrieve_baggage_policy("") is None
    assert retrieve_baggage_policy(None) is None


def test_estimate_checked_bag_fee_returns_a_plausible_number(temp_collection):
    fee = estimate_checked_bag_fee("Ryanair")
    assert fee is not None
    assert 0 < fee < 200  # sanity bound, not an exact pinned value since source ranges may be re-sourced later


def test_estimate_checked_bag_fee_unknown_airline_returns_none(temp_collection):
    # Vector search would otherwise always return the closest of the 3
    # knowledge-base airlines regardless of how distant the match actually
    # is (this used to silently assign e.g. Turkish Airlines Ryanair's fees) -
    # config.rag.max_match_distance rejects matches this far away.
    fee = estimate_checked_bag_fee("Turkish Airlines")
    assert fee is None


def test_retrieve_baggage_policy_rejects_distant_matches(temp_collection):
    """An airline genuinely unrelated to any of the 3 in the knowledge base
    must return None, not the nearest (but wrong) airline's policy."""
    assert retrieve_baggage_policy("Turkish Airlines") is None
    assert retrieve_baggage_policy("Emirates") is None


def test_estimate_checked_bag_fee_detailed_includes_source(temp_collection):
    detailed = estimate_checked_bag_fee_detailed("Ryanair")
    assert detailed is not None
    assert 0 < detailed["fee"] < 200
    assert detailed["source_url"].startswith("http")
    assert "Ryanair" in detailed["source_text"]


def test_estimate_checked_bag_fee_matches_detailed_fee(temp_collection):
    """The simple wrapper must return exactly the same fee as the detailed
    version, not a separately-computed value."""
    fee = estimate_checked_bag_fee("Ryanair")
    detailed = estimate_checked_bag_fee_detailed("Ryanair")
    assert fee == detailed["fee"]


def test_rag_node_enriches_flights_with_baggage_estimate(temp_collection):
    state = {
        "raw_flight_data": [
            {"name": "Ryanair", "price": 100.0},
            {"name": "EasyJet", "price": 120.0},
        ]
    }
    out = rag_node(state)
    assert len(out["raw_flight_data"]) == 2
    for flight in out["raw_flight_data"]:
        assert "baggage_fee_estimate" in flight
        assert isinstance(flight["baggage_fee_estimate"], float)
        # A known airline in the knowledge base should carry its source URL
        # forward too, so the UI can show where the estimate came from.
        assert flight["baggage_fee_source_url"] is not None
        assert flight["baggage_fee_source_url"].startswith("http")
    assert out["next_node"] == "optimizer"


def test_rag_node_sets_source_url_to_none_only_when_estimate_is_zero(temp_collection):
    """baggage_fee_source_url must be None exactly when baggage_fee_estimate
    is the 0.0 fallback - never a source URL paired with a 0.0 fee, and never
    a nonzero fee with no source to back it."""
    out = rag_node({"raw_flight_data": [{"name": "Ryanair", "price": 50.0}]})
    flight = out["raw_flight_data"][0]
    if flight["baggage_fee_estimate"] == 0.0:
        assert flight["baggage_fee_source_url"] is None
    else:
        assert flight["baggage_fee_source_url"] is not None


def test_rag_node_handles_empty_flight_list(temp_collection):
    out = rag_node({"raw_flight_data": []})
    assert out["raw_flight_data"] == []
    assert out["next_node"] == "optimizer"


def test_rag_node_preserves_sourcing_errors_from_earlier_in_the_run(temp_collection):
    """sourcing_errors has no LangGraph reducer, so rag_node must read and
    extend the incoming list rather than silently overwrite it - otherwise a
    real sourcing_node failure earlier in the same run would disappear by the
    time the UI reads final state."""
    out = rag_node({
        "raw_flight_data": [{"name": "Ryanair", "price": 100.0}],
        "sourcing_errors": ["Flight search failed: simulated"],
    })
    assert "Flight search failed: simulated" in out["sourcing_errors"]


def test_rag_node_defaults_sourcing_errors_to_empty_list(temp_collection):
    out = rag_node({"raw_flight_data": []})
    assert out["sourcing_errors"] == []


def test_rag_node_records_metrics_when_run_is_active(temp_collection):
    metrics = new_run()
    rag_node({"raw_flight_data": [{"name": "Ryanair", "price": 100.0}]})
    assert len(metrics.node_timings) == 1
    assert metrics.node_timings[0].node == "rag"
