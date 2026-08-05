# mcp-mistral-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

[![PyPI](https://img.shields.io/pypi/v/mcp-mistral-queue)](https://pypi.org/project/mcp-mistral-queue/)

An MCP (Model Context Protocol) server and CLI tool that coordinates local and multi-process / multi-client calls to the Mistral free tier (~1 request / 30 seconds) via a shared SQLite queue.
It uses SQLite (WAL mode) and async queueing with a single in-flight task to space request starts. This is best-effort traffic control, not an official SLA.

**Package:** [`mcp-mistral-queue`](https://pypi.org/project/mcp-mistral-queue/) on PyPI · **console script:** `mmq` (not the package name) · **current release:** `0.1.2`

## Features

 * **Automatic rate-limit coordination**: Shared ~31s start interval; on 429, shared backoff then re-enter the gate. Resets to the base interval on success.
 * **Multi-process & priority control**: Multiple processes/tasks can enqueue work. Priority (1–3) plus single in-flight processing order the queue.
 * **Flexible model & message options**: Any Mistral chat model name (defaults to `mistral-small-latest`; e.g. `mistral-large-latest`, `codestral-latest`), plus full conversation history via a `messages` array.
 * **Streaming & cancel handling**: Streams the Mistral API response internally (tool returns the full text); on client cancel (`CancelledError`) updates task status in the DB.
 * **Local control DB**: Temp DB under a per-user directory with mode `0700` (path overridable via `MMQ_TEMP_DB_PATH`).
 * **PyPI / uvx**: Install once or run ephemerally; entry point is `mmq`.
 * **Mistral Vibe / Grok / Claude Desktop**: Register as an MCP server (`mmq --mcp`). Do **not** use `vibe mmq.py "..."` — that runs Vibe’s agent CLI, not this tool.
 * **Good free-tier fit**: Occasional jobs (e.g. translating docs) that can wait ~31s between calls without burning a dedicated rate-limit stack.
 * **AI-friendly CLI**: Built for coding agents (Vibe, Claude Code, etc.) with `docs list` / `docs show` subcommands, agent guidance in help text, and JSON outputs for easy parsing.
 * **Stdin pipe support**: Pipe `git diff` output directly into `mmq` to generate commit messages.

## Prerequisites

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) recommended (`uvx` / `uv run`); `pip` also works
 * A Mistral API key (`MISTRAL_API_KEY`)

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```

## Install (PyPI)

Published and verified on [PyPI](https://pypi.org/project/mcp-mistral-queue/).

```bash
# One-shot (no permanent install) — recommended for MCP hosts
uvx --from mcp-mistral-queue mmq --help

# Or install into an environment
uv pip install mcp-mistral-queue
# pip install mcp-mistral-queue

mmq --help
```

**Quick smoke (needs `MISTRAL_API_KEY`; counts against free-tier quota):**

```bash
uvx --from mcp-mistral-queue mmq "Reply with pong only."
```

**Notes:**

 * Console script name is **`mmq`**. Wrong: `uvx mcp-mistral-queue --mcp`. Right: `uvx --from mcp-mistral-queue mmq --mcp`.
 * Dependencies: `mcp[cli]>=1.0.0,<2`, `mistralai>=1.0.0,<2` (pulled in by the package).

## Usage

### 1. CLI mode

After PyPI install / via `uvx`, invoke **`mmq`**.  
From a git checkout you can still use `uv run mmq.py ...` (PEP 723).

```bash
# Basic run (default model: mistral-small-latest)
uvx --from mcp-mistral-queue mmq "Explain Python list comprehensions briefly"
# or: mmq "Explain Python list comprehensions briefly"

# Choose a model (e.g. mistral-large-latest, codestral-latest)
mmq -m mistral-large-latest "Explain a complex algorithm"

# Custom system prompt
mmq -s "You are an AI that speaks casually." "How is the weather today?"

# Priority (1: high, 2: normal, 3: low)
mmq --priority 1 "Urgent question"

# Full conversation context as a messages JSON array
# (specify either prompt or --messages, not both)
mmq --messages '[{"role":"system","content":"Strict programmer"},{"role":"user","content":"What is ownership in Rust?"}]'

# Emergency brake: cancel queued / stuck work (no API call)
mmq --purge          # cancel all pending
mmq --purge-all      # cancel pending + processing
mmq --purge-id 42    # cancel one task by ID

# New structured purge subcommand (recommended for scripts/AI)
mmq purge --pending   # cancel all pending tasks
mmq purge --all       # cancel all pending + processing tasks
mmq purge --id 42     # cancel specific task by ID

# Pipe stdin to generate a commit message from a diff
git diff | mmq
git diff | mmq -
git diff | mmq --stdin
git diff | mmq -s "Generate a concise commit message"
```

### AI-Friendly Documentation Commands

For coding agents (Vibe, Claude Code, etc.):

```bash
# List all available documentation
mmq docs list

# Show specific documentation (returns markdown content)
mmq docs show usage
mmq docs show install
mmq docs show mcp
mmq docs show rate-limit
mmq docs show troubleshooting
mmq docs show examples
```

The `docs list` command outputs JSON with descriptions for easy parsing:

```json
{
  "results": [
    {"name": "usage", "description": "Usage guide and examples for mcp-mistral-queue CLI"},
    {"name": "install", "description": "Installation instructions for mcp-mistral-queue"}
  ],
  "help": "If you are a coding agent, run `mmq docs show {name}` to see details."
}
```

### 2. MCP server mode (Vibe / Grok / Claude Desktop / …)

Expose **`ask_mistral`** and **`get_queue_status`** to MCP hosts.  
Separate path from CLI prompts.

#### PyPI / uvx (recommended)

```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "uvx",
      "args": ["--from", "mcp-mistral-queue", "mmq", "--mcp"],
      "env": {
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
    "mistral-queue": {
      "command": "mmq",
      "args": ["--mcp"],
      "env": {
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
    "mistral-queue": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp[cli]>=1.0.0,<2",
        "--with", "mistralai>=1.0.0,<2",
        "--no-project",
        "/absolute/path/to/mmq.py",
        "--mcp"
      ],
      "env": {
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
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | Default model name |
| `MMQ_FAKE_API` | off | Offline / e2e: fake client (`1`/`true`) |

Other knobs (`MMQ_MAX_WAIT_TIME`, `MMQ_MAX_RETRIES`, …) exist for tuning; see `mmq.py`.

### MCP tools

When the server is running, clients can use the following tools:

#### `ask_mistral`

| Argument | Type | Default | Description |
|---|---|---|---|
| prompt | string | null | Single-shot user prompt text |
| messages | array | null | Conversation history (`[{"role": "...", "content": "..."}]`) |
| model | string | `"mistral-small-latest"` | Mistral model name |
| system_prompt | string | null | Custom system prompt (only when using `prompt`) |
| priority | number | 2 | Task priority (1: high, 2: normal, 3: low) |

#### `get_queue_status`

Returns current shared queue / rate-limit status as JSON:

| Field | Type | Description |
|---|---|---|
| pending | number | Tasks waiting in the queue |
| processing | number | Tasks currently claimed / running |
| seconds_until_next_slot | number | Seconds until the shared API gate opens |
| current_wait_interval | number | Active shared wait interval (seconds) |
| in_flight | boolean | Whether any task is currently processing |

## Control data location

The coordination temp DB is stored in a per-user directory created with mode `0700`:

 * Default: `<tempdir>/mcp_mistral_queue_<USER>/mcp_mistral_flow_control.db`  
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

# From a git checkout (imports mmq.py on PYTHONPATH via the script)
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
