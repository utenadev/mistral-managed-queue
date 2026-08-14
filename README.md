# mistral-managed-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

[![PyPI](https://img.shields.io/pypi/v/mistral-managed-queue)](https://pypi.org/project/mistral-managed-queue/)

A CLI tool and MCP (Model Context Protocol) server that coordinates local and multi-process / multi-client calls to the Mistral free tier (~1 request / 30 seconds) via a shared SQLite queue.
It uses SQLite (WAL mode) and async queueing with a single in-flight task to space request starts. This is best-effort traffic control, not an official SLA.

**Package:** [`mistral-managed-queue`](https://pypi.org/project/mistral-managed-queue/) on PyPI · **console script:** `mmq` (not the package name) · **current release:** `0.2.0`

## Features

 * **Automatic rate-limit coordination**: Shared ~31s start interval; on 429, shared backoff then re-enter the gate. Resets to the base interval on success.
 * **Multi-process & priority control**: Multiple processes/tasks can enqueue work. Priority (default 2; larger value is processed first) plus single in-flight processing order the queue.
 * **Flexible model & message options**: Any Mistral chat model name (defaults to `mistral-small-latest`; e.g. `mistral-large-latest`, `codestral-latest`).
 * **Streaming & cancel handling**: Streams the Mistral API response internally (the tool returns the full text); on client cancel (`CancelledError`) updates task status in the DB.
 * **Local control DB**: Temp DB under a per-user directory with mode `0700` (path overridable via `MMQ_TEMP_DB_PATH`).
 * **PyPI / uvx**: Install once or run ephemerally; entry point is `mmq`.
 * **Catalog fetching**: Fetch and cache model catalogs from providers (OpenRouter, NVIDIA NIM, Mistral) with `mmq catalog fetch` (requires `pip install mistral-managed-queue[catalog]`).
 * **Good free-tier fit**: Occasional jobs (e.g. translating docs) that can wait ~31s between calls without burning a dedicated rate-limit stack.

## Prerequisites

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) recommended (`uvx` / `uv run`); `pip` also works
 * A Mistral API key (`MISTRAL_API_KEY`)

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```

## Install (PyPI)

Published and verified on [PyPI](https://pypi.org/project/mistral-managed-queue/).

```bash
# One-shot (no permanent install) — recommended for MCP hosts
uvx --from mistral-managed-queue mmq --help

# Or install into an environment
uv pip install mistral-managed-queue
# pip install mistral-managed-queue

mmq --help
```

**Quick smoke (needs `MISTRAL_API_KEY`; counts against free-tier quota):**

```bash
uvx --from mistral-managed-queue mmq ask "Reply with pong only."
```

**Notes:**

 * Console script name is **`mmq`**. Wrong: `uvx mistral-managed-queue ...`. Right: `uvx --from mistral-managed-queue mmq ...`.
 * Core dependencies: `mcp[cli]>=1.0.0,<2`, `mistralai>=1.0.0,<2`. Catalog fetching needs `httpx` and `PyYAML` (install with `pip install mistral-managed-queue[catalog]`).

## Usage

The CLI is subcommand-based: `mmq ask`, `mmq fetch`, `mmq work`, `mmq purge`, `mmq catalog`, `mmq mcp`.

### 1. `ask` — direct API call (bypasses the queue)

Sends the prompt to the Mistral API immediately and prints the response.

```bash
# Basic run (default model: mistral-small-latest)
uvx --from mistral-managed-queue mmq ask "Explain Python list comprehensions briefly"
# or: mmq ask "Explain Python list comprehensions briefly"

# Choose a model (e.g. mistral-large-latest, codestral-latest)
mmq ask -m mistral-large-latest "Explain a complex algorithm"

# Custom system prompt
mmq ask -s "You are an AI that speaks casually." "How is the weather today?"

# JSON output for easy parsing
mmq ask -j "What is ownership in Rust?"
```

### 2. `fetch` — enqueue for asynchronous processing

Registers the prompt in the shared queue. It is **not** processed here — run
`mmq work` to drain the queue.

```bash
# Enqueue with default priority (2)
mmq fetch "Summarize this document"

# Choose a model / system prompt / priority
mmq fetch -m mistral-large-latest -s "Be concise" -p 1 "Translate this to Japanese"
```

**Priority**: larger value is processed first (`ORDER BY priority DESC`). Default is `2`.

### 3. `work` — process the queue (worker mode)

Claims and processes pending tasks in priority order (highest first; FIFO within
the same priority), each through the shared rate gate.

```bash
mmq work            # drain all currently pending tasks
mmq work --once     # process exactly one task and exit
mmq work --watch    # keep processing new tasks until interrupted (Ctrl-C)
```

### 4. `purge` — cancel queued tasks

```bash
mmq purge --pending   # delete all pending tasks
mmq purge --all       # delete every task (including completed/failed)
mmq purge --id 42     # delete a specific task by ID
```

### 5. `catalog fetch` — fetch provider model catalogs

Fetch and cache model catalogs from providers (OpenRouter, NVIDIA NIM, Mistral). Requires `httpx` and `PyYAML` (install with: `pip install mistral-managed-queue[catalog]`).

```bash
# Install with catalog extras first (if not using full install)
# pip install mistral-managed-queue[catalog]

# Fetch from all enabled providers and write to ./models.yaml (default)
mmq catalog fetch

# Specify output file
mmq catalog fetch -o ./my-catalog.yaml

# Skip validation
mmq catalog fetch --no-validate
```

Catalog fetching uses its own rate limiting, tuned independently from the chat API via `MMQ_CATALOG_BASE_WAIT_TIME` and `MMQ_CATALOG_MAX_WAIT_TIME`. If unset, they fall back to `MMQ_BASE_WAIT_TIME` / `MMQ_MAX_WAIT_TIME`.

### 6. `mcp` — MCP server control

Only available when MCP is enabled (set `MMQ_ENABLE_MCP=true`).

```bash
MMQ_ENABLE_MCP=true mmq mcp run      # start the MCP server
MMQ_ENABLE_MCP=true mmq mcp status   # show MCP availability
```

### 7. MCP server mode (Vibe / Grok / Claude Desktop / …)

Expose **`ask_mistral`** and **`get_queue_status`** to MCP hosts.

MCP is **opt-in**: set `MMQ_ENABLE_MCP=true` (values: `1` / `true` / `yes` / `on`) in the host environment, then run `mmq mcp run`.

#### PyPI / uvx (recommended)

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "uvx",
      "args": ["--from", "mistral-managed-queue", "mmq", "mcp", "run"],
      "env": {
        "MMQ_ENABLE_MCP": "true",
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

If `mmq` is already on `PATH` (venv / `uv pip install`):

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "mmq",
      "args": ["mcp", "run"],
      "env": {
        "MMQ_ENABLE_MCP": "true",
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

#### Local checkout (development)

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp[cli]>=1.0.0,<2",
        "--with", "mistralai>=1.0.0,<2",
        "--no-project",
        "python", "-m", "mmq.cli", "mcp", "run"
      ],
      "env": {
        "MMQ_ENABLE_MCP": "true",
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

After changing config, restart the client. Manual Vibe checklist: [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

### 3. Environment variables (optional)

| Variable | Default | Purpose |
|---|---|---|
| `MISTRAL_API_KEY` | (required) | Mistral API key |
| `MMQ_TEMP_DB_PATH` | per-user under tempdir | Shared queue DB file path |
| `MMQ_BASE_WAIT_TIME` | `31` | Seconds between starts (free-tier pacing) |
| `MMQ_MAX_WAIT_TIME` | `300` | Max backoff wait |
| `MMQ_MIN_SLEEP_INTERVAL` | `2` | Min sleep between retries |
| `MMQ_BACKOFF_MULTIPLIER` | `2.0` | Backoff multiplier on 429 |
| `MMQ_PROCESSING_TIMEOUT` | `120` | Zombie task timeout (seconds) |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | Default model name |
| `MMQ_ENABLE_MCP` | off | Enable MCP server / `mcp` subcommands (`1`/`true`) |
| `MMQ_CATALOG_BASE_WAIT_TIME` | `MMQ_BASE_WAIT_TIME` | Catalog fetch pacing |
| `MMQ_CATALOG_MAX_WAIT_TIME` | `MMQ_MAX_WAIT_TIME` | Catalog fetch max backoff |
| `MMQ_FAKE_API` | off | Offline / e2e: fake client (`1`/`true`) |
| `MMQ_FAKE_RESPONSE` | — | Fixed fake response text (testing) |
| `MMQ_FAKE_FAIL` | — | `429` or `error` to simulate failure (testing) |

### MCP tools

When the server is running, clients can use the following tools:

#### `ask_mistral`

| Argument | Type | Default | Description |
|---|---|---|---|
| prompt | string | required | User prompt text |
| model | string | `"mistral-small-latest"` | Mistral model name |
| system_prompt | string | null | Custom system prompt |

#### `get_queue_status`

Returns current shared queue status as JSON:

| Field | Type | Description |
|---|---|---|
| pending | number | Tasks waiting in the queue |
| processing | number | Tasks currently claimed / running |
| completed | number | Tasks finished |
| failed | number | Tasks failed |
| total | number | Total tasks |
| seconds_until_next_slot | number | Seconds until the rate gate grants the next slot |
| current_wait_interval | number | Current shared wait interval (after backoff) |
| in_flight | boolean | True if any task is currently processing |

## Control data location

The coordination temp DB is stored in a per-user directory created with mode `0700`:

 * Default: `<tempdir>/mistral_managed_queue_<USER>/mistral_managed_flow_control.db`  
   (`tempfile.gettempdir()`, often `/tmp` on Linux)
 * Override: set `MMQ_TEMP_DB_PATH` to a full file path (parent dir is created with `0700`)

## Tests

```bash
# Unit + e2e (fake API; no network required)
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/ -v -m "not live"

# e2e only
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e -v -m "not live"

# Live API (optional; consumes free-tier quota)
export MISTRAL_API_KEY=...
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e/test_live_api.py -v -m live
```

e2e uses `MMQ_FAKE_API=1` and a short `MMQ_BASE_WAIT_TIME` to exercise process boundaries (CLI / MCP stdio).
For a manual Vibe UI check, see [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

## Example: batch-style use of mmq (`scripts/translate_readme.py`)

Besides the CLI and MCP server, you can call the queue from Python. This repo ships a small sample:

**[`scripts/translate_readme.py`](scripts/translate_readme.py)** — regenerate locale READMEs from the English source via the **same free-tier queue** as `mmq` / `ask_mistral`.

| Idea | Why it fits mmq |
|------|-----------------|
| Occasional job | Docs change far less often than chat traffic |
| Can wait ~31s | ja then fr each take a gated slot |
| Shared DB | Does not bypass other free-tier clients on the machine |
| Programmatic API | Uses `execute_mistral_queue_async` + `MistralRequest` |

**Locales workflow:** edit **`README.md` (English) only**; do not hand-maintain `README.ja.md` / `README.fr.md`.

```bash
export MISTRAL_API_KEY=...
# optional: TRANSLATE_MODEL=mistral-small-latest

# From a git checkout (imports the mmq package on PYTHONPATH via the script)
python scripts/translate_readme.py              # → README.ja.md + README.fr.md
python scripts/translate_readme.py --lang ja    # one language
python scripts/translate_readme.py --dry-run    # preview, no write
```

What the sample does:

1. Protects fenced code blocks (line FSM) and inline ``code`` with placeholders  
2. Enqueues one translation job per language through **`execute_mistral_queue_async`**  
3. Restores placeholders, fixes the language switcher, validates (e.g. balanced fences)  
4. Writes outputs atomically  

Use it as a template for other infrequent batch jobs (summaries, structured extraction) that should share the free-tier gate.

## Acknowledgments

- **sioois** for sharing information about the Mistral API free tier
([link](https://zenn.dev/sioois/articles/dea773011514b1)).
- **@fujibee** for providing insights on using queues with SQLite WAL mode (#agmsg).
- **shunsuke_suzuki** for the AI-friendly CLI development methodology
([link](https://zenn.dev/shunsuke_suzuki/articles/make-cli-ai-friendly)).

Thank you all!

## Further docs

 * [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) — Vibe / MCP manual smoke
 * [docs/SEARCH_POSITIONING.md](docs/SEARCH_POSITIONING.md) — where web search belongs (outside mmq base)
 * [docs/tasks.md](docs/tasks.md) — backlog
 * [docs/NOTES.md](docs/NOTES.md) — design notes

## License

MIT License

Copyright (c) 2026 utenadev
