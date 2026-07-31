"""CLI process e2e: subprocess → main() → queue → FakeMistralClient."""

from __future__ import annotations

import json
import subprocess
import time

import pytest

pytestmark = pytest.mark.e2e


def _run(cmd: list[str], env: dict, timeout: float = 30.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_cli_happy_path(mmq_cmd, e2e_env, mcp_available):
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    env = {**e2e_env, "MMQ_FAKE_RESPONSE": "cli-hello"}
    result = _run(mmq_cmd("ping from cli"), env)
    assert result.returncode == 0, result.stderr
    assert "cli-hello" in result.stdout


def test_cli_missing_api_key(mmq_cmd, e2e_env, mcp_available):
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    env = {**e2e_env}
    env.pop("MISTRAL_API_KEY", None)
    # Ensure empty, not inherited from outer shell alone — pop may leave nothing
    env["MISTRAL_API_KEY"] = ""
    # empty string is still "set"; execute checks os.environ.get which returns ""
    # ValueError only when not set / falsy — "" is falsy. Good.
    del env["MISTRAL_API_KEY"]

    result = _run(mmq_cmd("no key"), env)
    assert result.returncode == 1
    assert "MISTRAL_API_KEY" in (result.stderr + result.stdout)


def test_cli_invalid_messages_json(mmq_cmd, e2e_env, mcp_available):
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    result = _run(mmq_cmd("--messages", "not-json"), e2e_env)
    # argparse accepts the flag; parse_messages_json fails inside run_cli
    assert result.returncode == 1
    combined = (result.stderr + result.stdout).lower()
    assert "error" in combined or "json" in combined or "messages" in combined


def test_cli_help_without_prompt(mmq_cmd, e2e_env, mcp_available):
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    result = _run(mmq_cmd(), e2e_env)
    assert result.returncode == 1
    assert "usage" in (result.stdout + result.stderr).lower()


def test_cli_two_sequential_respect_rate_gate(mmq_cmd, e2e_env, e2e_db, mcp_available):
    """Second CLI process should wait for shared BASE_WAIT after the first."""
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    wait = 0.4
    env = {
        **e2e_env,
        "MMQ_BASE_WAIT_TIME": str(wait),
        "MMQ_MIN_SLEEP_INTERVAL": "0.05",
        "MMQ_FAKE_RESPONSE": "seq",
    }

    t0 = time.monotonic()
    r1 = _run(mmq_cmd("first"), env, timeout=30)
    assert r1.returncode == 0, r1.stderr
    r2 = _run(mmq_cmd("second"), env, timeout=30)
    elapsed = time.monotonic() - t0

    assert r2.returncode == 0, r2.stderr
    # Two grants: first free, second waits ~wait. Allow slack for process startup.
    assert elapsed >= wait * 0.7, f"expected rate-limit wait, elapsed={elapsed:.3f}s"
    assert e2e_db.is_file()


def test_cli_purge_pending(mmq_cmd, e2e_env, e2e_db, mcp_available):
    """--purge cancels pending rows in the shared DB without calling the API."""
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    import sqlite3
    import time

    # Seed a pending row (CLI process will use same MMQ_TEMP_DB_PATH via e2e_env)
    with sqlite3.connect(e2e_db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "prompt_summary TEXT NOT NULL,"
            "priority INTEGER DEFAULT 2,"
            "status TEXT DEFAULT 'pending',"
            "result TEXT,"
            "created_at REAL NOT NULL,"
            "updated_at REAL NOT NULL)"
        )
        now = time.time()
        conn.execute(
            "INSERT INTO tasks (prompt_summary, priority, status, created_at, updated_at) "
            "VALUES ('seed', 2, 'pending', ?, ?)",
            (now, now),
        )
        conn.commit()

    result = _run(mmq_cmd("--purge"), e2e_env)
    assert result.returncode == 0, result.stderr
    assert "Cancelled" in result.stdout
    with sqlite3.connect(e2e_db) as conn:
        row = conn.execute("SELECT status FROM tasks LIMIT 1").fetchone()
        assert row[0] == "cancelled"
