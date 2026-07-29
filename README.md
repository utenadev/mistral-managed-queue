mcp-mistral-queue

[English](README_en.md)

Mistral API の無料枠（1リクエスト/30秒）制限を安全に回避し、ローカル環境や複数プロセス・MCPクライアントからの呼び出しを自動調停する MCP (Model Context Protocol) サーバー兼 CLI ツールです。
SQLite (WALモード) と非同期キューイングを活用し、API レート制限を遵守しながら順番にリクエストを処理します。

主な特徴
 * 自動レート制限調停: 31 秒間隔を自動調整し、無料枠の 429 Too Many Requests エラーを防止。エラー発生時は指数バックオフで自動回復。
 * マルチプロセス&優先度制御: 複数プロセス・タスクからの同時呼び出しに対応。タスク優先度 (Priority) に基づいた割り込み処理・キューイングを実現。
 * 柔軟なモデル&メッセージ指定: mistral-small-latest のほか、mistral-large-latest や codestral-latest への動的切り替え、および会話履歴（messages 配列）の直接投入に対応。
 * ストリーミング&キャンセルハンドリング: レスポンスの逐次処理と、クライアント側からのキャンセル信号・タイムアウトの安全な検出。
 * セキュアな設計: 一時管理用 DB は OS のユーザー専用隠しフォルダ（パーミッション 0700）内に配置し、他ユーザーからの干渉・情報漏洩を遮断。
 * uv 完全対応: PEP 723 (Inline Script Metadata) に対応。依存関係の個別管理や venv の作成が不要。
 * Mistral Vibe 連携: MCP サーバー（`--mcp`）として Vibe / Claude Desktop 等に登録可能。CLI 直実行は `uv run` を使用。

前提条件
 * Python 3.10+
 * uv がインストールされていること (0.1.0 以上を推奨)
 * Mistral API の API キー (MISTRAL_API_KEY)

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```

使い方

1. CLI モード (直接実行)

**スクリプト実行は `uv run` を使います。**  
（`vibe` コマンドは Mistral Vibe の**エージェント CLI** であり、`vibe mmq.py "..."` のようには動きません。）

```bash
# 基本実行 (デフォルトモデル: mistral-small-latest)
uv run mmq.py "Pythonのリスト内包表記について短く解説して"

# モデルを指定して実行 (例: mistral-large-latest, codestral-latest)
uv run mmq.py -m mistral-large-latest "複雑なアルゴリズムの解説をお願い"

# システムプロンプトを指定
uv run mmq.py -s "あなたは関西弁で話すAIです。" "今日の天気を教えて"

# 優先度 (1: 高, 2: 通常, 3: 低) を指定して割り込み処理
uv run mmq.py --priority 1 "緊急度が高い質問"

# 対話コンテキスト (messages 配列) を直接渡す
uv run mmq.py --messages '[{"role":"system","content":"厳格なプログラマー"},{"role":"user","content":"Rustの所有権とは？"}]'
```

2. MCP サーバーモード (Mistral Vibe / 他クライアント連携)

Vibe、Claude Desktop、OpenCode、Goose などから **MCP ツール `ask_mistral`** として呼びます。  
CLI の `uv run mmq.py "..."` とは別経路です。

**Vibe 設定例**（詳細は [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md)）:
```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp[cli]>=1.0.0,<2",
        "--with", "mistralai>=1.0.0,<2",
        "--no-project",
        "/absolute/path/to/mmq.py",
        "--mcp"
      ],
      "env": {
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

設定後、Vibe を再起動し、エージェントに tool `ask_mistral` を使わせます（モデルは tool 引数 `model` で指定、例: `mistral-large-latest`）。

**Claude Desktop 設定例 (claude_desktop_config.json):**
```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "uv",
      "args": [
        "run",
        "--with", "mcp[cli]>=1.0.0,<2",
        "--with", "mistralai>=1.0.0,<2",
        "--no-project",
        "/absolute/path/to/mmq.py",
        "--mcp"
      ],
      "env": {
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```

MCP ツール仕様 (ask_mistral)

MCP サーバーモード起動時、クライアント側からは ask_mistral ツールとしてアクセスできます。

| 引数名 | 型 | デフォルト値 | 説明 |
|---|---|---|---|
| prompt | string | null | 単発の入力プロンプトテキスト |
| messages | array | null | 会話履歴オブジェクトの配列 ([{"role": "...", "content": "..."}]) |
| model | string | "mistral-small-latest" | 利用する Mistral モデル名 |
| system_prompt | string | null | カスタムシステムプロンプト (prompt 指定時のみ有効) |
| priority | number | 2 | タスク優先度 (1: 高, 2: 通常, 3: 低) |

管理データの保存先

排他制御用のテンポラリ DB は、ユーザーごとにパーミッション 0700 で作成された専用ディレクトリに保存されます。
 * キュー管理 DB: /tmp/mcp_mistral_queue_<USER>/mcp_mistral_flow_control.db

テスト

```bash
# 単体 + e2e（Fake API、ネットワーク不要）
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/ -v -m "not live"

# e2e のみ
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e -v -m "not live"

# 本物 API（任意・無料枠を消費）
export MISTRAL_API_KEY=...
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e/test_live_api.py -v -m live
```

e2e は `MMQ_FAKE_API=1` と短い `MMQ_BASE_WAIT_TIME` でプロセス境界（CLI / MCP stdio）を検証します。
Vibe UI 経由の手動確認は [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) を参照してください。

ライセンス

MIT License

Copyright (c) 2026 kench
