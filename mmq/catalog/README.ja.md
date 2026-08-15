# カタログ — mistral-managed-queue (extras)

カタログ機能は LLM プロバイダからモデル一覧を取得し、ORR 互換の YAML として書き出します。
対応プロバイダは次の 3 つです。

- [OpenRouter](https://openrouter.ai)
- [NVIDIA NIM](https://build.nvidia.com/)
- [Mistral AI](https://mistral.ai)

## インストール

この機能には追加依存関係（`httpx` + `PyYAML`）が必要です。

```bash
# pip
pip install 'mistral-managed-queue[catalog]'

# uv
uv pip install 'mistral-managed-queue[catalog]'
```

## 使い方

```bash
# Fetch from all enabled providers and write to ./models.yaml (default)
mmq catalog fetch

# Specify output file
mmq catalog fetch -o ./my-catalog.yaml

# Skip validation
mmq catalog fetch --no-validate
```

カタログ取得はチャット API とは独立したレート制限を使い、
`MMQ_CATALOG_BASE_WAIT_TIME` と `MMQ_CATALOG_MAX_WAIT_TIME` で調整します。
未設定の場合は `MMQ_BASE_WAIT_TIME` / `MMQ_MAX_WAIT_TIME` にフォールバックします。

## プロバイダ

| プロバイダ | プラグイン | API キー環境変数 | モデル一覧 |
|---|---|---|---|
| OpenRouter | `OpenRouterPlugin` | `OPENROUTER_API_KEY` | `/api/v1/models` |
| NVIDIA NIM | `NvidiaNimPlugin` | `NVIDIA_API_KEY` | `/v1/models` |
| Mistral | `MistralPlugin` | `MISTRAL_API_KEY` | `/v1/models` |
