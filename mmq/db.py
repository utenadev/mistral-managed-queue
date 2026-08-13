# mmq/db.py
"""Database operations (init, task lifecycle, purge, queue status).

Note: task claiming uses SQLite ``UPDATE ... RETURNING`` (requires
SQLite >= 3.35, e.g. Python 3.10+ standard builds) so a claim is a single
atomic statement with no UPDATE-then-SELECT window.
"""

import os
import sqlite3
import tempfile
import getpass
import time
import logging
from typing import Optional

from .config import (
    BASE_WAIT_TIME,
    MAX_WAIT_TIME,
    BACKOFF_MULTIPLIER,
    MIN_SLEEP_INTERVAL,
    PROCESSING_TIMEOUT,
    DB_CONNECT_TIMEOUT,
    DB_SHORT_TIMEOUT,
)

logger = logging.getLogger("mcp-mistral-queue")

# Temp DB path
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
    # Owner-only directory (NOT world-readable). 0o700 is intentional for a
    # multi-process coordination DB; 0o644 would be less private.
    os.makedirs(base_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(base_dir, 0o700)  # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
    except Exception:
        pass

    return os.path.join(base_dir, "mcp_mistral_flow_control.db")

TEMP_DB_PATH = get_secure_temp_db_path()

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
                    prompt TEXT NOT NULL,
                    model TEXT,
                    system_prompt TEXT,
                    priority INTEGER DEFAULT 2,
                    status TEXT NOT NULL,  -- pending, processing, completed, failed
                    result TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            # Shared rate-limit gate (single row: last grant timestamp + active interval)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS api_log (
                    id INTEGER PRIMARY KEY,
                    last_executed_at REAL NOT NULL,
                    current_wait_time REAL DEFAULT 31.0
                )
                """
            )
            cursor.execute(
                "INSERT OR IGNORE INTO api_log (id, last_executed_at, current_wait_time) VALUES (1, 0.0, ?)",
                (BASE_WAIT_TIME,),
            )
            conn.commit()
    except Exception as e:
        logger.exception("DB initialization failed: %s", e)
        raise

def clean_zombie_tasks() -> None:
    """Mark timed-out processing tasks as failed; prune old failed tasks."""
    init_db()
    now = time.time()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'failed', error = 'zombie task timed out'
            WHERE status = 'processing'
              AND (updated_at + ?) < ?
            """,
            (PROCESSING_TIMEOUT, now),
        )
        cursor.execute(
            """
            DELETE FROM tasks
            WHERE status = 'failed'
              AND (updated_at + ?) < ?
            """,
            (PROCESSING_TIMEOUT * 2, now),
        )
        conn.commit()

def register_task(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    priority: int = 2,
) -> int:
    """Register a new task and return its task ID."""
    init_db()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (prompt, model, system_prompt, priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (prompt, model, system_prompt, priority, time.time(), time.time()),
        )
        conn.commit()
        return cursor.lastrowid

def claim_task(task_id: int) -> Optional[dict]:
    """Claim a specific pending task and mark it processing (or None).

    Only the task with the given ``task_id`` is claimed, and only if it is
    still ``pending``. Concurrent callers each claim *their own* task, which
    avoids the cross-claim deadlock a global highest-priority claimer causes.
    The atomic ``UPDATE ... WHERE id = ? AND status = 'pending' RETURNING``
    guarantees a task is claimed by exactly one caller.

    Args:
        task_id: The task id to claim.

    Returns:
        The task dict if claimed, else None.
    """
    init_db()
    now = time.time()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'processing', updated_at = ?
            WHERE id = ? AND status = 'pending'
            RETURNING id, prompt, model, system_prompt, priority
            """,
            (now, task_id),
        )
        row = cursor.fetchone()
        conn.commit()
        if row is None:
            return None
        return {
            "id": row[0],
            "prompt": row[1],
            "model": row[2],
            "system_prompt": row[3],
            "priority": row[4],
        }

def claim_next_task() -> Optional[dict]:
    """Atomically claim the highest-priority pending task (or None).

    Higher ``priority`` values are claimed first; ties break by task id
    (FIFO). The whole claim is a single ``UPDATE ... RETURNING`` statement,
    so concurrent workers can never claim the same task (no UPDATE-then-SELECT
    window between which another process could intervene).

    Returns:
        The task dict if any pending task exists, else None.
    """
    init_db()
    now = time.time()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = 'processing', updated_at = ?
            WHERE id = (
                SELECT id FROM tasks
                WHERE status = 'pending'
                ORDER BY priority DESC, id ASC
                LIMIT 1
            )
            RETURNING id, prompt, model, system_prompt, priority
            """,
            (now,),
        )
        row = cursor.fetchone()
        conn.commit()
        if row is None:
            return None
        return {
            "id": row[0],
            "prompt": row[1],
            "model": row[2],
            "system_prompt": row[3],
            "priority": row[4],
        }

