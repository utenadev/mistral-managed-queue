# AGENTS.md

## Project

`mcp-mistral-queue` — Python MCP server + CLI that queues Mistral API calls with
rate limiting (free-tier ~1 req/30s) via SQLite (WAL mode). Package layout under
`mmq/`. Console script: `mmq` (`mmq.cli:main`).

## Architecture

- `mmq/config.py` — all constants + env-var defaults (wait times, model, DB timeouts).
- `mmq/db.py` — SQLite layer: `init_db`, task lifecycle (`register_task`, `claim_task`,
  `claim_next_task`, `get_task`, `touch_task`, `update_task_status`), rate-limit gate
  (`wait_for_rate_limit`), `purge_tasks`, `read_queue_status`. Task claiming uses
  SQLite `UPDATE ... RETURNING` (needs SQLite >= 3.35).
- `mmq/core.py` — Mistral wrapper (`call_mistral_api` with retries + shared gate),
  `FakeMistralClient` (offline e2e), queue execution:
  - `execute_mistral_queue_async(req)` — self-serve path (MCP): registers its own task
    and claims *only its own* (avoids cross-claim deadlock; see tests `TestExecuteQueueConcurrent`).
  - `execute_next_task_async` / `drain_queue_async` / `watch_queue_async` — the
    `mmq work` worker, which claims pending tasks **by priority (DESC) then FIFO**.
- `mmq/cli.py` — subcommands: `ask`, `fetch`, `work`, `purge`, `catalog fetch`, `mcp`, `--mcp`.
- `mmq/mcp_server.py` — FastMCP server; tools `ask_mistral`, `get_queue_status`.
- `mmq/catalog/` — ORR-compatible catalog fetch/validate/write (`fetch.py`, `validate.py`,
  `write.py`, `types.py`). `write_catalog_yaml(path, document)` (order matters).
- `mmq/__init__.py` — `__version__` + re-exports. **Version is kept in sync with
  `pyproject.toml`** (currently `0.2.0`).

## Key Concepts

- **Rate gate**: single shared row in SQLite; every API attempt (first included) waits
  on it, so all processes/CLI/MCP are uniformly throttled. 429s raise the shared backoff.
- **Self-serve vs worker**: MCP `ask_mistral` processes its own request inline. `mmq fetch`
  only enqueues; `mmq work` (worker mode) drains the queue by priority.
- **Fake API**: `MMQ_FAKE_API=1` uses `FakeMistralClient` (echoes prompt unless
  `MMQ_FAKE_RESPONSE` set). `MMQ_FAKE_FAIL=429|error` simulates failures.

## Toolchain

- **Package manager**: `uv` (preferred). Build: `hatchling`. `uv build` → `dist/`.
- **No lint/typecheck/format tools configured** (no ruff, black, mypy). Do not assume they exist.

## Key Commands

```bash
# Run tests (unit + e2e with fake API; no network needed)
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/ -v -m "not live"

# e2e only
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e -v -m "not live"

# Live API test (costs free-tier quota; needs MISTRAL_API_KEY)
export MISTRAL_API_KEY=...
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e/test_live_api.py -v -m live

# CLI usage (from a git checkout)
MMQ_FAKE_API=1 uv run mmq ask "prompt"                    # immediate reply
MMQ_FAKE_API=1 uv run mmq fetch -p 5 "prompt"             # enqueue for later
MMQ_FAKE_API=1 uv run mmq work                            # drain queue (priority order)
MMQ_FAKE_API=1 uv run mmq work --once                     # process one task
MMQ_FAKE_API=1 uv run mmq work --watch                    # continuous worker
uv run mmq purge --pending                                # clean the queue
uv run mmq --mcp                                          # start MCP server (stdio)

# Task runner (Taskfile.yml, gitignored)
task test
```

## Running a Single Test

```bash
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/test_mmq.py::TestMistralRequest -v
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `MISTRAL_API_KEY` | (required) | Mistral API key |
| `MMQ_FAKE_API` | off | Set `1`/`true` for offline e2e (fake client, no network) |
| `MMQ_FAKE_RESPONSE` | — | Fixed fake response text (else echo prompt) |
| `MMQ_FAKE_FAIL` | — | `429`/`error` to simulate API failures |
| `MMQ_TEMP_DB_PATH` | per-user tempdir | Override DB path (for test isolation) |
| `MMQ_BASE_WAIT_TIME` | `31` | Seconds between request starts |
| `MMQ_MAX_WAIT_TIME` | `300` | Max backoff wait |
| `MMQ_BACKOFF_MULTIPLIER` | `2.0` | Backoff multiplier on 429 |
| `MMQ_MIN_SLEEP_INTERVAL` | `2.0` | Min poll/sleep granularity |
| `MMQ_PROCESSING_TIMEOUT` | `120` | Zombie task timeout |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | Default model |
| `MMQ_DB_CONNECT_TIMEOUT` | `30` | SQLite connect timeout |
| `MMQ_DB_SHORT_TIMEOUT` | `10` | SQLite short timeout |
| `MMQ_CATALOG_BASE_WAIT_TIME` | `MMQ_BASE_WAIT_TIME` | Catalog fetch pacing |
| `MMQ_CATALOG_MAX_WAIT_TIME` | `MMQ_MAX_WAIT_TIME` | Catalog fetch max backoff |
| `MMQ_ENABLE_MCP` | off | Show/enable `mcp` subcommand |

## Gotchas

- **Console script name is `mmq`**, not `mcp-mistral-queue`. Wrong: `uvx mcp-mistral-queue --mcp`.
  Right: `uvx --from mcp-mistral-queue mmq --mcp`.
- **There is no `mmq.py`** anymore — the app is the `mmq/` package. Run with
  `uv run mmq ...` or `python -m mmq.cli ...`. `uv run mmq.py` no longer works.
- **`write_catalog_yaml(path, document)`** — `path` first. The CLI `catalog fetch`
  calls it as `write_catalog_yaml(args.output, catalog.document)`.
- **Self-serve tasks must claim their own id** (`claim_task(task_id)`). Reintroducing a
  global highest-priority claim in `execute_mistral_queue_async` causes the cross-claim
  deadlock fixed by H1/H2. Global priority claiming lives only in `claim_next_task`
  (used by `mmq work`).
- **`mmq fetch` does not process** — it enqueues. Run `mmq work` to drain.
- **`REVIEW.md` is in `.gitignore`** — local-only, not committed. `Taskfile.yml` likewise.

## Tests

- `tests/test_mmq.py` — unit tests; stubs `mcp` and `mistralai` with `MagicMock` when
  missing so they run offline. `tests/catalog/` — catalog unit tests.
- `tests/e2e/` — subprocess tests running `python -m mmq.cli` with `MMQ_FAKE_API=1`
  and short waits (isolated `MMQ_TEMP_DB_PATH` per test).
- pytest `asyncio_mode = "auto"`; markers `e2e`, `live`.
- Key regression suites: `TestExecuteQueueConcurrent` (H1/H2 no-deadlock),
  `TestClaimNextTask` (worker priority ordering), `TestCliWiring` (adversarial-review fixes).
