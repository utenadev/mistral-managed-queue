# mcp-mistral-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

An MCP (Model Context Protocol) server and CLI tool that coordinates local and multi-process / multi-client calls to the Mistral free tier (~1 request / 30 seconds) via a shared SQLite queue.
It uses SQLite (WAL mode) and async queueing with a single in-flight task to space request starts. This is best-effort traffic control, not an official SLA.

## Features

 * **Automatic rate-limit coordination**: Shared ~31s start interval; on 429, shared backoff then re-enter the gate. Resets to the base interval on success.
 * **Multi-process & priority control**: Multiple processes/tasks can enqueue work. Priority (1–3) plus single in-flight processing order the queue.
 * **Flexible model & message options**: Any Mistral chat model name (defaults to `mistral-small-latest`; e.g. `mistral-large-latest`, `codestral-latest`), plus full conversation history via a `messages` array.
 * **Streaming & cancel handling**: Streams the Mistral API response internally (tool returns the full text); on client cancel (`CancelledError`) updates task status in the DB.
 * **Local control DB**: Temp DB under a per-user directory with mode `0700` (path overridable via `MMQ_TEMP_DB_PATH`).
 * **uv-friendly**: PEP 723 inline script metadata; use `uv run` to resolve deps.
 * **Mistral Vibe integration**: Register as an MCP server (`--mcp`) for Vibe / Claude Desktop / similar clients. Direct CLI use is `uv run` (not `vibe mmq.py ...`).

## Prerequisites

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) installed (0.1.0+ recommended)
 * A Mistral API key (`MISTRAL_API_KEY`)

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```

## Usage

### 1. CLI mode (direct run)

**Run the script with `uv run`.**  
The `vibe` command is Mistral Vibe’s **agent CLI**; `vibe mmq.py "..."` does **not** execute this script.

```bash
# Basic run (default model: mistral-small-latest)
uv run mmq.py "Explain Python list comprehensions briefly"

# Choose a model (e.g. mistral-large-latest, codestral-latest)
uv run mmq.py -m mistral-large-latest "Explain a complex algorithm"

# Custom system prompt
uv run mmq.py -s "You are an AI that speaks casually." "How is the weather today?"

# Priority (1: high, 2: normal, 3: low)
uv run mmq.py --priority 1 "Urgent question"

# Full conversation context as a messages JSON array
uv run mmq.py --messages '[{"role":"system","content":"Strict programmer"},{"role":"user","content":"What is ownership in Rust?"}]'
```

### 2. MCP server mode (Mistral Vibe / other clients)

Expose the **`ask_mistral`** tool to Vibe, Claude Desktop, OpenCode, Goose, and similar clients.  
This is a separate path from CLI `uv run mmq.py "..."`.

Use an **absolute path** to this repo’s `mmq.py` (package is not on PyPI yet).  
`uv run` resolves the PEP 723 deps; see [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md).

**Vibe / Claude Desktop example** (`claude_desktop_config.json` or equivalent):

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

After changing config, restart the client and have the agent use the `ask_mistral` tool (pass `model` when needed, e.g. `mistral-large-latest`).

> **After a PyPI release:** `uvx` / published install may replace the path form. The console script is `mmq` (see `pyproject.toml`), not `mcp-mistral-queue`. Track that in [docs/tasks.md](docs/tasks.md).

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

## License

MIT License

Copyright (c) 2026 utenadev
