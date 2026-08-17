"""Typed loader for config/config.yaml.

Centralizes every non-secret tunable used across the WayMax pipeline (LLM model
name, RapidAPI hosts/timeouts/result caps, optimizer assumptions, and UI
defaults) so they live in one reproducible, versioned file instead of being
hardcoded inline. Secrets (GOOGLE_API_KEY, Sky_Scanner_Key) are NOT read here
— they stay in .env via os.getenv, as before.
"""

import os
from functools import lru_cache
from typing import List

import yaml
from pydantic import BaseModel

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "config.yaml"
)


class LLMConfig(BaseModel):
    model: str


class FlightsConfig(BaseModel):
    host: str
    url: str
    roundtrip_url: str
    timeout_seconds: int
    result_limit: int
    currency: str
    cabin_class: str
    market: str
    locale: str
    request_limit: int
    default_max_flight_hours: int


class HotelsConfig(BaseModel):
    host: str
    autocomplete_url: str
    search_url: str
    autocomplete_timeout_seconds: int
    search_timeout_seconds: int
    result_limit: int
    units: str
    temperature_unit: str
    room_qty: int
    currency: str


class SourcingConfig(BaseModel):
    flights: FlightsConfig
    hotels: HotelsConfig


class OptimizerConfig(BaseModel):
    rooms_per_traveler_divisor: int
    default_nights_fallback: int


class RAGConfig(BaseModel):
    embedding_model: str
    persist_directory: str
    collection_name: str
    top_k: int


class RangeConfig(BaseModel):
    min: int
    max: int
    default: int
    step: int = 1


class UIConfig(BaseModel):
    page_title: str
    page_icon: str
    layout: str
    currencies: List[str]
    budget: RangeConfig
    travelers: RangeConfig
    min_hotel_stars_default: int
    max_flight_hours: RangeConfig


class WaymaxConfig(BaseModel):
    llm: LLMConfig
    sourcing: SourcingConfig
    optimizer: OptimizerConfig
    rag: RAGConfig
    ui: UIConfig


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> WaymaxConfig:
    """Load and validate config/config.yaml.

    Resolution order: explicit `path` argument, then the WAYMAX_CONFIG env var
    (useful for tests to point at a fixture file), then the default location
    at <repo_root>/config/config.yaml. Cached after first load since the
    values are static for the lifetime of the process.
    """
    resolved_path = path or os.getenv("WAYMAX_CONFIG", DEFAULT_CONFIG_PATH)
    with open(resolved_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return WaymaxConfig(**raw)
