---
description: Practical examples and use cases for mistral-managed-queue
---

# Examples

Practical use cases and examples for `mistral-managed-queue`.

## Basic Usage Examples

### Simple Text Generation

```bash
# Basic usage
mmq "Write a Python function to sort a list"

# With specific model
mmq -m mistral-medium-latest "Explain quantum computing in simple terms"

# With custom system prompt
mmq -s "You are a helpful code assistant" "Help me write a regex pattern"
```

### Conversation with Messages

```bash
# Multi-turn conversation using JSON messages
mmq --messages '[
  {"role": "system", "content": "You are a helpful assistant."},
  {"role": "user", "content": "Hello, how are you?"},
  {"role": "assistant", "content": "I am doing well, thank you!"},
  {"role": "user", "content": "What can you help me with?"}
]' -m mistral-small-latest
```

## Priority Management Examples

### High Priority Tasks

```bash
# High priority task (jumps to front of queue)
mmq --priority 1 "Urgent: analyze this critical production error"

# Low priority task (waits longer)
mmq --priority 3 "Background: summarize this document"
```

### Queue Management

```bash
# Check current queue status
mmq get_queue_status

# Cancel all pending tasks
mmq --purge

# Cancel a specific task by ID
mmq --purge-id 123

# Cancel all tasks (pending and processing)
mmq --purge-all
```

## MCP Server Examples

### Vibe Integration

```yaml
# ~/.vibe/config.yaml
mcp:
  servers:
    mistral-managed-queue:
      command: "uvx"
      args: ["--from", "mistral-managed-queue", "mmq", "--mcp"]
```

### Claude Desktop Integration

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "uvx",
      "args": ["--from", "mistral-managed-queue", "mmq", "--mcp"]
    }
  }
}
```

## Advanced Examples

### Batch Processing

```bash
# Process multiple prompts with different priorities
export MISTRAL_API_KEY=your-key

# High priority batch
mmq --priority 1 "Analyze this critical log file"
mmq --priority 1 "Generate urgent report"

# Normal priority batch
mmq --priority 2 "Write documentation"
mmq --priority 2 "Code review this PR"

# Low priority batch
mmq --priority 3 "Background research on AI trends"
```

### Environment Customization

```bash
# Custom rate limiting for pro tier
export MMQ_BASE_WAIT_TIME=5.0
export MMQ_MAX_WAIT_TIME=60.0
export MMQ_BACKOFF_MULTIPLIER=1.5

# Custom database location
export MMQ_TEMP_DB_PATH="/home/user/.mmq/db"

# Run with custom settings
mmq "test prompt"
```

### Testing with Fake API

```bash
# Enable fake API for testing without real API calls
export MMQ_FAKE_API=1
export MMQ_FAKE_RESPONSE="This is a test response"

# Test your integration
mmq "This will return the fake response"

# Test error handling
export MMQ_FAKE_FAIL=429
mmq "This will trigger rate limit error"
```

### Docker Usage

```dockerfile
# Dockerfile
FROM python:3.11-slim

RUN pip install uv
COPY . /app
WORKDIR /app

RUN uv pip install mistral-managed-queue

CMD ["mmq", "--mcp"]
```

```bash
# Build and run
docker build -t mistral-managed-queue .
docker run -e MISTRAL_API_KEY=your-key mistral-managed-queue
```

## Documentation Access Examples

### For AI Agents

```bash
# List all available documentation
mmq docs list

# Read specific documentation
mmq docs show installation
mmq docs show usage
mmq docs show mcp
mmq docs show rate-limit
mmq docs show troubleshooting
mmq docs show examples
```

### Documentation Output Format

The `docs list` command returns JSON for easy parsing by AI agents:

```json
{
  "results": [
    {
      "name": "install",
      "description": "Installation instructions for mistral-managed-queue"
    },
    {
      "name": "usage", 
      "description": "Usage guide and examples for mistral-managed-queue CLI"
    }
  ],
  "help": "If you are a coding agent, run `mmq docs show {name}` to see details."
}
```

AI Agent Guidance: Use the examples above to understand how to effectively use this tool. The `mmq docs list` and `mmq docs show` commands are designed specifically for AI agents to discover and understand available functionality.