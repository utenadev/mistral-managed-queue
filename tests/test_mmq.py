"""Tests for mistral-managed-queue core functionality."""

import os
import inspect
import asyncio
import sqlite3
import sys
import tempfile
import time
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Only stub missing heavy deps so unit tests run offline. Do not clobber real installs
# (e2e needs a real ``mcp`` package in the same interpreter when collected together).
def _ensure_module(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = MagicMock()


try:
    import mcp.server.fastmcp  # noqa: F401
except Exception:
    _ensure_module("mcp")
    _ensure_module("mcp.server")
    _ensure_module("mcp.server.fastmcp")

try:
    from mistralai import Mistral  # noqa: F401
except Exception:
    # Offline: stub package so ``from mistralai import Mistral`` succeeds.
    import types

    mod = types.ModuleType("mistralai")
    mod.Mistral = MagicMock(name="Mistral")
    sys.modules["mistralai"] = mod


# Check for optional catalog dependencies
try:
    import httpx  # noqa: F401
    import yaml  # noqa: F401
    _HAS_CATALOG_DEPS = True
except ImportError:
    _HAS_CATALOG_DEPS = False

# Check for MCP availability (e.g. for _get_mcp tests).
# The stubs above inject MagicMock, so verify we got a real class:
# a MagicMock would make the real registration test meaningless.
try:
    from mcp.server.fastmcp import FastMCP  # noqa: F401
    _HAS_MCP = inspect.isclass(FastMCP) and FastMCP.__module__.startswith("mcp.")
except ImportError:
    _HAS_MCP = False
from mmq.core import (
    BASE_WAIT_TIME,
    BACKOFF_MULTIPLIER,
    DB_SHORT_TIMEOUT,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    MAX_WAIT_TIME,
    MistralRequest,
    _is_rate_limit_error,
    call_mistral_api,
    drain_queue_async,
    execute_mistral_queue_async,
    execute_next_task_async,
)
from mmq.db import (
    claim_next_task,
    claim_task,
    clean_zombie_tasks,
    get_secure_temp_db_path,
    get_task,
    init_db,
    next_base_wait_time,
    purge_tasks,
    read_queue_status,
    register_task,
    reset_rate_limit_wait_time,
    touch_task,
    update_task_status,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db_path():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass


@pytest.fixture
def mock_db_path(monkeypatch, temp_db_path):
    """Mock the TEMP_DB_PATH for testing."""
    monkeypatch.setattr("mmq.db.TEMP_DB_PATH", temp_db_path)
    return temp_db_path


@pytest.fixture
def initialized_db(mock_db_path):
    """Create and initialize a test database."""
    init_db()
    return mock_db_path


# =============================================================================
# Test MistralRequest Dataclass
# =============================================================================

class TestMistralRequest:
    """Tests for MistralRequest dataclass."""

    def test_default_values(self):
        """Test default parameter values."""
        req = MistralRequest()
        assert req.prompt is None
        assert req.messages is None
        assert req.model == DEFAULT_MODEL
        assert req.system_prompt is None
        assert req.priority == 2

    def test_to_messages_with_prompt(self):
        """Test messages generation from prompt."""
        req = MistralRequest(prompt="Hello, world!")
        messages = req.to_messages()

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == DEFAULT_SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello, world!"

    def test_to_messages_with_custom_system_prompt(self):
        """Test messages generation with custom system prompt."""
        req = MistralRequest(
            prompt="Hello",
            system_prompt="You are a helpful assistant."
        )
        messages = req.to_messages()

        assert messages[0]["content"] == "You are a helpful assistant."

    def test_to_messages_with_messages(self):
        """Test direct messages usage."""
        custom_messages = [
            {"role": "system", "content": "Custom system"},
            {"role": "user", "content": "Custom user"},
        ]
        req = MistralRequest(messages=custom_messages)
        messages = req.to_messages()

        assert messages == custom_messages

    def test_to_messages_without_prompt_or_messages_raises(self):
        """Test that missing prompt and messages raises ValueError."""
        req = MistralRequest()
        with pytest.raises(ValueError, match="prompt.*messages"):
            req.to_messages()

    def test_to_messages_both_prompt_and_messages_raises(self):
        """Test that specifying both prompt and messages raises ValueError."""
        req = MistralRequest(
            prompt="hi",
            messages=[{"role": "user", "content": "hi"}],
        )
        with pytest.raises(ValueError, match="not both"):
            req.to_messages()


# =============================================================================
# Test Database Functions
# =============================================================================

class TestDatabaseFunctions:
    """Tests for database-related functions."""

    def test_init_db_creates_tables(self, initialized_db):
        """Test that init_db creates the tasks table."""
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
            assert cursor.fetchone() is not None

    def test_clean_zombie_tasks_marks_old_processing_failed(self, initialized_db):
        """Timed-out processing tasks are marked failed and kept short-term."""
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            old_time = time.time() - 200  # older than PROCESSING_TIMEOUT (120s)
            cursor.execute(
                "INSERT INTO tasks (prompt, priority, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("test", 2, "processing", old_time, old_time),
            )
            conn.commit()

        clean_zombie_tasks()

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, error FROM tasks WHERE prompt='test'")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "failed"
            assert "zombie" in (row[1] or "")

    def test_clean_zombie_tasks_preserves_recent(self, initialized_db):
        """Recent processing tasks are not touched by zombie cleanup."""
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (prompt, priority, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("recent", 2, "processing", time.time(), time.time()),
            )
            conn.commit()

        clean_zombie_tasks()

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tasks WHERE prompt='recent'")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "processing"


# =============================================================================
# Test Rate Limit Detection
# =============================================================================

class TestRateLimitFunctions:
    """Tests for rate-limit error detection."""

    def test_is_rate_limit_error_detects_429(self):
        """Test that 429 errors are detected."""
        assert _is_rate_limit_error(Exception("429 Too Many Requests"))
        assert _is_rate_limit_error(Exception("Rate limit exceeded"))
        assert _is_rate_limit_error(Exception("too many requests"))

    def test_is_rate_limit_error_ignores_other_errors(self):
        """Test that non-rate-limit errors are not detected."""
        assert not _is_rate_limit_error(Exception("Connection error"))
        assert not _is_rate_limit_error(Exception("500 Internal Server Error"))


# =============================================================================
# Test Task Management Functions
# =============================================================================

class TestTaskManagement:
    """Tests for task management functions."""

    def test_register_task(self, initialized_db):
        """Test task registration."""
        task_id = register_task(prompt="Test prompt")

        assert task_id > 0

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, prompt, priority, status FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row[1] == "Test prompt"
            assert row[2] == 2  # priority (default)
            assert row[3] == "pending"  # status

    def test_update_task_status(self, initialized_db):
        """Test updating task status."""
        task_id = register_task(prompt="Test")

        update_task_status(task_id, "processing", "Working...")

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, result FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            assert row[0] == "processing"
            assert row[1] == "Working..."

    def test_claim_task_marks_pending_as_processing(self, initialized_db):
        """Claiming a task transitions it from pending to processing."""
        task_id = register_task(prompt="A")

        claimed = claim_task(task_id)
        assert claimed is not None
        assert claimed["id"] == task_id

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
            assert cursor.fetchone()[0] == "processing"

    def test_claim_task_empty_queue_returns_none(self, initialized_db):
        """Claiming a task id that does not exist returns None."""
        assert claim_task(9999) is None

    def test_claim_task_other_task_not_claimed(self, initialized_db):
        """Claiming one task must not claim a different task."""
        a = register_task(prompt="a", priority=1)
        b = register_task(prompt="b", priority=3)

        claimed_a = claim_task(a)
        assert claimed_a is not None
        assert claimed_a["id"] == a

        # b must still be pending (never claimed by a's caller)
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tasks WHERE id = ?", (b,))
            assert cursor.fetchone()[0] == "pending"

    def test_claim_task_already_claimed_returns_none(self, initialized_db):
        """A task already processing cannot be claimed a second time."""
        task_id = register_task(prompt="A")
        assert claim_task(task_id) is not None
        assert claim_task(task_id) is None

    def test_touch_task_updates_updated_at(self, initialized_db):
        """Heartbeat refreshes updated_at for processing tasks."""
        task_id = register_task(prompt="hb")
        update_task_status(task_id, "processing")

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (1.0, task_id))
            conn.commit()

        touch_task(task_id)

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT updated_at FROM tasks WHERE id = ?", (task_id,))
            updated = cursor.fetchone()[0]
        assert updated > 1.0


# =============================================================================
# Test queue status snapshot
# =============================================================================

class TestQueueStatus:
    """Tests for read_queue_status."""

    def test_empty_queue_status(self, initialized_db):
        """Empty DB: all status counts are zero."""
        status = read_queue_status()
        assert status["pending"] == 0
        assert status["processing"] == 0
        assert status["completed"] == 0
        assert status["failed"] == 0
        assert status["total"] == 0

    def test_counts_pending_and_processing(self, initialized_db):
        """pending / processing / completed reflect task rows."""
        p1 = register_task(prompt="p1")
        p2 = register_task(prompt="p2")
        update_task_status(p1, "processing")

        status = read_queue_status()
        assert status["pending"] == 1
        assert status["processing"] == 1
        assert status["total"] == 2
        assert p2 > 0


# =============================================================================
# Test purge
# =============================================================================

class TestPurgeTasks:
    """Tests for purge_tasks."""

    def test_purge_pending_only(self, initialized_db):
        p = register_task(prompt="pending")
        r = register_task(prompt="running")
        update_task_status(r, "processing")

        n = purge_tasks(pending=True)
        assert n == 1
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE id = ?", (p,))
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE id = ?", (r,))
            assert cursor.fetchone()[0] == 1

    def test_purge_all(self, initialized_db):
        p = register_task(prompt="p")
        r = register_task(prompt="r")
        update_task_status(r, "processing")
        done = register_task(prompt="done")
        update_task_status(done, "completed", "ok")

        n = purge_tasks(all=True)
        assert n == 3
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tasks")
            assert cursor.fetchone()[0] == 0

    def test_purge_by_task_id(self, initialized_db):
        a = register_task(prompt="a")
        b = register_task(prompt="b")
        n = purge_tasks(task_id=a)
        assert n == 1
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE id = ?", (a,))
            assert cursor.fetchone()[0] == 0
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE id = ?", (b,))
            assert cursor.fetchone()[0] == 1


# =============================================================================
# Test execute_mistral_queue_async concurrency (regressions for H1/H2)
# =============================================================================

class TestExecuteQueueConcurrent:
    """Concurrent queue execution must not deadlock and must respect the gate."""

    def _fake_env(self, monkeypatch):
        monkeypatch.setenv("MMQ_FAKE_API", "1")
        monkeypatch.setenv("MMQ_FAKE_RESPONSE", "conc-ok")
        monkeypatch.setenv("MISTRAL_API_KEY", "k")
        monkeypatch.setattr("mmq.core.BASE_WAIT_TIME", 0.1)
        monkeypatch.setattr("mmq.db.BASE_WAIT_TIME", 0.1)
        monkeypatch.setattr("mmq.core.MIN_SLEEP_INTERVAL", 0.02)

    @pytest.mark.asyncio
    async def test_parallel_execute_no_deadlock(self, initialized_db, monkeypatch):
        """Two concurrent executes with different priorities must both complete."""
        self._fake_env(monkeypatch)
        reqs = [
            MistralRequest(prompt="low", priority=1),
            MistralRequest(prompt="high", priority=3),
        ]
        results = await asyncio.wait_for(
            asyncio.gather(
                execute_mistral_queue_async(reqs[0]),
                execute_mistral_queue_async(reqs[1]),
            ),
            timeout=10,
        )
        assert len(results) == 2
        assert all("conc-ok" in r for r in results)

    @pytest.mark.asyncio
    async def test_gate_serializes_concurrent_calls(self, initialized_db, monkeypatch):
        """First call goes through immediately; the second waits on the gate."""
        self._fake_env(monkeypatch)
        monkeypatch.setattr("mmq.core.BASE_WAIT_TIME", 0.3)
        monkeypatch.setattr("mmq.db.BASE_WAIT_TIME", 0.3)
        monkeypatch.setattr("mmq.core.MIN_SLEEP_INTERVAL", 0.05)

        t0 = time.monotonic()
        results = await asyncio.wait_for(
            asyncio.gather(
                call_mistral_api("k", "m", [{"role": "user", "content": "a"}], task_id=1),
                call_mistral_api("k", "m", [{"role": "user", "content": "b"}], task_id=2),
            ),
            timeout=10,
        )
        elapsed = time.monotonic() - t0
        assert len(results) == 2
        assert elapsed >= 0.3 * 0.7, f"gate not enforced, elapsed={elapsed:.3f}s"


# =============================================================================
# Test call_mistral_api retry behavior
# =============================================================================

class TestCallMistralApi:
    """Tests for streaming retry / buffer reset behavior."""

    @staticmethod
    def _noop_gate(monkeypatch):
        """No-op the shared rate gate so these tests exercise retry logic only."""
        async def _noop(*args, **kwargs):
            return None
        import mmq.core
        monkeypatch.setattr(mmq.core, "_await_rate_limit_slot", _noop)

    @pytest.mark.asyncio
    async def test_partial_stream_reset_on_retry(self, monkeypatch, mock_db_path):
        """Failed partial stream must not be concatenated onto the next attempt."""
        monkeypatch.setenv("MMQ_FAKE_API", "0")
        self._noop_gate(monkeypatch)

        class FakeChunk:
            def __init__(self, text):
                self.choices = [MagicMock(delta=MagicMock(content=text))]

        call_count = {"n": 0}

        async def fake_stream(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                async def gen():
                    yield FakeChunk("PARTIAL-")
                    raise Exception("connection reset")
                return gen()
            else:
                async def gen():
                    yield FakeChunk("FULL")
                return gen()

        mock_client = MagicMock()
        mock_client.chat.stream_async = fake_stream
        monkeypatch.setattr("mmq.core.Mistral", MagicMock(return_value=mock_client))
        monkeypatch.setattr("mmq.core.MIN_SLEEP_INTERVAL", 0.01)

        result = await call_mistral_api("fake-key", "mistral-small-latest", [{"role": "user", "content": "x"}])
        assert result == "FULL"
        assert "PARTIAL" not in result

    @pytest.mark.asyncio
    async def test_rate_limit_error_backoff(self, monkeypatch, mock_db_path):
        """On 429, the retry path backs off and eventually succeeds."""
        monkeypatch.setenv("MMQ_FAKE_API", "0")
        self._noop_gate(monkeypatch)

        class FakeChunk:
            def __init__(self, text):
                self.choices = [MagicMock(delta=MagicMock(content=text))]

        call_count = {"n": 0}

        async def fake_stream(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("429 Too Many Requests")
            async def gen():
                yield FakeChunk("ok")
            return gen()

        mock_client = MagicMock()
        mock_client.chat.stream_async = fake_stream
        monkeypatch.setattr("mmq.core.Mistral", MagicMock(return_value=mock_client))
        monkeypatch.setattr("mmq.core.MAX_WAIT_TIME", 0.05)
        monkeypatch.setattr("mmq.core.BASE_WAIT_TIME", 0.01)

        result = await call_mistral_api("fake-key", "mistral-small-latest", [{"role": "user", "content": "x"}])
        assert result == "ok"
        assert call_count["n"] == 2


# =============================================================================
# Test Constants
# =============================================================================

class TestConstants:
    """Tests for constant values."""

    def test_rate_limit_constants(self):
        """Test rate limiting constants have expected values."""
        assert BASE_WAIT_TIME == 31.0
        assert MAX_WAIT_TIME == 300.0
        assert BACKOFF_MULTIPLIER == 2.0

    def test_model_constants(self):
        """Test model constants."""
        assert DEFAULT_MODEL == "mistral-small-latest"
        assert "helpful" in DEFAULT_SYSTEM_PROMPT.lower()

class TestRandomInterval:
    """Tests for MMQ_RANDOM_INTERVAL randomized base wait mode."""

    def test_disabled_returns_fixed_base(self, monkeypatch):
        """With the mode off, the base interval is exactly BASE_WAIT_TIME."""
        monkeypatch.setattr("mmq.db.RANDOM_INTERVAL", False)
        assert next_base_wait_time() == BASE_WAIT_TIME

    def test_enabled_draws_uniformly_in_range(self, monkeypatch):
        """With the mode on, draws stay within [BASE_WAIT_TIME, max] and vary."""
        monkeypatch.setattr("mmq.db.RANDOM_INTERVAL", True)
        samples = [next_base_wait_time() for _ in range(200)]
        assert all(BASE_WAIT_TIME <= s <= 50.0 for s in samples)
        assert len(set(samples)) > 1

    def test_enabled_respects_custom_max(self, monkeypatch):
        """A custom MMQ_RANDOM_INTERVAL_MAX caps the upper bound."""
        monkeypatch.setattr("mmq.db.RANDOM_INTERVAL", True)
        monkeypatch.setattr("mmq.db.RANDOM_INTERVAL_MAX", 40.0)
        samples = [next_base_wait_time() for _ in range(100)]
        assert all(31.0 <= s <= 40.0 for s in samples)

    def test_max_below_min_is_clamped(self, monkeypatch):
        """A max lower than BASE_WAIT_TIME degenerates to the min bound."""
        monkeypatch.setattr("mmq.db.RANDOM_INTERVAL", True)
        monkeypatch.setattr("mmq.db.RANDOM_INTERVAL_MAX", 10.0)
        assert next_base_wait_time() == BASE_WAIT_TIME

    def test_reset_stores_randomized_interval(self, monkeypatch, mock_db_path):
        """reset_rate_limit_wait_time persists a value within the range."""
        monkeypatch.setattr("mmq.db.RANDOM_INTERVAL", True)
        reset_rate_limit_wait_time()
        stored = read_queue_status()["current_wait_interval"]
        assert BASE_WAIT_TIME <= stored <= 50.0


# =============================================================================
# Test Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_secure_temp_db_path(self):
        """Test secure temp DB path generation."""
        path = get_secure_temp_db_path()
        assert path.endswith("mistral_managed_flow_control.db")
        assert "mistral_managed_queue_" in path


# =============================================================================
# Test claim_next_task (priority-ordered worker claim)
# =============================================================================

class TestClaimNextTask:
    """The worker's priority-ordered claim must be atomic and deterministic."""

    def test_claims_highest_priority_first(self, initialized_db):
        register_task(prompt="low", priority=1)
        register_task(prompt="high", priority=3)
        register_task(prompt="mid", priority=2)
        assert claim_next_task()["priority"] == 3
        assert claim_next_task()["priority"] == 2
        assert claim_next_task()["priority"] == 1
        assert claim_next_task() is None

    def test_fifo_on_tie(self, initialized_db):
        a = register_task(prompt="a", priority=5)
        b = register_task(prompt="b", priority=5)
        assert claim_next_task()["id"] == a
        assert claim_next_task()["id"] == b

    def test_atomic_no_double_claim(self, initialized_db):
        a = register_task(prompt="a", priority=2)
        b = register_task(prompt="b", priority=2)
        first = claim_next_task()["id"]
        second = claim_next_task()["id"]
        assert {first, second} == {a, b}
        # Already-claimed tasks are never handed out again
        assert claim_next_task() is None

    def test_claimed_task_marked_processing(self, initialized_db):
        tid = register_task(prompt="x", priority=2)
        claim_next_task()
        task = get_task(tid)
        assert task["status"] == "processing"


# =============================================================================
# Test get_task
# =============================================================================

class TestGetTask:
    """get_task must return the full row or None."""

    def test_returns_full_row(self, initialized_db):
        tid = register_task(prompt="p", model="m", system_prompt="s", priority=7)
        task = get_task(tid)
        assert task is not None
        assert task["prompt"] == "p"
        assert task["model"] == "m"
        assert task["system_prompt"] == "s"
        assert task["priority"] == 7
        assert task["status"] == "pending"

    def test_missing_returns_none(self, initialized_db):
        assert get_task(99999) is None


# =============================================================================
# Test worker drain (execute_next / drain / watch)
# =============================================================================

class TestWorkerQueue:
    """The `mmq work` worker drains pending tasks in priority order."""

    def _fake_env(self, monkeypatch):
        monkeypatch.setenv("MMQ_FAKE_API", "1")
        monkeypatch.setenv("MMQ_FAKE_RESPONSE", "work-ok")
        monkeypatch.setenv("MISTRAL_API_KEY", "k")
        monkeypatch.setattr("mmq.core.BASE_WAIT_TIME", 0.05)
        monkeypatch.setattr("mmq.db.BASE_WAIT_TIME", 0.05)
        monkeypatch.setattr("mmq.core.MIN_SLEEP_INTERVAL", 0.01)

    @pytest.mark.asyncio
    async def test_execute_next_empty_queue(self, initialized_db, monkeypatch):
        self._fake_env(monkeypatch)
        assert await execute_next_task_async() is None

    @pytest.mark.asyncio
    async def test_execute_next_returns_response(self, initialized_db, monkeypatch):
        self._fake_env(monkeypatch)
        monkeypatch.setenv("MMQ_FAKE_RESPONSE", "single-ok")
        register_task(prompt="hi", priority=2)
        result = await execute_next_task_async()
        assert result == "single-ok"

    @pytest.mark.asyncio
    async def test_drain_processes_all_and_completes(self, initialized_db, monkeypatch):
        self._fake_env(monkeypatch)
        low = register_task(prompt="low", priority=1)
        mid = register_task(prompt="mid", priority=2)
        high = register_task(prompt="high", priority=3)
        count = await drain_queue_async()
        assert count == 3
        for tid in (low, mid, high):
            task = get_task(tid)
            assert task["status"] == "completed"

    @pytest.mark.asyncio
    async def test_drain_continues_past_failure(self, initialized_db, monkeypatch):
        self._fake_env(monkeypatch)
        monkeypatch.setenv("MMQ_FAKE_FAIL", "error")
        a = register_task(prompt="a", priority=2)
        b = register_task(prompt="b", priority=1)
        count = await drain_queue_async()
        assert count == 2
        assert get_task(a)["status"] == "failed"
        assert get_task(b)["status"] == "failed"


# =============================================================================
# Test CLI wiring regressions (adversarial review agy+opus 2026-08-13)
# =============================================================================

class TestCliWiring:
    """CLI subcommand wiring must not pass arguments in the wrong order or None."""

    @pytest.mark.skipif(
        not _HAS_CATALOG_DEPS, reason="requires mmq[catalog] (httpx+PyYAML)"
    )
    def test_catalog_fetch_passes_document_to_writer(self, monkeypatch):
        """write_catalog_yaml(path, document) must receive (output, document)."""
        from types import SimpleNamespace

        from mmq import cli

        doc = {"schema_version": 1, "providers": []}
        fake_fetch = MagicMock(
            return_value=SimpleNamespace(document=doc, errors=[], partial=False)
        )
        fake_write = MagicMock()
        monkeypatch.setattr("mmq.catalog.fetch.fetch_catalog", fake_fetch)
        monkeypatch.setattr("mmq.catalog.write.write_catalog_yaml", fake_write)

        args = cli._build_parser().parse_args(["catalog", "fetch", "-o", "out.yaml"])
        assert cli._resolve_args(args) == 0
        fake_write.assert_called_once_with("out.yaml", doc)
        assert fake_fetch.call_args.kwargs.get("validate") is True

    @pytest.mark.skipif(
        not _HAS_CATALOG_DEPS, reason="requires mmq[catalog] (httpx+PyYAML)"
    )
    def test_catalog_fetch_no_validate_flag(self, monkeypatch):
        """`--no-validate` must reach fetch_catalog (not be silently ignored)."""
        from types import SimpleNamespace

        from mmq import cli

        fake_fetch = MagicMock(
            return_value=SimpleNamespace(document={}, errors=[], partial=False)
        )
        fake_write = MagicMock()
        monkeypatch.setattr("mmq.catalog.fetch.fetch_catalog", fake_fetch)
        monkeypatch.setattr("mmq.catalog.write.write_catalog_yaml", fake_write)

        args = cli._build_parser().parse_args(
            ["catalog", "fetch", "--no-validate", "-o", "out.yaml"]
        )
        assert cli._resolve_args(args) == 0
        assert fake_fetch.call_args.kwargs.get("validate") is False

    def test_ask_defaults_model_when_omitted(self, monkeypatch, capsys):
        """`mmq ask` without -m must fall back to DEFAULT_MODEL, not None."""
        from mmq import cli
        from mmq import core as core_mod

        calls = {}

        async def fake_call(api_key, model, messages, task_id=None):
            calls["model"] = model
            calls["messages"] = messages
            return "hello"

        monkeypatch.setattr(core_mod, "call_mistral_api", fake_call)
        args = cli._build_parser().parse_args(["ask", "hi"])
        assert cli._resolve_args(args) == 0
        assert calls["model"] == DEFAULT_MODEL
        assert "hi" in str(calls["messages"])

    @pytest.mark.skipif(
        not _HAS_MCP, reason="mcp package not installed"
    )
    def test_get_mcp_registers_tools(self):
        """_get_mcp() must succeed and register both tools."""
        from mmq.mcp_server import _get_mcp
        mcp = _get_mcp()
        assert mcp is not None
        names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "ask_mistral" in names
        assert "get_queue_status" in names

    def test_catalog_fetch_without_extras_shows_guidance(self, capsys):
        """Without catalog deps, mmq catalog fetch must print guidance and exit 1."""
        from mmq import cli
        import sys

        # Simulate missing httpx: block the import and drop any cached catalog
        # modules so `from .catalog.fetch import ...` actually fails.
        saved = {}
        for name in list(sys.modules):
            if name.startswith("mmq.catalog"):
                saved[name] = sys.modules.pop(name)

        import builtins
        orig_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "httpx":
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return orig_import(name, *args, **kwargs)

        builtins.__import__ = _mock_import
        try:
            args = cli._build_parser().parse_args(["catalog", "fetch", "-o", "out.yaml"])
            exit_code = cli._resolve_args(args)
            assert exit_code == 1, f"expected 1, got {exit_code}"
            err = capsys.readouterr().err
            assert "mistral-managed-queue[catalog]" in err
        finally:
            builtins.__import__ = orig_import
            sys.modules.update(saved)

