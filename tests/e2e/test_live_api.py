"""Optional live Mistral API smoke (opt-in; burns free-tier quota)."""

from __future__ import annotations

import os
import subprocess

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.live]


@pytest.fixture
def live_env(e2e_db):
    key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if not key:
        pytest.skip("MISTRAL_API_KEY not set")
    env = os.environ.copy()
    env.update(
        {
            "MISTRAL_API_KEY": key,
            "MMQ_TEMP_DB_PATH": str(e2e_db),
            # Keep real timing but don't use fake API
            "MMQ_FAKE_API": "0",
            "PYTHONUNBUFFERED": "1",
        }
    )
    env.pop("MMQ_FAKE_RESPONSE", None)
    env.pop("MMQ_FAKE_FAIL", None)
    return env


def test_live_cli_one_shot(mmq_cmd, live_env, mcp_available):
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    result = subprocess.run(
        mmq_cmd("Reply with exactly: pong"),
        env=live_env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "expected non-empty model response"
