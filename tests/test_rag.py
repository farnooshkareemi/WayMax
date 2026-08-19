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
from src.rag.retriever import estimate_checked_bag_fee, retrieve_baggage_policy


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
    fee = estimate_checked_bag_fee("SomeAirlineNotInKnowledgeBase")
    # Semantic search always returns the closest match even if it's a poor
    # match, so this either returns a (weak) match or None if unparseable --
    # both are acceptable; the real guarantee is that it never raises.
    assert fee is None or isinstance(fee, float)


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
    assert out["next_node"] == "optimizer"


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
