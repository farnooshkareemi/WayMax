"""Tests for src.agents.supervisor.supervisor_node.

The Gemini structured-output call (structured_llm.invoke) is mocked at the
module level — no real LLM calls or API keys required.
"""

from unittest.mock import patch, MagicMock

from langchain_core.messages import HumanMessage, AIMessage

import src.agents.supervisor as supervisor_module
from src.metrics import new_run


def _mock_result(**overrides):
    fields = dict(
        origin="LHR", destination="JFK", destination_city="New York",
        max_budget=1500.0, travel_dates="2026-09-20 to 2026-09-25", travelers=2,
    )
    fields.update(overrides)
    parsed = supervisor_module.TravelConstraints(**fields)
    raw = AIMessage(content="", usage_metadata={"input_tokens": 150, "output_tokens": 40, "total_tokens": 190})
    return {"parsed": parsed, "raw": raw, "parsing_error": None}


def test_empty_chat_history_routes_to_end():
    out = supervisor_module.supervisor_node({"chat_history": []})
    assert out["next_node"] == "end"
    assert out["destination"] is None


def test_destination_found_routes_to_sourcing():
    mock_llm = MagicMock(invoke=MagicMock(return_value=_mock_result()))
    with patch.object(supervisor_module, "structured_llm", mock_llm):
        out = supervisor_module.supervisor_node({"chat_history": [HumanMessage(content="test trip")]})

    assert out["next_node"] == "sourcing"
    assert out["destination"] == "JFK"
    assert out["origin"] == "LHR"
    assert out["travelers"] == 2


def test_no_destination_extracted_routes_to_end():
    mock_llm = MagicMock(invoke=MagicMock(return_value=_mock_result(destination=None)))
    with patch.object(supervisor_module, "structured_llm", mock_llm):
        out = supervisor_module.supervisor_node({"chat_history": [HumanMessage(content="vague request")]})

    assert out["next_node"] == "end"


def test_llm_exception_returns_none_fields_and_routes_to_end():
    mock_llm = MagicMock(invoke=MagicMock(side_effect=RuntimeError("LLM unavailable")))
    with patch.object(supervisor_module, "structured_llm", mock_llm):
        out = supervisor_module.supervisor_node({"chat_history": [HumanMessage(content="test trip")]})

    assert out["next_node"] == "end"
    assert out["origin"] is None
    assert out["destination"] is None


def test_records_llm_usage_and_timing_when_run_is_active():
    metrics = new_run()
    mock_llm = MagicMock(invoke=MagicMock(return_value=_mock_result()))
    with patch.object(supervisor_module, "structured_llm", mock_llm):
        supervisor_module.supervisor_node({"chat_history": [HumanMessage(content="test trip")]})

    assert len(metrics.llm_usage) == 1
    assert metrics.llm_usage[0].total_tokens == 190
    assert len(metrics.node_timings) == 1
    assert metrics.node_timings[0].node == "supervisor"
