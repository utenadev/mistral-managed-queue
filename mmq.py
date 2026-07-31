# /// script
# dependencies = [
#     "mcp[cli]>=1.0.0,<2",
#     "mistralai>=1.0.0,<2",
# ]
# ///

import argparse
import asyncio
import getpass
import json
import logging
import os
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import Context, FastMCP
from mistralai import Mistral

# === Constant Configuration (env overrides for tests / local tuning) ===


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


# Rate limiting constants
BASE_WAIT_TIME = _env_float("MMQ_BASE_WAIT_TIME", 31.0)  # free tier ~1 req/30s
MAX_WAIT_TIME = _env_float("MMQ_MAX_WAIT_TIME", 300.0)
BACKOFF_MULTIPLIER = _env_float("MMQ_BACKOFF_MULTIPLIER", 2.0)
MIN_SLEEP_INTERVAL = _env_float("MMQ_MIN_SLEEP_INTERVAL", 2.0)

# Task management constants
PROCESSING_TIMEOUT = _env_float("MMQ_PROCESSING_TIMEOUT", 120.0)
TASK_POLL_INTERVAL = _env_float("MMQ_TASK_POLL_INTERVAL", 1.0)
MAX_RETRIES = _env_int("MMQ_MAX_RETRIES", 3)

# Streaming constants
PROGRESS_REPORT_INTERVAL = _env_int("MMQ_PROGRESS_REPORT_INTERVAL", 5)

# Model defaults
DEFAULT_MODEL = os.environ.get("MMQ_DEFAULT_MODEL", "mistral-small-latest")
DEFAULT_SYSTEM_PROMPT = "You are a helpful, respectful, and honest assistant."

# Database constants
DB_CONNECT_TIMEOUT = _env_float("MMQ_DB_CONNECT_TIMEOUT", 30.0)
DB_SHORT_TIMEOUT = _env_float("MMQ_DB_SHORT_TIMEOUT", 10.0)

# === Logging Setup ===
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("mcp-mistral-queue")

__all__ = [
    "MistralRequest",
    "execute_mistral_queue_async",
    "ask_mistral",
    "get_queue_status",
]


@dataclass
class MistralRequest:
    """Parameters for a single Mistral API request."""

    prompt: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    model: str = DEFAULT_MODEL
    system_prompt: Optional[str] = None
    priority: int = 2

    def to_messages(self) -> List[Dict[str, Any]]:
        """Build the ``messages`` array for the Mistral API.

        Exactly one of ``prompt`` or ``messages`` must be set.
        """
        if self.prompt is not None and self.messages is not None:
            raise ValueError("Specify only one of `prompt` or `messages`, not both.")
        if self.messages:
            return self.messages
        if self.prompt:
            sys_content = self.system_prompt or DEFAULT_SYSTEM_PROMPT
            return [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": self.prompt},
            ]
        raise ValueError("Specify either `prompt` or `messages`.")


