<!-- TODO: translate this file via scripts/translate_readme.py --include docs/README_MCP -->

# MCP Server — mistral-managed-queue

The MCP (Model Context Protocol) server exposes `ask_mistral` and `get_queue_status`
to MCP hosts such as Vibe, Claude Desktop, and Grok.

MCP is **opt-in**: set `MMQ_ENABLE_MCP=true` in the host environment.

## CLI Control

```bash
MMQ_ENABLE_MCP=true mmq mcp run      # start the MCP server
MMQ_ENABLE_MCP=true mmq mcp status   # show MCP availability
```

## Configuration (PyPI / uvx — recommended)

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

## Local Checkout (development)

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

After changing config, restart the client. Manual Vibe checklist: [SMOKE_VIBE.md](SMOKE_VIBE.md).

## MCP Tools

### `ask_mistral`

| Argument | Type | Default | Description |
|---|---|---|---|
| prompt | string | required | User prompt text |
| model | string | "mistral-small-latest" | Mistral model name |
| system_prompt | string | null | Custom system prompt |

### `get_queue_status`

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