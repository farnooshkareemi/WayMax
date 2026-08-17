"""Centralized logging setup for WayMax.

Every module gets its logger via `logging.getLogger(__name__)` as usual;
this module just configures the root handler/level once, from an entry
point (src/main.py, src/ui/app.py), so a demo/production run stays quiet
by default instead of spamming "--- STARTING X NODE ---" and per-request
DEBUG lines to the terminal.

Verbosity is controlled by the WAYMAX_LOG_LEVEL env var (default: WARNING).
Set it to INFO to see node-level progress, or DEBUG to see full per-request
detail (API params, cache hits, parsed counts) - the same detail the old
print("DEBUG: ...") calls carried, just opt-in now instead of always-on.
"""

import logging
import os


def configure_logging() -> None:
    level_name = os.getenv("WAYMAX_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
