# MCPサーバー — mistral-managed-queue

MCP（Model Context Protocol）サーバーは `ask_mistral` と `get_queue_status` を
Vibe、Claude Desktop、Grok などの MCP ホストに公開します。

MCP は **オプトイン** です。ホスト環境で `MMQ_ENABLE_MCP=true` を設定してください。

## CLI 操作

```bash
MMQ_ENABLE_MCP=true mmq mcp run      # start the MCP server
MMQ_ENABLE_MCP=true mmq mcp status   # show MCP availability
```

## 設定（PyPI / uvx — 推奨）

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "uvx",
      "args": ["--from", "mistral-managed-queue", "mmq", "mcp", "run"],
      "env": {
        "MMQ_ENABLE_MCP": "true",
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

`mmq` がすでに `PATH` にある場合（venv / `uv pip install`）:

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "mmq",
      "args": ["mcp", "run"],
      "env": {
        "MMQ_ENABLE_MCP": "true",
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

## ローカルチェックアウト（開発）

```json
{
  "mcpServers": {
    "mistral-managed-queue": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp[cli]>=1.0.0,<2",
        "--with", "mistralai>=1.0.0,<2",
        "--no-project",
        "python", "-m", "mmq.cli", "mcp", "run"
      ],
      "env": {
        "MMQ_ENABLE_MCP": "true",
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

設定変更後はクライアントを再起動してください。Vibe の手動チェックリスト: [docs/SMOKE_VIBE.md](../docs/SMOKE_VIBE.md)。

## MCP ツール

### `ask_mistral`

| 引数 | 型 | デフォルト | 説明 |
|---|---|---|---|
| prompt | string | required | ユーザーのプロンプト本文 |
| model | string | "mistral-small-latest" | Mistral モデル名 |
| system_prompt | string | null | カスタムシステムプロンプト |

### `get_queue_status`

現在の共有キュー状態を JSON で返します。

| フィールド | 型 | 説明 |
|---|---|---|
| pending | number | キュー待ちのタスク数 |
| processing | number | 現在 claim / 実行中のタスク数 |
| completed | number | 完了したタスク数 |
| failed | number | 失敗したタスク数 |
| total | number | タスク総数 |
| seconds_until_next_slot | number | レートゲートが次スロットを開けるまでの秒数 |
| current_wait_interval | number | 現在の共有待機間隔（バックオフ後） |
| in_flight | boolean | いずれかのタスクが処理中なら True |
