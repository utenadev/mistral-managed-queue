"""Shared fixtures for subprocess e2e tests."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MMQ_SCRIPT = REPO_ROOT / "mmq.py"

# If unit tests (or other plugins) left MagicMock stubs in sys.modules, drop them
# so the real MCP client can be imported for protocol e2e.
for _name in list(sys.modules):
    if _name == "mcp" or _name.startswith("mcp."):
        if isinstance(sys.modules[_name], MagicMock):
            del sys.modules[_name]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def mmq_script() -> Path:
    assert MMQ_SCRIPT.is_file(), f"mmq.py not found at {MMQ_SCRIPT}"
    return MMQ_SCRIPT


@pytest.fixture(scope="session")
def python_exe() -> str:
    """Interpreter that runs mmq.py (must have mcp + mistralai when not faking import)."""
    return sys.executable


@pytest.fixture
def e2e_db(tmp_path) -> Path:
    return tmp_path / "e2e_flow.db"


@pytest.fixture
def e2e_env(e2e_db) -> dict:
    """Isolated env: fake API, short waits, dedicated SQLite path."""
    env = os.environ.copy()
    # Drop keys that could force live behaviour in nested tools
    env.pop("MMQ_FAKE_FAIL", None)
    env.update(
        {
            "MMQ_FAKE_API": "1",
            "MMQ_FAKE_RESPONSE": "e2e-ok",
            "MISTRAL_API_KEY": env.get("MISTRAL_API_KEY") or "e2e-test-key",
            "MMQ_TEMP_DB_PATH": str(e2e_db),
            "MMQ_BASE_WAIT_TIME": "0.05",
            "MMQ_MAX_WAIT_TIME": "1.0",
            "MMQ_MIN_SLEEP_INTERVAL": "0.02",
            "MMQ_TASK_POLL_INTERVAL": "0.05",
            "MMQ_PROCESSING_TIMEOUT": "5.0",
            "MMQ_MAX_RETRIES": "2",
            # Avoid inheriting user locale surprises
            "PYTHONUNBUFFERED": "1",
        }
    )
    return env


@pytest.fixture
def mmq_cmd(python_exe, mmq_script):
    """Build argv prefix: [python, mmq.py, ...]."""

    def _cmd(*args: str) -> list[str]:
        return [python_exe, str(mmq_script), *args]

    return _cmd


@pytest.fixture(scope="session")
def mcp_available() -> bool:
    try:
        import mcp  # noqa: F401
        from mcp.server.fastmcp import FastMCP  # noqa: F401

        return True
    except Exception:
        return False


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "e2e: end-to-end tests (CLI/MCP subprocess, fake API by default)"
    )
    config.addinivalue_line(
        "markers",
        "live: real Mistral API (requires MISTRAL_API_KEY; costs free-tier quota)",
    )


def require_mcp(mcp_available: bool) -> None:
    if not mcp_available:
        pytest.skip("mcp package (with FastMCP) not installed in this interpreter")


def require_uv() -> str:
    path = shutil.which("uv")
    if not path:
        pytest.skip("uv not found on PATH")
    return path
