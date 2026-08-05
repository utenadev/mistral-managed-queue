# AGENTS.md

## Project

`mcp-mistral-queue` — single-file Python MCP server + CLI that queues Mistral API calls with rate limiting (free-tier ~1 req/30s) via SQLite (WAL mode). Main code: `mmq.py` (1238 lines). Entry point: `mmq` console script (`mmq:main`).

## Toolchain

- **Package manager**: `uv` (preferred). `pip` works but `uv` is used in all task commands.
- **Build**: `hatchling` (see `pyproject.toml`). `uv build` → `dist/`.
- **No lint/typecheck/format tools configured** (no ruff, black, mypy in pyproject.toml). Do not assume they exist.

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

# Build
uv build

# Run from git checkout (PEP 723)
uv run mmq.py "prompt"

# Task runner (Taskfile.yml)
task test
task semgrep
task gitleaks
task pypi:publish
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
| `MMQ_TEMP_DB_PATH` | per-user tempdir | Override DB path (for test isolation) |
| `MMQ_BASE_WAIT_TIME` | `31` | Seconds between request starts |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | Default model |
| `MMQ_MAX_WAIT_TIME` | `300` | Max backoff wait |
| `MMQ_PROCESSING_TIMEOUT` | `120` | Zombie task timeout |

## Gotchas

- **Console script name is `mmq`**, not `mcp-mistral-queue`. Wrong: `uvx mcp-mistral-queue --mcp`. Right: `uvx --from mcp-mistral-queue mmq --mcp`.
- **Do not use `vibe mmq.py "..."`** — that runs Vibe's agent CLI, not this tool. Use `mmq` or `uv run mmq.py ...`.
- **`mmq.py` has PEP 723 script metadata** (`/// script` block) so it can be run directly with `uv run mmq.py ...` from a git checkout.
- **New `purge` subcommand** (`mmq purge --pending`, `--all`, `--id N`) is the recommended way; `--purge`/`--purge-all`/`--purge-id` are legacy flags still supported for backward compat.
- **`mmq docs list`** outputs JSON of available docs; **`mmq docs show <name>`** prints a doc file. Excluded from docs: `NOTES.md`, `tasks.md`, `SEARCH_POSITIONING.md`, `SMOKE_VIBE.md`, `README.md`, `REVIEW.md`.
- **`REVIEW.md` is in `.gitignore`** — it is local-only and not committed.
- **`Taskfile.yml` is in `.gitignore`** — local ops only.

## Architecture

- `mmq.py` is the entire application (single file). It contains: CLI arg parsing, MCP server (`FastMCP`), SQLite queue, rate limiter, fake API client for testing, and docs commands.
- `tests/test_mmq.py` — unit tests (stubs `mcp` and `mistralai` when missing for offline runs).
- `tests/e2e/` — subprocess e2e tests that run `mmq.py` as a separate process with `MMQ_FAKE_API=1`.
- `scripts/translate_readme.py` — sample script using the queue to translate READMEs via Mistral.
- `docs/` — markdown docs referenced by `mmq docs show`. Only `install.md`, `usage.md`, `mcp.md`, `rate-limit.md`, `troubleshooting.md`, `examples.md` are included in the PyPI package.

## Testing Notes

- pytest `asyncio_mode = "auto"` in `pyproject.toml`.
- Unit tests stub `mcp` and `mistralai` with `MagicMock` when those packages are not installed, so they run offline.
- e2e tests use subprocess isolation with `MMQ_FAKE_API=1` and short wait times (`MMQ_BASE_WAIT_TIME=0.05`).
- `live` marker tests require a real `MISTRAL_API_KEY` and consume free-tier quota.