def get_task(task_id: int) -> Optional[dict]:
    """Return a full task row (including status/result/error) or None."""
    init_db()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, prompt, model, system_prompt, priority, status, result, error "
            "FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

def touch_task(task_id: int) -> None:
    """Refresh the task's updated_at timestamp."""
    init_db()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET updated_at = ?
            WHERE id = ?
            """,
            (time.time(), task_id),
        )
        conn.commit()

def wait_for_rate_limit() -> tuple[bool, float, float]:
    """Atomically claim a slot from the shared rate-limit gate.

    Returns ``(ready, sleep_needed, current_wait_time)``. If ready, the
    gate's ``last_executed_at`` is stamped to ``now`` for all processes.
    """
    init_db()
    with sqlite3.connect(
        TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT, isolation_level=None
    ) as conn:
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
            logger.exception("Rate limit gate check failed: %s", e)
            raise


def update_rate_limit_wait_time(
    new_wait_time: float,
    *,
    stamp_executed: bool = False,
) -> None:
    """Update the shared wait time in the rate-limit gate.

    Args:
        new_wait_time: The new wait time (clamped to
            ``[MIN_SLEEP_INTERVAL, MAX_WAIT_TIME]``).
        stamp_executed: If True, also set ``last_executed_at`` to now so the
            backoff interval is measured from this moment for all processes.
    """
    clamped_wait_time = max(
        MIN_SLEEP_INTERVAL, min(new_wait_time, MAX_WAIT_TIME)
    )
    init_db()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_SHORT_TIMEOUT) as conn:
        cursor = conn.cursor()
        if stamp_executed:
            cursor.execute(
                "UPDATE api_log SET current_wait_time = ?, last_executed_at = ? WHERE id = 1",
                (clamped_wait_time, time.time()),
            )
        else:
            cursor.execute(
                "UPDATE api_log SET current_wait_time = ? WHERE id = 1",
                (clamped_wait_time,),
            )
        conn.commit()


def reset_rate_limit_wait_time() -> None:
    """Reset the shared wait time to ``BASE_WAIT_TIME``."""
    update_rate_limit_wait_time(BASE_WAIT_TIME)


def read_queue_status() -> dict:
    """Return queue status including the shared rate-limit gate state."""
    init_db()
    now = time.time()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, COUNT(*) FROM tasks GROUP BY status"
        )
        status_counts = {status: count for status, count in cursor.fetchall()}
        cursor.execute(
            "SELECT last_executed_at, current_wait_time FROM api_log WHERE id = 1"
        )
        row = cursor.fetchone()
        last_exec = float(row[0]) if row else 0.0
        wait_time = float(row[1]) if row else BASE_WAIT_TIME

    elapsed = now - last_exec
    seconds_until = max(0.0, wait_time - elapsed)
    processing = status_counts.get("processing", 0)
    return {
        "pending": status_counts.get("pending", 0),
        "processing": processing,
        "completed": status_counts.get("completed", 0),
        "failed": status_counts.get("failed", 0),
        "total": sum(status_counts.values()),
        "seconds_until_next_slot": round(seconds_until, 3),
        "current_wait_interval": wait_time,
        "in_flight": processing > 0,
    }

def update_task_status(task_id: int, status: str, result: Optional[str] = None, error: Optional[str] = None) -> None:
    """Update a task's status, result, and error."""
    init_db()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = ?, result = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, result, error, time.time(), task_id),
        )
        conn.commit()

def purge_tasks(*, pending: bool = False, all: bool = False, task_id: Optional[int] = None) -> int:
    """Delete tasks. Exactly one of pending/all/task_id must be specified."""
    init_db()
    with sqlite3.connect(TEMP_DB_PATH, timeout=DB_CONNECT_TIMEOUT) as conn:
        cursor = conn.cursor()
        if all:
            cursor.execute("DELETE FROM tasks")
        elif pending:
            cursor.execute("DELETE FROM tasks WHERE status = 'pending'")
        elif task_id is not None:
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        else:
            raise ValueError("Specify one of pending, all, or task_id")
        conn.commit()
        return cursor.rowcount