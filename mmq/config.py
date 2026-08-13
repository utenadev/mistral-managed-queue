# mmq/config.py
"""Shared configuration: env var helpers and module constants (single source of truth)."""

import os


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


# ---- Rate limit baseline values ----
BASE_WAIT_TIME = _env_float("MMQ_BASE_WAIT_TIME", 31.0)  # free tier ~1 req/30s
MAX_WAIT_TIME = _env_float("MMQ_MAX_WAIT_TIME", 300.0)
BACKOFF_MULTIPLIER = _env_float("MMQ_BACKOFF_MULTIPLIER", 2.0)
MIN_SLEEP_INTERVAL = _env_float("MMQ_MIN_SLEEP_INTERVAL", 2.0)
PROCESSING_TIMEOUT = _env_float("MMQ_PROCESSING_TIMEOUT", 120.0)

# ---- Default model / system prompt ----
DEFAULT_MODEL = os.environ.get("MMQ_DEFAULT_MODEL", "mistral-small-latest")
DEFAULT_SYSTEM_PROMPT = "You are a helpful, respectful, and honest assistant."

# ---- DB connection timeouts ----
DB_CONNECT_TIMEOUT = _env_float("MMQ_DB_CONNECT_TIMEOUT", 30.0)
DB_SHORT_TIMEOUT = _env_float("MMQ_DB_SHORT_TIMEOUT", 10.0)
