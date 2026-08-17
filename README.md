# WAYMAX: Autonomous Travel Optimizer

## System Overview
WAYMAX is a multi-agent travel optimization system built using LangGraph. Its primary goal is to take unstructured user travel requests and compute mathematically optimal flight and hotel combinations that strictly adhere to a maximum budget constraint.

## Architecture: The Supervisor Pattern
We utilize a Hierarchical Supervisor multi-agent topology to enforce strict mathematical and behavioral boundaries.

* **Node 0: The Supervisor (Concierge Agent)**
  * **Role:** The only agent allowed to interface with the user.
  * **Task:** Extract constraints (Destination, Travel Dates, Max Budget) from natural language and route the flow to specialist agents.
* **Node 1: The Sourcing Agent**
  * **Role:** Data retrieval. 
  * **Task:** Trigger external APIs (Flights/Hotels) based on extracted constraints. It strictly outputs raw JSON data and cannot converse.
* **Node 2: The Optimization Agent (RAG + Math)**
  * **Role:** The Mathematician.
  * **Task:** Query the vector database for hidden travel rules (baggage fees, tourist taxes) and compute the exact combination of raw API data that stays under the max budget.

## The Shared State (LangGraph TypedDict)
Data moves between agents strictly through this state schema:
* `chat_history`: List of strings.
* `extracted_constraints`: Dict containing `destination` and `max_budget` (float).
* `raw_vendor_data`: List of dicts (Flight/Hotel JSONs).
* `final_itinerary`: Dict containing the optimized result.

## RAG Knowledge Base Strategy
The system uses Retrieval-Augmented Generation to account for non-API costs:
1. Low-Cost Airline Baggage Policies.
2. Local Tourist Tax Frameworks.
3. Public Transit Manuals.

## Installation

```bash
git clone https://github.com/<your-username>/waymax.git
cd waymax
pip install -e .[dev]
```

This installs WayMax and its runtime dependencies (LangGraph, LangChain, Streamlit, etc.)
plus the `dev` extra (`pytest`, `responses`) needed to run the test suite.

## Configuration

Non-secret tunables (LLM model name, API hosts/timeouts, result caps, UI defaults, etc.)
live in [`config/config.yaml`](config/config.yaml) and are loaded through `src/config.py`.
Secrets go in a `.env` file at the repo root (not committed):

```
GOOGLE_API_KEY=your-google-api-key
Sky_Scanner_Key=your-rapidapi-key
```

## Running

```bash
# Run the LangGraph pipeline against a hardcoded test trip
python -m src.main

# Run the Streamlit UI
streamlit run src/ui/app.py
```

## Testing

```bash
pytest tests/ -v
```

All tests run offline against mocked API/LLM responses — no API keys required.