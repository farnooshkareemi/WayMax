"""Aggregate outputs/metrics/*.json into a summary report.

Every graph invocation (via src/main.py or the Streamlit UI) writes one
RunMetrics JSON file to outputs/metrics/ (see src/metrics.py). Individually
those files are just a snapshot of a single run; this script is what turns
them into an actual evaluation: per-node latency percentiles, LLM token
usage, API call success rates per endpoint, and the fraction of runs that
landed within budget.

Usage:
    python scripts/metrics_report.py
    python scripts/metrics_report.py --metrics-dir path/to/other/dir
"""

import argparse
import glob
import json
import os
import statistics
from collections import defaultdict
from typing import Any, Dict, List

DEFAULT_METRICS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "metrics"
)


def load_runs(metrics_dir: str) -> List[Dict[str, Any]]:
    paths = sorted(glob.glob(os.path.join(metrics_dir, "*.json")))
    runs = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                runs.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"Skipping unreadable metrics file {path}: {e}")
    return runs


def _percentile(values: List[float], pct: float) -> float:
    """Nearest-rank percentile; exact for pct=50 (median) and safe for n=1."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    if pct == 50:
        return statistics.median(sorted_vals)
    # statistics.quantiles needs n>=2, which we've already ensured above.
    quantiles = statistics.quantiles(sorted_vals, n=100, method="inclusive")
    index = max(0, min(99, round(pct) - 1))
    return quantiles[index]


def summarize_node_timings(runs: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """node name -> {avg, p50, p95, count, failure_count} across all runs."""
    durations_by_node: Dict[str, List[float]] = defaultdict(list)
    failures_by_node: Dict[str, int] = defaultdict(int)

    for run in runs:
        for timing in run.get("node_timings", []):
            durations_by_node[timing["node"]].append(timing["duration_seconds"])
            if not timing.get("success", True):
                failures_by_node[timing["node"]] += 1

    summary = {}
    for node, durations in durations_by_node.items():
        summary[node] = {
            "count": len(durations),
            "avg_seconds": statistics.mean(durations),
            "p50_seconds": _percentile(durations, 50),
            "p95_seconds": _percentile(durations, 95),
            "failure_count": failures_by_node.get(node, 0),
        }
    return summary


def summarize_llm_usage(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_input = total_output = total_tokens = 0
    call_count = 0
    for run in runs:
        for usage in run.get("llm_usage", []):
            call_count += 1
            total_input += usage.get("input_tokens") or 0
            total_output += usage.get("output_tokens") or 0
            total_tokens += usage.get("total_tokens") or 0
    return {
        "call_count": call_count,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_tokens,
        "avg_tokens_per_call": (total_tokens / call_count) if call_count else 0.0,
    }


def summarize_api_calls(runs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """API call name -> {total, ok_count, failure_rate, cache_hit_rate}."""
    calls_by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for run in runs:
        for call in run.get("api_calls", []):
            calls_by_name[call["name"]].append(call)

    summary = {}
    for name, calls in calls_by_name.items():
        ok_count = sum(1 for c in calls if c.get("ok"))
        cache_hits = [c for c in calls if c.get("cache_hit") is not None]
        cache_hit_count = sum(1 for c in cache_hits if c["cache_hit"])
        summary[name] = {
            "total": len(calls),
            "ok_count": ok_count,
            "failure_rate": 1 - (ok_count / len(calls)) if calls else 0.0,
            "cache_hit_rate": (cache_hit_count / len(cache_hits)) if cache_hits else None,
        }
    return summary


def summarize_optimizer(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    # within_budget is null when the optimizer never produced any itinerary
    # at all (e.g. flights or hotels came back empty) - that's a distinct
    # outcome from "produced an itinerary but it exceeded budget"
    # (within_budget: false), so it's excluded from the rate rather than
    # silently counted as a budget failure.
    within_budget_count = 0
    decided_count = 0
    evaluated_count = 0
    combinations = []
    for run in runs:
        optimizer = run.get("optimizer")
        if not optimizer:
            continue
        evaluated_count += 1
        combinations.append(optimizer.get("combinations_evaluated", 0))
        within_budget = optimizer.get("within_budget")
        if within_budget is not None:
            decided_count += 1
            if within_budget:
                within_budget_count += 1
    return {
        "runs_with_optimizer_result": evaluated_count,
        "runs_with_no_itinerary": evaluated_count - decided_count,
        "within_budget_rate": (within_budget_count / decided_count) if decided_count else None,
        "avg_combinations_evaluated": statistics.mean(combinations) if combinations else 0.0,
    }


def print_report(runs: List[Dict[str, Any]]) -> None:
    if not runs:
        print("No metrics files found. Run `python -m src.main` or the Streamlit UI at least once to generate some.")
        return

    success_count = sum(1 for r in runs if r.get("success"))
    total_durations = [r["total_duration_seconds"] for r in runs if r.get("total_duration_seconds") is not None]

    print(f"WayMax Metrics Report - {len(runs)} run(s)\n")

    print(f"Overall success rate: {success_count}/{len(runs)} ({success_count / len(runs):.0%})")
    if total_durations:
        print(
            f"Total pipeline duration - avg: {statistics.mean(total_durations):.2f}s, "
            f"p50: {_percentile(total_durations, 50):.2f}s, "
            f"p95: {_percentile(total_durations, 95):.2f}s"
        )

    print("\nPer-node latency:")
    node_summary = summarize_node_timings(runs)
    for node, stats in sorted(node_summary.items()):
        failure_note = f", {stats['failure_count']} failure(s)" if stats["failure_count"] else ""
        print(
            f"  {node:<14} avg {stats['avg_seconds']:6.2f}s  "
            f"p50 {stats['p50_seconds']:6.2f}s  "
            f"p95 {stats['p95_seconds']:6.2f}s  "
            f"(n={stats['count']}{failure_note})"
        )

    print("\nLLM usage:")
    llm_summary = summarize_llm_usage(runs)
    print(
        f"  {llm_summary['call_count']} call(s), "
        f"{llm_summary['total_tokens']} total tokens "
        f"({llm_summary['total_input_tokens']} in / {llm_summary['total_output_tokens']} out), "
        f"avg {llm_summary['avg_tokens_per_call']:.0f} tokens/call"
    )

    print("\nAPI calls:")
    api_summary = summarize_api_calls(runs)
    for name, stats in sorted(api_summary.items()):
        cache_note = f", cache hit rate {stats['cache_hit_rate']:.0%}" if stats["cache_hit_rate"] is not None else ""
        print(
            f"  {name:<20} {stats['ok_count']}/{stats['total']} ok  "
            f"(failure rate {stats['failure_rate']:.0%}{cache_note})"
        )

    print("\nOptimizer:")
    opt_summary = summarize_optimizer(runs)
    if opt_summary["runs_with_optimizer_result"]:
        budget_rate = opt_summary["within_budget_rate"]
        budget_str = f"{budget_rate:.0%}" if budget_rate is not None else "N/A (no run produced an itinerary)"
        print(f"  Within-budget rate: {budget_str}")
        if opt_summary["runs_with_no_itinerary"]:
            print(f"  Runs with no itinerary at all (empty flights/hotels): {opt_summary['runs_with_no_itinerary']}")
        print(f"  Avg combinations evaluated: {opt_summary['avg_combinations_evaluated']:.0f}")
    else:
        print("  No runs produced an optimizer result.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics-dir",
        default=DEFAULT_METRICS_DIR,
        help="Directory containing RunMetrics JSON files (default: outputs/metrics/)",
    )
    args = parser.parse_args()

    runs = load_runs(args.metrics_dir)
    print_report(runs)


if __name__ == "__main__":
    main()
