"""Tests for mcp-mistral-queue core functionality."""

import os
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
    import mistralai  # noqa: F401
except Exception:
    _ensure_module("mistralai")

from mmq import (
    BASE_WAIT_TIME,
    BACKOFF_MULTIPLIER,
    DB_SHORT_TIMEOUT,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    MAX_WAIT_TIME,
    MistralRequest,
    PROGRESS_REPORT_INTERVAL,
    call_mistral_api,
    claim_task,
    clean_zombie_tasks,
    get_secure_temp_db_path,
    init_db,
    is_rate_limit_error,
    register_task,
    touch_task,
    update_rate_limit_wait_time,
    update_task_status,
    wait_for_rate_limit,
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
    monkeypatch.setattr("mmq.TEMP_DB_PATH", temp_db_path)
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


# =============================================================================
# Test Database Functions
# =============================================================================

class TestDatabaseFunctions:
    """Tests for database-related functions."""

    def test_init_db_creates_tables(self, initialized_db):
        """Test that init_db creates required tables."""
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            
            # Check tasks table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
            assert cursor.fetchone() is not None
            
            # Check api_log table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_log'")
            assert cursor.fetchone() is not None
            
            # Check api_log has initial data
            cursor.execute("SELECT COUNT(*) FROM api_log")
            assert cursor.fetchone()[0] == 1

    def test_clean_zombie_tasks_removes_old_processing(self, initialized_db):
        """Test that clean_zombie_tasks removes old processing tasks."""
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            
            # Insert a zombie task (old processing task)
            old_time = time.time() - 200  # 200 seconds ago
            cursor.execute(
                "INSERT INTO tasks (prompt_summary, priority, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("test", 2, "processing", old_time, old_time),
            )
            conn.commit()
        
        # Clean zombie tasks
        cleaned = clean_zombie_tasks()
        assert cleaned >= 1
        
        # Verify task was marked as failed
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tasks WHERE prompt_summary='test'")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "failed"

    def test_clean_zombie_tasks_preserves_recent(self, initialized_db):
        """Test that clean_zombie_tasks preserves recent processing tasks."""
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            
            # Insert a recent processing task
            cursor.execute(
                "INSERT INTO tasks (prompt_summary, priority, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("recent", 2, "processing", time.time(), time.time()),
            )
            conn.commit()
        
        # Clean zombie tasks
        clean_zombie_tasks()
        
        # Verify recent task is still processing
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tasks WHERE prompt_summary='recent'")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "processing"


# =============================================================================
# Test Rate Limit Functions
# =============================================================================

class TestRateLimitFunctions:
    """Tests for rate limiting functions."""

    def test_is_rate_limit_error_detects_429(self):
        """Test that 429 errors are detected."""
        assert is_rate_limit_error(Exception("429 Too Many Requests"))
        assert is_rate_limit_error(Exception("Rate limit exceeded"))
        assert is_rate_limit_error(Exception("too many requests"))

    def test_is_rate_limit_error_ignores_other_errors(self):
        """Test that non-rate-limit errors are not detected."""
        assert not is_rate_limit_error(Exception("Connection error"))
        assert not is_rate_limit_error(Exception("500 Internal Server Error"))

    @pytest.mark.asyncio
    async def test_wait_for_rate_limit_initially_ready(self, initialized_db):
        """Test that rate limit is initially ready."""
        ready, sleep_needed, wait_time = await wait_for_rate_limit()
        assert ready is True
        assert sleep_needed == 0.0
        assert wait_time == BASE_WAIT_TIME

    @pytest.mark.asyncio
    async def test_update_and_reset_rate_limit(self, initialized_db):
        """Test updating and resetting rate limit wait time."""
        # Update to a new value
        await update_rate_limit_wait_time(60.0)
        
        # Check it was updated
        ready, sleep_needed, wait_time = await wait_for_rate_limit()
        assert ready is True
        assert wait_time == 60.0

    @pytest.mark.asyncio
    async def test_wait_for_rate_limit_not_ready_when_recent(self, initialized_db):
        """After a recent stamp, gate should refuse until interval elapses."""
        # Consume a slot at base interval
        ready, _, wait_time = await wait_for_rate_limit()
        assert ready is True
        assert wait_time == BASE_WAIT_TIME

        ready2, sleep_needed, _ = await wait_for_rate_limit()
        assert ready2 is False
        assert sleep_needed > 0

    @pytest.mark.asyncio
    async def test_stamp_executed_updates_last_executed(self, initialized_db):
        """stamp_executed=True moves last_executed_at to now for shared backoff."""
        await update_rate_limit_wait_time(62.0, stamp_executed=True)
        ready, sleep_needed, wait_time = await wait_for_rate_limit()
        assert ready is False
        assert wait_time == 62.0
        assert sleep_needed > 0


# =============================================================================
# Test Task Management Functions
# =============================================================================

class TestTaskManagement:
    """Tests for task management functions."""

    @pytest.mark.asyncio
    async def test_register_task(self, initialized_db):
        """Test task registration."""
        req = MistralRequest(prompt="Test prompt")
        task_id = await register_task(req)
        
        assert task_id > 0
        
        # Verify in database
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, prompt_summary, priority, status FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row[1] == "Test prompt"  # prompt_summary
            assert row[2] == 2  # priority (default)
            assert row[3] == "pending"  # status

    @pytest.mark.asyncio
    async def test_update_task_status(self, initialized_db):
        """Test updating task status."""
        # First register a task
        req = MistralRequest(prompt="Test")
        task_id = await register_task(req)
        
        # Update status
        await update_task_status(task_id, "processing", "Working...")
        
        # Verify update
        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, result FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            assert row[0] == "processing"
            assert row[1] == "Working..."

    @pytest.mark.asyncio
    async def test_claim_task_exclusive_single_inflight(self, initialized_db):
        """Only one task may be processing; second claim must fail."""
        req_a = MistralRequest(prompt="A", priority=2)
        req_b = MistralRequest(prompt="B", priority=2)
        id_a = await register_task(req_a)
        id_b = await register_task(req_b)

        assert await claim_task(id_a) is True
        # B is next pending but A is still processing
        assert await claim_task(id_b) is False

        await update_task_status(id_a, "completed", "done")
        assert await claim_task(id_b) is True

    @pytest.mark.asyncio
    async def test_claim_task_respects_priority(self, initialized_db):
        """Higher priority (lower number) is claimed first."""
        low = await register_task(MistralRequest(prompt="low", priority=3))
        high = await register_task(MistralRequest(prompt="high", priority=1))

        assert await claim_task(low) is False
        assert await claim_task(high) is True

    @pytest.mark.asyncio
    async def test_touch_task_updates_updated_at(self, initialized_db):
        """Heartbeat refreshes updated_at for processing tasks."""
        task_id = await register_task(MistralRequest(prompt="hb"))
        await update_task_status(task_id, "processing")

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (1.0, task_id))
            conn.commit()

        await touch_task(task_id)

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT updated_at FROM tasks WHERE id = ?", (task_id,))
            updated = cursor.fetchone()[0]
        assert updated > 1.0


