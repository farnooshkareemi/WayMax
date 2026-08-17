"""Per-run engineering metrics for the WayMax pipeline.

Every invocation of the graph writes one JSON file to outputs/metrics/ capturing
run performance, LLM token usage, API call outcomes, and optimizer quality —
so future work can look back at real numbers instead of guessing what to optimize.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

METRICS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "metrics"
)


class NodeTiming(BaseModel):
    node: str
    duration_seconds: float
    success: bool


class LLMUsage(BaseModel):
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class APICallOutcome(BaseModel):
    name: str                       # e.g. "flights_search", "hotels_autocomplete", "hotels_search"
    status_code: Optional[int] = None
    ok: bool
    results_returned: Optional[int] = None
    cache_hit: Optional[bool] = None  # only meaningful for the hotel dest_id lookup: True when
                                       # hotel_dest_id was already resolved (e.g. by the UI's
                                       # search box), False when a live Autocomplete call was made


class OptimizerQuality(BaseModel):
    combinations_evaluated: int
    best_total_price: Optional[float] = None
    within_budget: Optional[bool] = None


class RunMetrics(BaseModel):
    run_id: str
    timestamp: str
    total_duration_seconds: Optional[float] = None
    success: bool = True
    node_timings: List[NodeTiming] = Field(default_factory=list)
    llm_usage: List[LLMUsage] = Field(default_factory=list)
    api_calls: List[APICallOutcome] = Field(default_factory=list)
    optimizer: Optional[OptimizerQuality] = None

    def add_node_timing(self, node: str, duration_seconds: float, success: bool = True) -> None:
        self.node_timings.append(NodeTiming(node=node, duration_seconds=duration_seconds, success=success))

    def add_llm_usage(self, model: str, input_tokens: int = None, output_tokens: int = None, total_tokens: int = None) -> None:
        self.llm_usage.append(LLMUsage(model=model, input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens))

    def add_api_call(self, name: str, ok: bool, status_code: int = None, results_returned: int = None, cache_hit: bool = None) -> None:
        self.api_calls.append(APICallOutcome(name=name, status_code=status_code, ok=ok, results_returned=results_returned, cache_hit=cache_hit))

    def set_optimizer_quality(self, combinations_evaluated: int, best_total_price: float = None, within_budget: bool = None) -> None:
        self.optimizer = OptimizerQuality(
            combinations_evaluated=combinations_evaluated,
            best_total_price=best_total_price,
            within_budget=within_budget,
        )

    def write(self) -> str:
        """Write this run's metrics to outputs/metrics/<run_id>.json and return the path."""
        os.makedirs(METRICS_DIR, exist_ok=True)
        path = os.path.join(METRICS_DIR, f"{self.run_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2)
        return path


_current_run: Optional[RunMetrics] = None


def new_run() -> RunMetrics:
    """Start a fresh RunMetrics with a timestamp-based run_id and make it the
    current run for get_current_run()/node instrumentation to attach to."""
    global _current_run
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%S%fZ")
    _current_run = RunMetrics(run_id=run_id, timestamp=now.isoformat())
    return _current_run


def get_current_run() -> Optional[RunMetrics]:
    """Return the RunMetrics started by the most recent new_run() call, or None
    if no run is in progress (e.g. a node was called standalone/in a test)."""
    return _current_run


class node_timer:
    """Context manager that records a node's wall-clock duration into a RunMetrics.

    Usage:
        with node_timer(metrics, "supervisor"):
            ... do work ...
    """

    def __init__(self, metrics: RunMetrics, node_name: str):
        self.metrics = metrics
        self.node_name = node_name
        self.start: Optional[float] = None

    def __enter__(self) -> "node_timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration = time.perf_counter() - (self.start or time.perf_counter())
        self.metrics.add_node_timing(self.node_name, duration, success=exc_type is None)
