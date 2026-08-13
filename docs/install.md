---
description: Installation instructions for mcp-mistral-queue
---

# Installation

`mcp-mistral-queue` is a CLI tool and MCP server for managing Mistral API calls with priority queuing and rate limiting.

## Prerequisites

- Python 3.10+
- `uv` (recommended) or `pip`
- Mistral API key

## Installation Methods

### Using uv (recommended)

```bash
# Install globally
uv pip install mcp-mistral-queue

# Or run directly without installation
uvx --from mcp-mistral-queue mmq
```

### Using pip

```bash
pip install mcp-mistral-queue
```

### From source

```bash
# Clone the repository
git clone https://github.com/your-repo/mcp-mistral-queue.git
cd mcp-mistral-queue

# Install in development mode
uv pip install -e .
```

## Environment Setup

Set your Mistral API key:

```bash
# For CLI usage
export MISTRAL_API_KEY="your-api-key"

# Or set it permanently in your shell profile
```

## MCP Configuration

For MCP clients (Vibe, Claude Desktop, etc.):

```json
{
  "command": "mmq",
  "args": ["--mcp"]
}
```

AI Agent Guidance: Use `mmq --mcp` to start the MCP server for tool integration.