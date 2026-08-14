<!-- TODO: translate this file via scripts/translate_readme.py --include docs/README_extras_Catalog -->

# Catalog — mistral-managed-queue (extras)

The catalog feature fetches model lists from LLM providers and writes them as
ORR-compatible YAML. It supports three providers:

- [OpenRouter](https://openrouter.ai)
- [NVIDIA NIM](https://build.nvidia.com/)
- [Mistral AI](https://mistral.ai)

## Installation

This feature requires extra dependencies (`httpx` + `PyYAML`):

```bash
# pip
pip install 'mistral-managed-queue[catalog]'

# uv
uv pip install 'mistral-managed-queue[catalog]'
```

## Usage

```bash
# Fetch from all enabled providers and write to ./models.yaml (default)
mmq catalog fetch

# Specify output file
mmq catalog fetch -o ./my-catalog.yaml

# Skip validation
mmq catalog fetch --no-validate
```

Catalog fetching uses its own rate limiting, tuned independently from the chat API
via `MMQ_CATALOG_BASE_WAIT_TIME` and `MMQ_CATALOG_MAX_WAIT_TIME`. If unset, they fall
back to `MMQ_BASE_WAIT_TIME` / `MMQ_MAX_WAIT_TIME`.

## Providers

| Provider | Plugin | API Key Env | Models List |
|---|---|---|---|
| OpenRouter | `OpenRouterPlugin` | `OPENROUTER_API_KEY` | `/api/v1/models` |
| NVIDIA NIM | `NvidiaNimPlugin` | `NVIDIA_API_KEY` | `/v1/models` |
| Mistral | `MistralPlugin` | `MISTRAL_API_KEY` | `/v1/models` |