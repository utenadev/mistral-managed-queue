---
description: MCP server setup and usage for mistral-managed-queue
---

# MCP Server Mode

`mistral-managed-queue` includes full MCP (Model Context Protocol) server support for integration with AI agents like Vibe, Claude Desktop, and others.

## Available MCP Tools

### ask_mistral

Execute Mistral API calls through the queue system.

**Parameters:**
- `prompt` (optional): Single-shot user prompt text
- `messages` (optional): Conversation history as JSON array
- `model` (optional): Mistral model name (default: `mistral-small-latest`)
- `system_prompt` (optional): Custom system prompt
- `priority` (optional): Task priority (1: high, 2: normal, 3: low)

**Returns:** Response text from Mistral API

**Example Usage:**
```json
{
  "tool": "ask_mistral",
  "arguments": {
    "prompt": "Explain Python decorators",
    "model": "mistral-medium-latest",
    "priority": 2
  }
}
```

### get_queue_status

Get current queue and rate limit status.

**Parameters:** None

**Returns:** JSON string with queue status:
- `pending`: Number of tasks waiting in queue
- `processing`: Number of tasks currently running
- `seconds_until_next_slot`: Time until next API slot is available
- `current_wait_interval`: Current rate limit interval
- `in_flight`: Boolean indicating if any task is processing

**Example Usage:**
```json
{
  "tool": "get_queue_status",
  "arguments": {}
}
```

## MCP Client Configuration

### Vibe Configuration

Add to your Vibe configuration:

```yaml
# ~/.vibe/config.yaml
mcp:
  servers:
    mistral-managed-queue:
      command: "mmq"
      args: ["--mcp"]
```

Or use `uvx`:

```yaml
mcp:
  servers:
    mistral-managed-queue:
      command: "uvx"
      args: ["--from", "mistral-managed-queue", "mmq", "--mcp"]
```

### Claude Desktop Configuration

Add to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "mmq",
      "args": ["--mcp"]
    }
  }
}
```

## Starting the MCP Server

```bash
# Direct execution
mmq --mcp

# Using uvx (recommended for global installation)
uvx mistral-managed-queue --mcp

# With specific environment variables
MISTRAL_API_KEY=your-key mmq --mcp
```

## MCP Server Behavior

- The server runs in stdio mode
- All tools are registered with the FastMCP framework
- Rate limiting and queuing work the same as CLI mode
- Multiple clients can connect to the same MCP server instance

AI Agent Guidance: When using MCP tools, always check `get_queue_status` before making multiple API calls to understand current queue state.