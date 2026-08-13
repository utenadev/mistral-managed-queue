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
    result = _run(mmq_cmd("ask", "ping from cli"), env)
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

    result = _run(mmq_cmd("ask", "no key"), env)
    assert result.returncode == 1
    assert "MISTRAL_API_KEY" in (result.stderr + result.stdout)


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
    r1 = _run(mmq_cmd("ask", "first"), env, timeout=30)
    assert r1.returncode == 0, r1.stderr
    r2 = _run(mmq_cmd("ask", "second"), env, timeout=30)
    elapsed = time.monotonic() - t0

    assert r2.returncode == 0, r2.stderr
    # Two grants: first free, second waits ~wait. Allow slack for process startup.
    assert elapsed >= wait * 0.7, f"expected rate-limit wait, elapsed={elapsed:.3f}s"
    assert e2e_db.is_file()


def test_cli_two_concurrent_respect_rate_gate(mmq_cmd, e2e_env, e2e_db, mcp_available):
    """Two processes started together must be serialized by the shared gate.

    Regression for H2: the shared rate gate must apply to the *first* call of
    every process, so concurrent ``mmq ask`` runs cannot collide.
    """
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    wait = 0.5
    env = {
        **e2e_env,
        "MMQ_BASE_WAIT_TIME": str(wait),
        "MMQ_MIN_SLEEP_INTERVAL": "0.05",
        "MMQ_FAKE_RESPONSE": "conc",
    }

    t0 = time.monotonic()
    p1 = subprocess.Popen(
        mmq_cmd("ask", "one"), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    p2 = subprocess.Popen(
        mmq_cmd("ask", "two"), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    out1, err1 = p1.communicate(timeout=30)
    out2, err2 = p2.communicate(timeout=30)
    elapsed = time.monotonic() - t0

    assert p1.returncode == 0, err1
    assert p2.returncode == 0, err2
    assert "conc" in (out1 + out2)
    # The gate must serialize the two processes: total wall time >= BASE_WAIT.
    assert elapsed >= wait * 0.7, (
        f"gate not enforced across processes, elapsed={elapsed:.3f}s"
    )
    assert e2e_db.is_file()


def test_cli_purge_pending(mmq_cmd, e2e_env, e2e_db, mcp_available):
    """mmq purge --pending removes pending rows in the shared DB without calling the API."""
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    import sqlite3
    import time

    # Seed a pending row (CLI process will use same MMQ_TEMP_DB_PATH via e2e_env)
    with sqlite3.connect(e2e_db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "prompt TEXT NOT NULL,"
            "model TEXT,"
            "system_prompt TEXT,"
            "priority INTEGER DEFAULT 2,"
            "status TEXT NOT NULL,"
            "result TEXT,"
            "error TEXT,"
            "created_at REAL NOT NULL,"
            "updated_at REAL NOT NULL)"
        )
        now = time.time()
        conn.execute(
            "INSERT INTO tasks (prompt, priority, status, created_at, updated_at) "
            "VALUES ('seed', 2, 'pending', ?, ?)",
            (now, now),
        )
        conn.commit()

    result = _run(mmq_cmd("purge", "--pending"), e2e_env)
    assert result.returncode == 0, result.stderr
    assert "Deleted" in result.stdout
    with sqlite3.connect(e2e_db) as conn:
        row = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
        assert row[0] == 0


def test_cli_fetch_then_work_drains(mmq_cmd, e2e_env, e2e_db, mcp_available):
    """`mmq fetch` enqueues; `mmq work` drains it and completes the task."""
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    import sqlite3

    env = {**e2e_env, "MMQ_FAKE_RESPONSE": "work-e2e"}

    r1 = _run(mmq_cmd("fetch", "hello from fetch"), env)
    assert r1.returncode == 0, r1.stderr
    assert "enqueued" in r1.stdout.lower()
    assert "mmq work" in r1.stdout

    r2 = _run(mmq_cmd("work"), env)
    assert r2.returncode == 0, r2.stderr
    assert "Processed 1 task" in r2.stdout

    with sqlite3.connect(e2e_db) as conn:
        rows = conn.execute("SELECT status, result FROM tasks").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "completed"
    assert rows[0][1] == "work-e2e"


def test_cli_work_respects_priority(mmq_cmd, e2e_env, e2e_db, mcp_available):
    """`mmq work` processes the higher-priority task first."""
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    import sqlite3

    env = {**e2e_env, "MMQ_FAKE_RESPONSE": "prio"}

    r_high = _run(mmq_cmd("fetch", "hi", "--priority", "10"), env)
    r_low = _run(mmq_cmd("fetch", "lo", "--priority", "1"), env)
    assert r_high.returncode == 0, r_high.stderr
    assert r_low.returncode == 0, r_low.stderr

    r_work = _run(mmq_cmd("work"), env)
    assert r_work.returncode == 0, r_work.stderr
    assert "Processed 2 task" in r_work.stdout

    with sqlite3.connect(e2e_db) as conn:
        rows = conn.execute(
            "SELECT prompt, priority, updated_at FROM tasks ORDER BY priority DESC"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "hi" and rows[0][1] == 10
    assert rows[1][0] == "lo" and rows[1][1] == 1
    # The higher-priority task finished first (strictly earlier timestamp)
    assert rows[0][2] < rows[1][2]


def test_cli_work_once(mmq_cmd, e2e_env, e2e_db, mcp_available):
    """`mmq work --once` processes exactly one task."""
    from tests.e2e.conftest import require_mcp

    require_mcp(mcp_available)

    import sqlite3

    env = {**e2e_env, "MMQ_FAKE_RESPONSE": "once"}

    _run(mmq_cmd("fetch", "a", "--priority", "2"), env)
    _run(mmq_cmd("fetch", "b", "--priority", "2"), env)

    r = _run(mmq_cmd("work", "--once"), env)
    assert r.returncode == 0, r.stderr
    assert "Processed 1 task" in r.stdout

    with sqlite3.connect(e2e_db) as conn:
        statuses = sorted(s[0] for s in conn.execute("SELECT status FROM tasks"))
    assert statuses == ["completed", "pending"]
