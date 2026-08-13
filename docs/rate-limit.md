---
description: Rate limiting and backoff behavior in mcp-mistral-queue
---

# Rate Limiting

`mcp-mistral-queue` implements intelligent rate limiting to handle Mistral API's free tier constraints (approximately 1 request per 30 seconds).

## How Rate Limiting Works

### Shared Rate Limit State

- All processes share a common SQLite database for rate limit tracking
- The shared state prevents multiple processes from overwhelming the API
- Rate limit information is stored in the `api_log` table

### Exponential Backoff

When rate limit errors (HTTP 429) are detected:

1. The wait time is doubled for subsequent attempts
2. The backoff is capped at `MMQ_MAX_WAIT_TIME` (default: 300 seconds)
3. All processes respect the updated wait time

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MMQ_BASE_WAIT_TIME` | 31.0 | Base interval between API calls |
| `MMQ_MAX_WAIT_TIME` | 300.0 | Maximum wait time cap |
| `MMQ_BACKOFF_MULTIPLIER` | 2.0 | Multiplier for exponential backoff |
| `MMQ_MIN_SLEEP_INTERVAL` | 2.0 | Minimum sleep between retries |

### Adjusting for Different Tiers

#### Free Tier
```bash
# Default settings work well for free tier
export MMQ_BASE_WAIT_TIME=31.0
export MMQ_MAX_WAIT_TIME=300.0
```

#### Pro Tier
```bash
# Adjust for higher rate limits
export MMQ_BASE_WAIT_TIME=5.0
export MMQ_MAX_WAIT_TIME=60.0
```

## Queue Behavior

- Tasks are processed in priority order (1=high, 2=normal, 3=low)
- Within the same priority, tasks are processed in FIFO order
- Only one task can be in "processing" state at any time
- Other tasks remain in "pending" state until their turn

## Retry Logic

- Maximum of 3 retry attempts per API call
- Rate limit errors trigger immediate backoff and re-queue
- Other errors wait for the minimum sleep interval before retry

AI Agent Guidance: The rate limiting is automatic. If you see "Rate limiting active" messages, the system is working as expected.