def get_secure_temp_db_path() -> str:
    """Build a temp DB path under a per-user directory (mode ``0700``).

    Override with ``MMQ_TEMP_DB_PATH`` (full file path) for tests / isolation.
    """
    override = os.environ.get("MMQ_TEMP_DB_PATH")
    if override:
        parent = os.path.dirname(os.path.abspath(override)) or "."
        os.makedirs(parent, mode=0o700, exist_ok=True)
        return override

    user = getpass.getuser()
    base_dir = os.path.join(tempfile.gettempdir(), f"mcp_mistral_queue_{user}")
    os.makedirs(base_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(base_dir, 0o700)
    except Exception:
        pass

    return os.path.join(base_dir, "mcp_mistral_flow_control.db")


TEMP_DB_PATH = get_secure_temp_db_path()
mcp = FastMCP("mcp-mistral-queue")


def _fake_api_enabled() -> bool:
    return os.environ.get("MMQ_FAKE_API", "").strip().lower() in ("1", "true", "yes", "on")


class FakeMistralClient:
    """Deterministic stand-in for ``mistralai.Mistral`` (e2e / offline).

    Env:
      MMQ_FAKE_RESPONSE  fixed response text (default: echo last user message)
      MMQ_FAKE_FAIL      ``429`` or ``error`` to raise before streaming
    """

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key
        self.chat = self

    async def stream_async(self, model: str, messages: List[Dict[str, Any]], **kwargs: Any):
        fail = os.environ.get("MMQ_FAKE_FAIL", "").strip().lower()
        if fail in ("429", "rate_limit", "ratelimit"):
            raise Exception("429 Too Many Requests")
        if fail in ("error", "1", "true"):
            raise Exception("MMQ_FAKE_FAIL simulated error")

        fixed = os.environ.get("MMQ_FAKE_RESPONSE")
        if fixed is not None and fixed != "":
            text = fixed
        else:
            text = "fake-ok"
            for msg in reversed(messages or []):
                if msg.get("role") == "user":
                    text = f"echo:{msg.get('content', '')}"
                    break

        class _Delta:
            def __init__(self, content: str) -> None:
                self.content = content

        class _Choice:
            def __init__(self, content: str) -> None:
                self.delta = _Delta(content)

        class _Chunk:
            def __init__(self, content: str) -> None:
                self.choices = [_Choice(content)]

        async def _gen():
            yield _Chunk(text)

        return _gen()


def create_mistral_client(api_key: str):
    """Return a real or fake Mistral client based on ``MMQ_FAKE_API``."""
    if _fake_api_enabled():
        logger.info("MMQ_FAKE_API enabled: using FakeMistralClient")
        return FakeMistralClient(api_key=api_key)
    return Mistral(api_key=api_key)


def init_db() -> None:
    """Initialize the temporary management database structure."""
    try:
        with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            
            # Create tasks table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt_summary TEXT NOT NULL,
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """
            )
            
            # Create api_log table
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS api_log (
                    id INTEGER PRIMARY KEY,
                    last_executed_at REAL NOT NULL,
                    current_wait_time REAL DEFAULT {BASE_WAIT_TIME}
                )
            """
            )
            
            # Initialize api_log with default values
            cursor.execute(
                "INSERT OR IGNORE INTO api_log (id, last_executed_at, current_wait_time) VALUES (1, 0.0, ?)",
                (BASE_WAIT_TIME,),
            )
            conn.commit()
            logger.debug("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise


def clean_zombie_tasks() -> int:
    """Clean up zombie tasks that are stuck in processing state.
    
    Args:
        None
        
    Returns:
        Number of tasks cleaned up
    """
    try:
        cutoff = time.time() - PROCESSING_TIMEOUT
        with sqlite3.connect(TEMP_DB_PATH, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tasks
                SET status = 'failed', result = 'Timeout: Process crashed or unresponsive'
                WHERE status = 'processing' AND updated_at < ?
                """,
                (cutoff,),
            )
            cleaned_count = cursor.rowcount
            conn.commit()
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} zombie task(s)")
            return cleaned_count
    except Exception as e:
        logger.error(f"Failed to clean zombie tasks: {e}", exc_info=True)
        raise


# === Helper Functions for Task Management ===

async def register_task(req: MistralRequest) -> int:
    """Register a new task in the queue.
    
    Args:
        req: MistralRequest containing task parameters
        
    Returns:
        The assigned task ID
    """
    await asyncio.to_thread(clean_zombie_tasks)
    summary = (
        (req.prompt or "")[:30]
        if req.prompt
        else (f"Messages ({len(req.messages)})" if req.messages else "Task")
    )
    now = time.time()
    
    def _do_register():
        with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (prompt_summary, priority, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (summary, req.priority, now, now),
            )
            task_id = cursor.lastrowid
            conn.commit()
            return task_id
    
    task_id = await asyncio.to_thread(_do_register)
    logger.info(f"Task registered (ID: {task_id}, Model: {req.model}, Priority: {req.priority})")
    return task_id


async def claim_task(task_id: int) -> bool:
    """Try to claim a task for exclusive processing (single in-flight).

    A task may be claimed only when:
    1. No other task is currently ``processing``, and
    2. This task is the head of the pending queue (priority ASC, id ASC).
    """
    def _do_claim():
        with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status = 'processing'"
                )
                in_flight = cursor.fetchone()[0]
                if in_flight > 0:
                    conn.rollback()
                    return False

                cursor.execute(
                    "SELECT id FROM tasks WHERE status = 'pending' "
                    "ORDER BY priority ASC, id ASC LIMIT 1"
                )
                next_task = cursor.fetchone()

                if next_task and next_task[0] == task_id:
                    cursor.execute(
                        "UPDATE tasks SET status = 'processing', updated_at = ? WHERE id = ?",
                        (time.time(), task_id),
                    )
                    conn.commit()
                    return True
                else:
                    conn.rollback()
                    return False
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to claim task {task_id}: {e}")
                raise

    return await asyncio.to_thread(_do_claim)


async def touch_task(task_id: int) -> None:
    """Heartbeat: refresh updated_at so zombie cleanup does not kill live work."""

    def _do_touch():
        with sqlite3.connect(TEMP_DB_PATH, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET updated_at = ? WHERE id = ? AND status = 'processing'",
                (time.time(), task_id),
            )
            conn.commit()

    await asyncio.to_thread(_do_touch)


async def wait_for_rate_limit() -> tuple[bool, float, float]:
    """Wait for rate limit to allow API call.
    
    Returns:
        Tuple of (ready: bool, sleep_needed: float, current_wait_time: float)
    """
    def _check_limit():
        with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute(
                    "SELECT last_executed_at, current_wait_time FROM api_log WHERE id = 1"
                )
                row = cursor.fetchone()
                last_exec = row[0] if row else 0.0
                wait_time = row[1] if row else BASE_WAIT_TIME
                
                elapsed = time.time() - last_exec
                if elapsed >= wait_time:
                    cursor.execute(
                        "UPDATE api_log SET last_executed_at = ? WHERE id = 1",
                        (time.time(),),
                    )
                    conn.commit()
                    return True, 0.0, wait_time
                else:
                    conn.rollback()
                    return False, wait_time - elapsed, wait_time
            except Exception as e:
                conn.rollback()
                logger.error(f"Rate limit check failed: {e}")
                raise
    
    return await asyncio.to_thread(_check_limit)


async def update_rate_limit_wait_time(
    new_wait_time: float,
    *,
    stamp_executed: bool = False,
) -> None:
    """Update the current wait time in the rate limit log.

    Args:
        new_wait_time: The new wait time to set (capped at MAX_WAIT_TIME)
        stamp_executed: If True, also set last_executed_at to now so the
            backoff interval is measured from this moment for all processes.
    """
    capped_wait_time = min(new_wait_time, MAX_WAIT_TIME)
    now = time.time()

    def _do_update():
        with sqlite3.connect(TEMP_DB_PATH, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            if stamp_executed:
                cursor.execute(
                    "UPDATE api_log SET current_wait_time = ?, last_executed_at = ? WHERE id = 1",
                    (capped_wait_time, now),
                )
            else:
                cursor.execute(
                    "UPDATE api_log SET current_wait_time = ? WHERE id = 1",
                    (capped_wait_time,),
                )
            conn.commit()

    await asyncio.to_thread(_do_update)
    logger.info(f"Rate limit wait time updated to {capped_wait_time:.1f}s")


async def reset_rate_limit_wait_time() -> None:
    """Reset the rate limit wait time to base value."""
    await update_rate_limit_wait_time(BASE_WAIT_TIME)


def is_rate_limit_error(error: Exception) -> bool:
    """Check if the error is a rate limit (429) error.
    
    Args:
        error: The exception to check
        
    Returns:
        True if it's a rate limit error
    """
    error_str = str(error).lower()
    return any(keyword in error_str for keyword in ["429", "rate limit", "too many requests"])


async def _await_rate_limit_slot(
    ctx: Optional[Context] = None,
    task_id: Optional[int] = None,
) -> None:
    """Block until the shared rate-limit gate grants an API slot."""
    while True:
        ready, sleep_needed, active_wait_time = await wait_for_rate_limit()
        if ready:
            return

        logger.info(
            f"Rate limiting active... {sleep_needed:.1f}s remaining "
            f"(current interval: {active_wait_time:.0f}s)"
        )
        if ctx:
            await ctx.info(
                f"Rate limiting active... {sleep_needed:.1f}s remaining "
                f"(current interval: {active_wait_time:.0f}s)"
            )
        if task_id is not None:
            await touch_task(task_id)
        await asyncio.sleep(min(sleep_needed, MIN_SLEEP_INTERVAL))


async def call_mistral_api(
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    ctx: Optional[Context] = None,
    task_id: Optional[int] = None,
) -> str:
    """Call Mistral API with streaming, retries, and shared rate-limit re-entry.

    On 429/rate-limit errors the shared backoff is updated and the process
    re-enters ``wait_for_rate_limit`` before the next attempt (not a fixed 2s sleep).
    Response buffers are reset at the start of each attempt.
    """
    client = create_mistral_client(api_key)
    api_err: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        # Issue 3: never concatenate partial stream from a failed attempt
        full_response_text = ""
        chunk_count = 0

        try:
            response_stream = await client.chat.stream_async(
                model=model,
                messages=messages,
            )

            async for chunk in response_stream:
                chunk_text = ""
                # Handle both possible chunk structures (SDK version compatibility)
                if hasattr(chunk, "data") and chunk.data and hasattr(chunk.data, "choices"):
                    chunk_text = chunk.data.choices[0].delta.content or ""
                elif hasattr(chunk, "choices") and chunk.choices:
                    chunk_text = chunk.choices[0].delta.content or ""

                if chunk_text:
                    full_response_text += chunk_text
                    chunk_count += 1
                    if chunk_count % PROGRESS_REPORT_INTERVAL == 0:
                        if ctx:
                            await ctx.report_progress(chunk_count, 100)
                        # Issue 5: heartbeat so long streams are not zombied
                        if task_id is not None:
                            await touch_task(task_id)

            # Success - reset rate limit interval to base
            await reset_rate_limit_wait_time()
            return full_response_text

        except Exception as err:
            api_err = err
            logger.warning(
                f"API call failed (Attempt {attempt + 1}/{MAX_RETRIES}): {api_err}"
            )

            if attempt >= MAX_RETRIES - 1:
                break

            # Issue 1+8: rate-limit errors update shared backoff and re-enter the gate
            if is_rate_limit_error(api_err):
                new_wait_time = BASE_WAIT_TIME * (BACKOFF_MULTIPLIER ** (attempt + 1))
                await update_rate_limit_wait_time(new_wait_time, stamp_executed=True)
                logger.warning(
                    f"Rate limit detected, backing off to "
                    f"{min(new_wait_time, MAX_WAIT_TIME):.1f}s wait time"
                )
                await _await_rate_limit_slot(ctx=ctx, task_id=task_id)
            else:
                await asyncio.sleep(MIN_SLEEP_INTERVAL)

    raise RuntimeError(
        f"Mistral API call failed after {MAX_RETRIES} retries: {api_err}"
    )


async def update_task_status(
    task_id: int,
    status: str,
    result: Optional[str] = None,
) -> None:
    """Update task status in the database.
    
    Args:
        task_id: The task ID to update
        status: New status ('pending', 'processing', 'completed', 'failed', 'cancelled')
        result: Optional result text
    """
    def _do_update():
        with sqlite3.connect(TEMP_DB_PATH, timeout=DB_SHORT_TIMEOUT) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                (status, result or "", time.time(), task_id),
            )
            conn.commit()
    
    await asyncio.to_thread(_do_update)
    logger.debug(f"Task {task_id} status updated to '{status}'")


# === Main Execution Logic ===

async def execute_mistral_queue_async(
    req: MistralRequest,
    ctx: Optional[Context] = None,
) -> str:
    """Core logic: Priority queue, async rate limiting, streaming, cancel handling.
    
    Args:
        req: MistralRequest containing all parameters
        ctx: Optional MCP context
        
    Returns:
        The response text from Mistral API
        
    Raises:
        ValueError: If MISTRAL_API_KEY is not set
        asyncio.CancelledError: If task is cancelled
        RuntimeError: If API call fails after retries
    """
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise ValueError("Environment variable MISTRAL_API_KEY is not set.")
    
    await asyncio.to_thread(init_db)
    final_messages = req.to_messages()
    
    # 1. Register task
    my_task_id = await register_task(req)

    try:
        # 2. Wait for exclusive turn (priority queue + single in-flight)
        logger.info(f"Waiting for task {my_task_id} to reach front of queue...")
        while True:
            claimed = await claim_task(my_task_id)
            if claimed:
                break
            await asyncio.sleep(TASK_POLL_INTERVAL)

        # 3. Wait for shared rate-limit slot (stamps last_executed_at when granted)
        logger.info(f"Task {my_task_id} claimed, waiting for rate limit...")
        await _await_rate_limit_slot(ctx=ctx, task_id=my_task_id)

        # 4. Call Mistral API (retries re-enter rate-limit gate on 429)
        logger.info(f"Calling Mistral API (Model: {req.model})...")
        if ctx:
            await ctx.info(f"Starting Mistral API ({req.model}) call...")

        full_response_text = await call_mistral_api(
            api_key=api_key,
            model=req.model,
            messages=final_messages,
            ctx=ctx,
            task_id=my_task_id,
        )

        # 5. Update task as completed
        await update_task_status(my_task_id, "completed", full_response_text)
        return full_response_text

    except asyncio.CancelledError:
        # Task was cancelled
        await update_task_status(my_task_id, "cancelled", "Task was cancelled")
        logger.info(f"Task {my_task_id} was cancelled")
        raise

    except Exception as e:
        # Unexpected error
        await update_task_status(my_task_id, "failed", str(e))
        logger.error(f"Task {my_task_id} failed: {e}", exc_info=True)
        raise


def read_queue_status() -> Dict[str, Any]:
    """Snapshot of queue and shared rate-limit state (read-only).

    Ensures the DB schema exists, then returns:
      pending, processing, seconds_until_next_slot, current_wait_interval, in_flight
    """
    init_db()
    now = time.time()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_SHORT_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'pending'"
        )
        pending = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'processing'"
        )
        processing = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT last_executed_at, current_wait_time FROM api_log WHERE id = 1"
        )
        row = cursor.fetchone()
        last_exec = float(row[0]) if row else 0.0
        wait_time = float(row[1]) if row else BASE_WAIT_TIME

    elapsed = now - last_exec
    seconds_until = max(0.0, wait_time - elapsed)
    return {
        "pending": pending,
        "processing": processing,
        "seconds_until_next_slot": round(seconds_until, 3),
        "current_wait_interval": wait_time,
        "in_flight": processing > 0,
    }


# MCP Tool Registration
@mcp.tool()
async def ask_mistral(
    ctx: Optional[Context] = None,
    prompt: Optional[str] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    model: str = DEFAULT_MODEL,
    system_prompt: Optional[str] = None,
    priority: int = 2,
) -> str:
    """Call the Mistral API with queuing and shared rate-limit control.

    Args:
        ctx: MCP context (injected automatically by the host).
        prompt: Single-shot user prompt text.
        messages: Conversation history
            (``[{"role": "...", "content": "..."}]``).
        model: Mistral model name (default: ``mistral-small-latest``).
        system_prompt: Custom system prompt (only used with ``prompt``).
        priority: Task priority (1: high, 2: normal, 3: low).

    Returns:
        Response text from the Mistral API.
    """
    req = MistralRequest(
        prompt=prompt,
        messages=messages,
        model=model,
        system_prompt=system_prompt,
        priority=priority,
    )
    return await execute_mistral_queue_async(req, ctx)


@mcp.tool()
async def get_queue_status() -> str:
    """Return current shared queue and rate-limit status as JSON.

    Fields:
        pending: tasks waiting in the queue
        processing: tasks currently claimed / running
        seconds_until_next_slot: seconds until the shared API gate opens
        current_wait_interval: active shared wait interval in seconds
        in_flight: whether any task is currently processing
    """
    status = await asyncio.to_thread(read_queue_status)
    return json.dumps(status)


def parse_messages_json(messages_str: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """Parse a JSON string into a ``messages`` array."""
    if messages_str is None:
        return None
    try:
        return json.loads(messages_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid messages JSON: {e}")


def purge_tasks(
    *,
    pending: bool = False,
    processing: bool = False,
    task_id: Optional[int] = None,
) -> int:
    """Cancel matching tasks (set status to ``cancelled``).

    Exactly one mode must be used:
      - ``task_id``: cancel that row if present
      - ``pending`` only: cancel all pending
      - ``pending`` and ``processing``: cancel pending + processing (purge-all)

    Returns:
        Number of rows updated.
    """
    if task_id is not None and (pending or processing):
        raise ValueError("Cannot combine task_id with pending/processing filters.")
    if task_id is None and not pending and not processing:
        raise ValueError("Specify task_id and/or pending/processing filters.")

    init_db()
    now = time.time()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        if task_id is not None:
            cursor.execute(
                "UPDATE tasks SET status = 'cancelled', result = ?, updated_at = ? "
                "WHERE id = ? AND status IN ('pending', 'processing')",
                ("Purged by task id", now, task_id),
            )
        else:
            statuses: List[str] = []
            if pending:
                statuses.append("pending")
            if processing:
                statuses.append("processing")
            placeholders = ",".join("?" * len(statuses))
            cursor.execute(
                f"UPDATE tasks SET status = 'cancelled', result = ?, updated_at = ? "
                f"WHERE status IN ({placeholders})",
                ("Purged", now, *statuses),
            )
        count = cursor.rowcount
        conn.commit()
    return int(count or 0)


def start_mcp_server() -> None:
    """Start the MCP server on stdio (``FastMCP.run`` is a sync API)."""
    mcp.run(transport="stdio")


async def run_cli(args) -> int:
    """Run in CLI mode."""
    messages = parse_messages_json(args.messages)
    
    req = MistralRequest(
        prompt=args.prompt,
        messages=messages,
        model=args.model,
        system_prompt=args.system_prompt,
        priority=args.priority,
    )
    
    try:
        result = await execute_mistral_queue_async(req)
        print(result)
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def run_purge(args) -> int:
    """Handle --purge / --purge-all / --purge-id CLI modes."""
    modes = sum(
        [
            bool(args.purge),
            bool(args.purge_all),
            args.purge_id is not None,
        ]
    )
    if modes != 1:
        print(
            "Error: specify exactly one of --purge, --purge-all, or --purge-id",
            file=sys.stderr,
        )
        return 2
    try:
        if args.purge_id is not None:
            n = purge_tasks(task_id=args.purge_id)
        elif args.purge_all:
            n = purge_tasks(pending=True, processing=True)
        else:
            n = purge_tasks(pending=True)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Cancelled {n} task(s).")
    return 0


def main():
    """CLI / MCP entry point."""
    parser = argparse.ArgumentParser(
        description="Mistral API Queue - CLI mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic run (CLI)
  uv run mmq.py "Explain Python briefly"

  # Choose a model
  uv run mmq.py -m mistral-large-latest "Explain this algorithm"

  # Emergency brake: cancel queued work
  uv run mmq.py --purge
  uv run mmq.py --purge-all
  uv run mmq.py --purge-id 42

  # MCP server mode (register with Vibe / Claude Desktop / etc.)
  uv run mmq.py --mcp
""",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Input prompt text",
    )
    parser.add_argument(
        "-m", "--model",
        default=DEFAULT_MODEL,
        help=f"Model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "-s", "--system-prompt",
        default=None,
        help="System prompt",
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Task priority (1: high, 2: normal, 3: low) (default: 2)",
    )
    parser.add_argument(
        "--messages",
        default=None,
        help="Messages array as a JSON string",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Start in MCP server mode",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Cancel all pending tasks (emergency brake)",
    )
    parser.add_argument(
        "--purge-all",
        action="store_true",
        help="Cancel all pending and processing tasks",
    )
    parser.add_argument(
        "--purge-id",
        type=int,
        default=None,
        metavar="ID",
        help="Cancel a single task by ID",
    )
    
    args = parser.parse_args()
    
    if args.mcp:
        start_mcp_server()
    elif args.purge or args.purge_all or args.purge_id is not None:
        sys.exit(run_purge(args))
    elif args.prompt is None and args.messages is None:
        parser.print_help()
        sys.exit(1)
    else:
        sys.exit(asyncio.run(run_cli(args)))


if __name__ == "__main__":
    main()
