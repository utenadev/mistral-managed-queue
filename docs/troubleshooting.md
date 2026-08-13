---
description: Troubleshooting guide for mcp-mistral-queue
---

# Troubleshooting

Common issues and their solutions when using `mcp-mistral-queue`.

## Installation Issues

### Dependency Errors

**Symptom:** Import errors when running `mmq.py`

**Solution:**
```bash
# Install required dependencies
uv pip install mcp-mistral-queue

# Or install from requirements
uv pip install mcp[cli] mistralai
```

### Command Not Found

**Symptom:** `mmq: command not found`

**Solution:**
```bash
# Install globally
uv pip install mcp-mistral-queue

# Or run directly
uvx mcp-mistral-queue

# Or use python -m
python -m mcp_mistral_queue
```

## API Issues

### Authentication Errors

**Symptom:** API calls fail with authentication errors

**Solution:**
```bash
# Set your API key
export MISTRAL_API_KEY="your-actual-api-key"

# Verify it's set
printenv MISTRAL_API_KEY
```

### Rate Limit Errors

**Symptom:** Frequent 429 errors or long wait times

**Solution:**
```bash
# Check current queue status
mmq get_queue_status

# Adjust rate limit settings if needed
export MMQ_BASE_WAIT_TIME=60.0
export MMQ_MAX_WAIT_TIME=600.0
```

## Queue Issues

### Tasks Stuck in Processing

**Symptom:** Tasks remain in "processing" state for a long time

**Solution:**
```bash
# Clean up zombie tasks (automatic on startup, but can be forced)
# This is handled automatically, but you can check with:
mmq get_queue_status

# If needed, manually purge stuck tasks
mmq --purge-id <task_id>
```

### Tasks Not Starting

**Symptom:** Tasks remain in "pending" state indefinitely

**Solution:**
```bash
# Check if there are too many concurrent processes
# Only one task can process at a time by design

# Check queue status
mmq get_queue_status

# If a task is stuck, purge it
mmq --purge-all
```

## Database Issues

### Permission Errors

**Symptom:** Database permission errors

**Solution:**
```bash
# The database is created in a user-specific temp directory
# Ensure /tmp is writable

# Override database location if needed
export MMQ_TEMP_DB_PATH="/custom/path/to/db"
```

## Debugging

### Enable Debug Logging

```bash
# Set logging level to DEBUG
# Edit mmq.py and change logging.basicConfig level to logging.DEBUG

# Or add debug prints to specific functions
```

### Check Database Contents

```bash
# The database is located at:
# /tmp/mcp_mistral_queue_{username}/mcp_mistral_flow_control.db

# You can inspect it with sqlite3
sqlite3 /tmp/mcp_mistral_queue_$(whoami)/mcp_mistral_flow_control.db ".tables"
sqlite3 /tmp/mcp_mistral_queue_$(whoami)/mcp_mistral_flow_control.db "SELECT * FROM tasks;"
```

## Testing

### Using Fake API

```bash
# Enable fake API for testing
export MMQ_FAKE_API=1

# Set fake response (optional)
export MMQ_FAKE_RESPONSE="test response"

# Test without actual API calls
mmq --mcp
```

### Common Test Scenarios

```bash
# Test basic functionality
export MMQ_FAKE_API=1
mmq "test prompt"

# Test rate limiting
export MMQ_FAKE_API=1
export MMQ_FAKE_FAIL=429
mmq "should trigger rate limit backoff"
```

AI Agent Guidance: For debugging, use the `--mcp` mode with your AI client to inspect tool behavior interactively.