# =============================================================================
# Test call_mistral_api retry behavior
# =============================================================================

class TestCallMistralApi:
    """Tests for streaming retry / buffer reset / rate-limit re-entry."""

    @pytest.mark.asyncio
    async def test_partial_stream_reset_on_retry(self, initialized_db, monkeypatch):
        """Failed partial stream must not be concatenated onto the next attempt."""
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
        monkeypatch.setattr("mmq.Mistral", MagicMock(return_value=mock_client))
        # Skip shared rate-limit re-entry waits on non-429 path (2s sleep only once)
        monkeypatch.setattr("mmq.MIN_SLEEP_INTERVAL", 0.01)

        result = await call_mistral_api("fake-key", "mistral-small-latest", [{"role": "user", "content": "x"}])
        assert result == "FULL"
        assert "PARTIAL" not in result

    @pytest.mark.asyncio
    async def test_rate_limit_error_reenters_gate(self, initialized_db, monkeypatch):
        """On 429, shared wait time is stamped and wait_for_rate_limit is used again."""
        class FakeChunk:
            def __init__(self, text):
                self.choices = [MagicMock(delta=MagicMock(content=text))]

        call_count = {"n": 0}
        gate_calls = {"n": 0}

        async def fake_stream(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("429 Too Many Requests")
            async def gen():
                yield FakeChunk("ok")
            return gen()

        async def fake_await_slot(*, ctx=None, task_id=None):
            gate_calls["n"] += 1
            # Grant immediately without real sleep
            return

        mock_client = MagicMock()
        mock_client.chat.stream_async = fake_stream
        monkeypatch.setattr("mmq.Mistral", MagicMock(return_value=mock_client))
        monkeypatch.setattr("mmq._await_rate_limit_slot", fake_await_slot)

        result = await call_mistral_api("fake-key", "mistral-small-latest", [{"role": "user", "content": "x"}])
        assert result == "ok"
        assert gate_calls["n"] == 1

        with sqlite3.connect(initialized_db, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_wait_time FROM api_log WHERE id = 1")
            # After success, wait time is reset to BASE
            assert cursor.fetchone()[0] == BASE_WAIT_TIME


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


# =============================================================================
# Test Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_secure_temp_db_path(self):
        """Test secure temp DB path generation."""
        path = get_secure_temp_db_path()
        assert path.endswith("mcp_mistral_flow_control.db")
        assert "mcp_mistral_queue_" in path
