"""Tests for scripts/metrics_report.py's aggregation logic.

Uses small synthetic RunMetrics-shaped dicts rather than real files from
outputs/metrics/, so these tests are deterministic and don't depend on
whatever runs happen to exist locally.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from metrics_report import (
    summarize_node_timings,
    summarize_llm_usage,
    summarize_api_calls,
    summarize_optimizer,
    load_runs,
)


def _run(node_timings=None, llm_usage=None, api_calls=None, optimizer=None):
    return {
        "run_id": "test",
        "timestamp": "2026-01-01T00:00:00Z",
        "total_duration_seconds": 1.0,
        "success": True,
        "node_timings": node_timings or [],
        "llm_usage": llm_usage or [],
        "api_calls": api_calls or [],
        "optimizer": optimizer,
    }


def test_summarize_node_timings_averages_across_runs():
    runs = [
        _run(node_timings=[{"node": "sourcing", "duration_seconds": 2.0, "success": True}]),
        _run(node_timings=[{"node": "sourcing", "duration_seconds": 4.0, "success": True}]),
    ]
    summary = summarize_node_timings(runs)
    assert summary["sourcing"]["count"] == 2
    assert summary["sourcing"]["avg_seconds"] == 3.0
    assert summary["sourcing"]["failure_count"] == 0


def test_summarize_node_timings_counts_failures():
    runs = [_run(node_timings=[{"node": "rag", "duration_seconds": 1.0, "success": False}])]
    summary = summarize_node_timings(runs)
    assert summary["rag"]["failure_count"] == 1


def test_summarize_llm_usage_sums_tokens():
    runs = [
        _run(llm_usage=[{"model": "gemini-2.5-flash", "input_tokens": 10, "output_tokens": 20, "total_tokens": 30}]),
        _run(llm_usage=[{"model": "gemini-2.5-flash", "input_tokens": 5, "output_tokens": 15, "total_tokens": 20}]),
    ]
    summary = summarize_llm_usage(runs)
    assert summary["call_count"] == 2
    assert summary["total_tokens"] == 50
    assert summary["avg_tokens_per_call"] == 25.0


def test_summarize_api_calls_computes_failure_rate():
    runs = [
        _run(api_calls=[{"name": "flights_search", "ok": True, "cache_hit": None}]),
        _run(api_calls=[{"name": "flights_search", "ok": False, "cache_hit": None}]),
    ]
    summary = summarize_api_calls(runs)
    assert summary["flights_search"]["total"] == 2
    assert summary["flights_search"]["failure_rate"] == 0.5


def test_summarize_api_calls_computes_cache_hit_rate_only_when_meaningful():
    runs = [
        _run(api_calls=[{"name": "hotels_dest_lookup", "ok": True, "cache_hit": True}]),
        _run(api_calls=[{"name": "hotels_dest_lookup", "ok": True, "cache_hit": False}]),
        # flights_search never sets cache_hit - should not report a rate at all.
        _run(api_calls=[{"name": "flights_search", "ok": True, "cache_hit": None}]),
    ]
    summary = summarize_api_calls(runs)
    assert summary["hotels_dest_lookup"]["cache_hit_rate"] == 0.5
    assert summary["flights_search"]["cache_hit_rate"] is None


def test_summarize_optimizer_within_budget_rate_excludes_null_results():
    """within_budget=null (no itinerary was ever produced) must not be counted
    the same as within_budget=false (an itinerary was produced but over budget)."""
    runs = [
        _run(optimizer={"combinations_evaluated": 10, "within_budget": True}),
        _run(optimizer={"combinations_evaluated": 5, "within_budget": False}),
        _run(optimizer={"combinations_evaluated": 0, "within_budget": None}),
    ]
    summary = summarize_optimizer(runs)
    assert summary["runs_with_optimizer_result"] == 3
    assert summary["runs_with_no_itinerary"] == 1
    # 1 True out of 2 decided (True/False) results = 50%, the null one excluded.
    assert summary["within_budget_rate"] == 0.5


def test_summarize_optimizer_handles_no_runs_with_optimizer_result():
    summary = summarize_optimizer([_run(optimizer=None)])
    assert summary["runs_with_optimizer_result"] == 0
    assert summary["within_budget_rate"] is None


def test_load_runs_skips_unreadable_files(tmp_path):
    good_path = tmp_path / "good.json"
    good_path.write_text('{"run_id": "good"}', encoding="utf-8")
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not valid json", encoding="utf-8")

    runs = load_runs(str(tmp_path))
    assert len(runs) == 1
    assert runs[0]["run_id"] == "good"


def test_load_runs_empty_directory_returns_empty_list(tmp_path):
    assert load_runs(str(tmp_path)) == []
