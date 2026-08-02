# Vibe / MCP manual smoke runbook

Automated e2e covers **CLI process** and **MCP stdio protocol** with `MMQ_FAKE_API=1`.
This runbook is for verifying the real **Vibe (or Claude Desktop) → MCP → mmq** path once.

## Prerequisites

- `uv` installed (for `uvx` / local `uv run`)
- `MISTRAL_API_KEY` set

## 1. Register MCP server in Vibe

### Recommended (PyPI)

Console script is **`mmq`** (package name is `mcp-mistral-queue`):

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

Quick CLI check: `uvx --from mcp-mistral-queue mmq --help`

### Local checkout (development)

```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp[cli]>=1.0.0,<2",
        "--with",
        "mistralai>=1.0.0,<2",
        "--no-project",
        "/absolute/path/to/mcp-mistral-queue/mmq.py",
        "--mcp"
      ],
      "env": {
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

Notes:

- Do **not** set `MMQ_FAKE_API` for real usage.
- Tools to expect: `ask_mistral`, `get_queue_status`.

## 2. Smoke checklist

1. Restart Vibe (or reload MCP servers) after config change.
2. Confirm tool **`ask_mistral`** is listed / available to the agent.
3. Ask the agent to call `ask_mistral` with a short prompt, e.g. “Reply with pong”.
4. Expect a normal completion (may wait ~31s if another process just used the shared queue DB).
5. Optional: fire two requests close together and confirm the second waits (rate gate).

## 3. Offline substitute (no Vibe UI)

If Vibe is unavailable, the automated MCP e2e is the protocol-level equivalent:

```bash
# from repo root; needs mcp[cli] + mistralai + pytest in the interpreter
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e/test_mcp_e2e.py -v
```

## 4. Live API (optional, costs free-tier quota)

```bash
export MISTRAL_API_KEY=...
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e/test_live_api.py -v -m live
```
