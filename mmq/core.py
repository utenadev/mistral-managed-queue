# mmq/core.py
"""Shared mmq package logic (env var helpers, Mistral wrapper, etc.)."""

import os
import asyncio
import logging
from typing import Optional, List, Dict, Any

from dataclasses import dataclass

from mistralai import Mistral

from .config import (
    BASE_WAIT_TIME,
    MAX_WAIT_TIME,
    BACKOFF_MULTIPLIER,
    MIN_SLEEP_INTERVAL,
    DEFAULT_MODEL,
    DEFAULT_SYSTEM_PROMPT,
    DB_CONNECT_TIMEOUT,
    DB_SHORT_TIMEOUT,
)
from .db import (
    register_task,
    claim_task,
    claim_next_task,
    get_task,
    touch_task,
    wait_for_rate_limit,
    update_rate_limit_wait_time,
    reset_rate_limit_wait_time,
)

logger = logging.getLogger("mcp-mistral-queue")

# ---- Env var helpers ----
def _fake_api_enabled() -> bool:
    return os.environ.get("MMQ_FAKE_API", "").strip().lower() in ("1", "true", "yes", "on")

# ---- MistralRequest and FakeMistralClient ----
@dataclass
class MistralRequest:
    """Request parameters for a Mistral API call."""
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


async def _await_rate_limit_slot(task_id: Optional[int] = None) -> None:
    """Block until the shared rate-limit gate grants an API slot."""
    while True:
        ready, sleep_needed, active_wait_time = await asyncio.to_thread(wait_for_rate_limit)
        if ready:
            return

        logger.info(
            f"Rate limiting active... {sleep_needed:.1f}s remaining "
            f"(current interval: {active_wait_time:.0f}s)"
        )
        if task_id is not None:
            await asyncio.to_thread(touch_task, task_id)
        await asyncio.sleep(min(sleep_needed, MIN_SLEEP_INTERVAL))


async def call_mistral_api(
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    task_id: Optional[int] = None,
) -> str:
    """Call Mistral API with retries and shared rate-limit enforcement (async).

    Every attempt (including the first) first waits for a slot on the shared
    rate-limit gate, so all callers — CLI ``ask``, MCP tools, the in-process
    queue — are uniformly throttled across processes. On 429/rate-limit errors
    the shared backoff is increased; the next attempt then naturally waits on
    the raised gate.
    """
    if not api_key:
        raise ValueError("Environment variable MISTRAL_API_KEY is not set.")

    client = create_mistral_client(api_key)
    api_err: Optional[Exception] = None

    for attempt in range(3):  # MAX_RETRIES could be made configurable
        full_response_text = ""
        chunk_count = 0

        # Gate every attempt through the shared rate limit (first included)
        await _await_rate_limit_slot(task_id=task_id)

        try:
            # Note: The actual SDK method may be chat.completions.create or chat.stream_async.
            # We'll use stream_async for demonstration.
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
                    if chunk_count % 5 == 0:  # PROGRESS_REPORT_INTERVAL
                        if task_id is not None:
                            await asyncio.to_thread(touch_task, task_id)

            # Success - reset shared rate limit interval to base
            await asyncio.to_thread(reset_rate_limit_wait_time)
            return full_response_text

        except Exception as err:
            api_err = err
            logger.warning(
                f"API call failed (Attempt {attempt + 1}/3): {api_err}"
            )

            if attempt >= 2:  # last attempt
                break

            if _is_rate_limit_error(err):
                # Update the shared backoff; the next loop iteration waits on
                # the raised gate before retrying.
                new_wait_time = BASE_WAIT_TIME * (BACKOFF_MULTIPLIER ** (attempt + 1))
                await asyncio.to_thread(
                    update_rate_limit_wait_time, new_wait_time, stamp_executed=True
                )
                logger.warning(
                    f"Rate limit detected, backing off to "
                    f"{min(new_wait_time, MAX_WAIT_TIME):.1f}s wait time"
                )
            else:
                await asyncio.sleep(MIN_SLEEP_INTERVAL)

    raise RuntimeError(
        f"Mistral API call failed after 3 retries: {api_err}"
    )


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Check if the error is a rate limit (429) error."""
    exc_str = str(exc).lower()
    return any(
        keyword in exc_str
        for keyword in ["429", "rate limit", "too many requests"]
    )


async def execute_mistral_queue_async(
    req: MistralRequest,
) -> str:
    """Execute a Mistral request via the internal queue.

    Steps:
      1. Register task in DB.
      2. Poll to claim this task (single worker simulation).
      3. Call Mistral API with retries (rate gate enforced inside).
      4. Update task status as completed.
    """
    # Ensure DB is initialized
    from .db import init_db
    await asyncio.to_thread(init_db)

    # 1. Register task
    task_id = await asyncio.to_thread(
        register_task,
        prompt=req.prompt,
        model=req.model,
        system_prompt=req.system_prompt,
        priority=req.priority,
    )

    try:
        # 2. Poll until this task is claimed (each caller claims only its own).
        #    If a separate ``mmq work`` worker claims it first, wait for that
        #    worker to finish and surface its result instead of hanging forever.
        while True:
            claimed = await asyncio.to_thread(claim_task, task_id)
            if claimed is not None:
                break
            task = await asyncio.to_thread(get_task, task_id)
            if task is None:
                raise RuntimeError(f"Task {task_id} was removed from the queue.")
            if task["status"] in ("completed", "failed", "cancelled"):
                if task["status"] == "completed":
                    return task.get("result") or ""
                raise RuntimeError(
                    f"Task {task_id} ended as {task['status']}: "
                    f"{task.get('error') or 'unknown error'}"
                )
            await asyncio.sleep(0.5)  # poll interval

        # 3. Call Mistral API (with retries and shared rate limiting).
        #    ``call_mistral_api`` waits on the shared rate-limit gate before
        #    every attempt, so no separate gate wait is needed here.
        messages = req.to_messages()
        result = await call_mistral_api(
            api_key=os.environ.get("MISTRAL_API_KEY", ""),
            model=req.model,
            messages=messages,
            task_id=task_id,
        )

        # 4. Update task as completed
        await asyncio.to_thread(
            update_task_status,
            task_id=task_id,
            status="completed",
            result=result,
        )
        return result

    except asyncio.CancelledError:
        # Task was cancelled
        await asyncio.to_thread(
            update_task_status,
            task_id=task_id,
            status="cancelled",
            result="Task was cancelled",
        )
        raise

    except Exception as e:
        # Unexpected error
        await asyncio.to_thread(
            update_task_status,
            task_id=task_id,
            status="failed",
            result=str(e),
        )
        raise


def update_task_status(
    task_id: int,
    status: str,
    result: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Update task status in the database."""
    # Delegate to db.py
    from .db import update_task_status as db_update_task_status
    db_update_task_status(task_id, status, result, error)


