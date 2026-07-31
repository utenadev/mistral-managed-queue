# mcp-mistral-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

Mistral API の無料枠（約 1 リクエスト/30 秒）向けに、ローカルや複数プロセス・MCP クライアントからの呼び出しを共有 SQLite キューで調停する MCP (Model Context Protocol) サーバー兼 CLI ツールです。
WAL モードの SQLite と非同期キューで開始間隔を協調し、単一 in-flight で順番に処理します（ベストエフォートの交通整理であり、公式の SLA 保証ではありません）。

## 主な特徴

 * **自動レート制限調停**: 共有の約 31 秒間隔で開始を協調し、429 時は共有バックオフ後にゲートを再通過。成功時は既定間隔へ復帰。
 * **マルチプロセス&優先度制御**: 複数プロセス・タスクからの同時呼び出しに対応。優先度 (1–3) と単一 in-flight でキューを整理。
 * **柔軟なモデル&メッセージ指定**: 任意の Mistral チャットモデル名（デフォルト `mistral-small-latest`。例: `mistral-large-latest`, `codestral-latest`）と、会話履歴（`messages` 配列）に対応。
 * **ストリーミング&キャンセル**: Mistral API レスポンスを内部でストリーム処理（ツールは全文を返却）。クライアント側キャンセル（`CancelledError`）時は DB 状態を更新。
 * **ローカル制御 DB**: ユーザー専用ディレクトリ（パーミッション `0700`）配下にテンポラリ DB を配置（`MMQ_TEMP_DB_PATH` で上書き可）。
 * **uv 対応**: PEP 723 (Inline Script Metadata)。`uv run` で依存を解決。
 * **Mistral Vibe 連携**: MCP サーバー（`--mcp`）として Vibe / Claude Desktop 等に登録可能。CLI 直実行は `uv run` を使用（`vibe mmq.py ...` では動かない）。

## 前提条件

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) がインストールされていること（0.1.0 以上を推奨）
 * Mistral API キー（`MISTRAL_API_KEY`）

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```

## 使い方

### 1. CLI モード（直接実行）

**スクリプト実行は `uv run` を使います。**  
`vibe` コマンドは Mistral Vibe の**エージェント CLI** であり、`vibe mmq.py "..."` のようには動きません。

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

# 緊急ブレーキ: キュー投入済み / スタックした作業をキャンセル（API は呼ばない）
uv run mmq.py --purge          # pending をすべてキャンセル
uv run mmq.py --purge-all      # pending + processing をキャンセル
uv run mmq.py --purge-id 42    # 指定 ID をキャンセル
```

### 2. MCP サーバーモード（Mistral Vibe / 他クライアント連携）

Vibe、Claude Desktop、OpenCode、Goose などから **MCP ツール `ask_mistral`** として呼びます。  
CLI の `uv run mmq.py "..."` とは別経路です。

このリポジトリの `mmq.py` への **絶対パス** を使ってください（PyPI 未公開）。  
`uv run` が PEP 723 の依存を解決します。詳細は [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md)。

**Vibe / Claude Desktop 設定例**（`claude_desktop_config.json` など）:

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

設定後、クライアントを再起動し、エージェントに tool `ask_mistral` を使わせます（モデルは tool 引数 `model` で指定、例: `mistral-large-latest`）。

> **PyPI 公開後:** `uvx` や公開パッケージ経由の起動に置き換え可能になります。console script 名は `mmq`（`pyproject.toml` 参照）であり、`mcp-mistral-queue` ではありません。進捗は [docs/tasks.md](docs/tasks.md) を参照。

### MCP ツール

サーバー起動中、クライアントは次のツールを利用できます。

#### `ask_mistral`

| 引数名 | 型 | デフォルト値 | 説明 |
|---|---|---|---|
| prompt | string | null | 単発の入力プロンプトテキスト |
| messages | array | null | 会話履歴オブジェクトの配列 (`[{"role": "...", "content": "..."}]`) |
| model | string | `"mistral-small-latest"` | 利用する Mistral モデル名 |
| system_prompt | string | null | カスタムシステムプロンプト（`prompt` 指定時のみ有効） |
| priority | number | 2 | タスク優先度（1: 高, 2: 通常, 3: 低） |

#### `get_queue_status`

共有キュー / レート制限の状態を JSON で返します:

| フィールド | 型 | 説明 |
|---|---|---|
| pending | number | キュー待ちタスク数 |
| processing | number | 実行中（claim 済み）タスク数 |
| seconds_until_next_slot | number | 次の API スロットまでの秒数 |
| current_wait_interval | number | 現在の共有待機間隔（秒） |
| in_flight | boolean | 実行中タスクがあるか |

## 管理データの保存先

排他制御用のテンポラリ DB は、ユーザーごとにパーミッション `0700` で作成された専用ディレクトリに保存されます。

 * デフォルト: `<tempdir>/mcp_mistral_queue_<USER>/mcp_mistral_flow_control.db`  
   （`tempfile.gettempdir()`。Linux では多くの場合 `/tmp`）
 * 上書き: `MMQ_TEMP_DB_PATH` に DB ファイルのフルパスを指定（親ディレクトリは `0700` で作成）

## テスト

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

## ライセンス

MIT License

Copyright (c) 2026 utenadev
