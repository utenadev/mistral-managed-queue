---
description: Usage guide and examples for mcp-mistral-queue CLI
---

# Usage Guide

`mcp-mistral-queue` provides a command-line interface and MCP server for making Mistral API calls with intelligent queuing and rate limiting.

## Basic CLI Usage

```bash
# Simple prompt
mmq "Explain Python briefly"

# With specific model
mmq -m mistral-large-latest "Explain this algorithm"

# With custom system prompt
mmq -s "You are a code expert" "Help me debug this Python code"

# With priority (1=high, 2=normal, 3=low)
mmq --priority 1 "Urgent: fix this production issue"
```

## Advanced Usage

### Using Messages API

```bash
# Pass messages as JSON string
mmq --messages '[{"role": "user", "content": "Hello"}]' \
     -m mistral-small-latest
```

### Task Management

```bash
# List available documentation (AI-friendly)
mmq docs list

# Show specific documentation
mmq docs show usage

# Emergency purge commands
mmq --purge              # Cancel all pending tasks
mmq --purge-all          # Cancel all pending and processing tasks
mmq --purge-id 42        # Cancel specific task by ID

# Structured purge subcommand (recommended)
mmq purge --pending      # Cancel all pending tasks
mmq purge --all          # Cancel all pending and processing tasks
mmq purge --id 42        # Cancel specific task by ID
```

### Pipe stdin to generate a commit message from staged changes

```bash
git diff --staged | mmq
git diff --staged | mmq -
git diff --staged | mmq --stdin
git diff --staged | mmq -s "Generate a concise commit message"
```

When no prompt argument is given and stdin is not a TTY (i.e. data is being piped), `mmq` reads from stdin automatically. Use `-` or `--stdin` to be explicit.

## MCP Server Mode

```bash
# Start MCP server
mmq --mcp

# Or using uvx
uvx mcp-mistral-queue --mcp
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MISTRAL_API_KEY` | - | Required: Your Mistral API key |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | Default model to use |
| `MMQ_BASE_WAIT_TIME` | 31.0 | Base wait time between API calls |
| `MMQ_MAX_WAIT_TIME` | 300.0 | Maximum wait time |
| `MMQ_BACKOFF_MULTIPLIER` | 2.0 | Exponential backoff multiplier |
| `MMQ_FAKE_API` | `false` | Enable fake API for testing |

AI Agent Guidance: Use the MCP tools (`ask_mistral`, `get_queue_status`) for programmatic access.