async def execute_next_task_async() -> Optional[str]:
    """Claim and process the next pending task (highest priority first).

    Returns:
        The API response text, or None if the queue was empty.

    Raises:
        RuntimeError: If the Mistral API call fails after its internal retries
            (the task is marked ``failed`` first).
    """
    task = await asyncio.to_thread(claim_next_task)
    if task is None:
        return None
    return await _process_claimed_task(task)


async def drain_queue_async() -> int:
    """Process all currently pending tasks (highest priority first).

    A task whose API call fails is marked ``failed`` and the drain continues
    with the next task, so one bad request does not stall the queue.

    Returns:
        The number of tasks processed (succeeded or failed).
    """
    from .db import init_db
    await asyncio.to_thread(init_db)
    count = 0
    while True:
        task = await asyncio.to_thread(claim_next_task)
        if task is None:
            break
        count += 1
        try:
            await _process_claimed_task(task)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Task %s failed; continuing", task["id"])
    return count


async def watch_queue_async(poll_interval: float = 2.0) -> None:
    """Continuously process pending tasks as they arrive (until cancelled).

    Exits cleanly on ``asyncio.CancelledError``.
    """
    while True:
        processed = await drain_queue_async()
        if processed == 0:
            await asyncio.sleep(poll_interval)


async def _process_claimed_task(task: dict) -> str:
    """Run one claimed task through the API and update its status."""
    task_id = task["id"]
    req = MistralRequest(
        prompt=task["prompt"],
        model=task["model"] or DEFAULT_MODEL,
        system_prompt=task["system_prompt"],
    )
    try:
        result = await call_mistral_api(
            api_key=os.environ.get("MISTRAL_API_KEY", ""),
            model=req.model,
            messages=req.to_messages(),
            task_id=task_id,
        )
        await asyncio.to_thread(
            update_task_status,
            task_id=task_id,
            status="completed",
            result=result,
        )
        return result
    except asyncio.CancelledError:
        await asyncio.to_thread(
            update_task_status,
            task_id=task_id,
            status="cancelled",
            result="Task was cancelled",
        )
        raise
    except Exception as e:
        await asyncio.to_thread(
            update_task_status,
            task_id=task_id,
            status="failed",
            result=None,
            error=str(e),
        )
        raise


def read_queue_status() -> dict:
    """Read queue status from the database."""
    from .db import read_queue_status as db_read_queue_status
    return db_read_queue_status()


# ---- Public API ----
__all__ = [
    # Constants
    "BASE_WAIT_TIME",
    "MAX_WAIT_TIME",
    "BACKOFF_MULTIPLIER",
    "MIN_SLEEP_INTERVAL",
    "DEFAULT_MODEL",
    "DEFAULT_SYSTEM_PROMPT",
    "DB_CONNECT_TIMEOUT",
    "DB_SHORT_TIMEOUT",
    # Classes
    "MistralRequest",
    "FakeMistralClient",
    # Functions
    "create_mistral_client",
    "call_mistral_api",
    "execute_mistral_queue_async",
    "execute_next_task_async",
    "drain_queue_async",
    "watch_queue_async",
    "update_task_status",
    "read_queue_status",
]