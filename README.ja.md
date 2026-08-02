# mcp-mistral-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

[![PyPI](https://img.shields.io/pypi/v/mcp-mistral-queue)](https://pypi.org/project/mcp-mistral-queue/)

MCP（Model Context Protocol）サーバーおよびCLIツール。Mistralの無料ティア（約30秒に1リクエスト）を、SQLiteキューを介してローカルおよびマルチプロセス/マルチクライアントの呼び出しを調整します。
SQLite（WALモード）と非同期キューイングを使用し、1つの処理中タスクでリクエスト開始を間隔を空けて実行します。これはベストエフォートのトラフィック制御であり、公式のSLAではありません。

**パッケージ:** [`mcp-mistral-queue`](https://pypi.org/project/mcp-mistral-queue/) on PyPI · **コンソールスクリプト名:** `mmq`（パッケージ名ではない）· **現在のリリース:** `0.1.1`

## 機能

 * **自動レート制限調整**: 共有の約31秒間隔で開始。429エラー時は共有バックオフ後に再度ゲートに入る。成功時は基本間隔にリセット。
 * **マルチプロセス・優先度制御**: 複数のプロセス/タスクがジョブを enqueue 可能。優先度（1-3）と単一処理中タスクによりキューが順序付けられる。
 * **柔軟なモデル・メッセージオプション**: Mistralのチャットモデル名（デフォルトは`mistral-small-latest`。例: `mistral-large-latest`、`codestral-latest`）と、`messages`配列による完全な会話履歴をサポート。
 * **ストリーミング・キャンセル処理**: Mistral APIレスポンスを内部でストリーミング（ツールは全文を返却）。クライアントキャンセル（`CancelledError`）時にDB内のタスクステータスを更新。
 * **ローカル制御DB**: パーミッション`0700`の一時DB（パスは`MMQ_TEMP_DB_PATH`で上書き可能）。
 * **PyPI / uvx**: 一度インストールするか、エフェメラルに実行。エントリポイントは`mmq`。
 * **Mistral Vibe / Grok / Claude Desktop**: MCPサーバーとして登録（`mmq --mcp`）。`vibe mmq.py "..."`は使用しないこと。これはVibeのエージェントCLIであり、このツールではない。
 * **無料ティアに最適**: ドキュメント翻訳などの偶発的なジョブで、31秒間隔で呼び出しを待てる場合に適合。

## 前提条件

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) 推奨（`uvx` / `uv run`）。`pip`でも動作
 * Mistral APIキー（`MISTRAL_API_KEY`）

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```


## インストール（PyPI）

[PyPI](https://pypi.org/project/mcp-mistral-queue/) に公開されており、検証済み。

```bash
# One-shot (no permanent install) — recommended for MCP hosts
uvx --from mcp-mistral-queue mmq --help

# Or install into an environment
uv pip install mcp-mistral-queue
# pip install mcp-mistral-queue

mmq --help
```


**簡易テスト（`MISTRAL_API_KEY`が必要。無料ティアのクォータにカウントされる）**:

```bash
uvx --from mcp-mistral-queue mmq "Reply with pong only."
```


**注意事項:**

 * コンソールスクリプト名は**`mmq`**。間違い: `uvx mcp-mistral-queue --mcp`。正解: `uvx --from mcp-mistral-queue mmq --mcp`。
 * 依存関係: `mcp[cli]>=1.0.0,<2`、`mistralai>=1.0.0,<2`（パッケージに同梱）。

## 使用方法

### 1. CLIモード

PyPIインストール後または`uvx`経由で、**`mmq`**を実行。
Gitチェックアウトからでも`uv run mmq.py ...`（PEP 723）で使用可能。

```bash
# Basic run (default model: mistral-small-latest)
uvx --from mcp-mistral-queue mmq "Explain Python list comprehensions briefly"
# or: mmq "Explain Python list comprehensions briefly"

# Choose a model (e.g. mistral-large-latest, codestral-latest)
mmq -m mistral-large-latest "Explain a complex algorithm"

# Custom system prompt
mmq -s "You are an AI that speaks casually." "How is the weather today?"

# Priority (1: high, 2: normal, 3: low)
mmq --priority 1 "Urgent question"

# Full conversation context as a messages JSON array
# (specify either prompt or --messages, not both)
mmq --messages '[{"role":"system","content":"Strict programmer"},{"role":"user","content":"What is ownership in Rust?"}]'

# Emergency brake: cancel queued / stuck work (no API call)
mmq --purge          # cancel all pending
mmq --purge-all      # cancel pending + processing
mmq --purge-id 42    # cancel one task by ID
```


### 2. MCPサーバーモード（Vibe / Grok / Claude Desktop / …）

MCPホストに**`ask_mistral`**および**`get_queue_status`**を公開。
CLIプロンプトとはパスを分ける。

#### PyPI / uvx（推奨）

```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "uvx",
      "args": ["--from", "mcp-mistral-queue", "mmq", "--mcp"],
      "env": {
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```


既に`mmq`が`PATH`（venv / `uv pip install`）に存在する場合:

```json
{
  "mcpServers": {
    "mistral-queue": {
      "command": "mmq",
      "args": ["--mcp"],
      "env": {
        "MISTRAL_API_KEY": "your-mistral-api-key"
      }
    }
  }
}
```


#### ローカルチェックアウト（開発）

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


設定変更後はクライアントを再起動。Vibe手動チェックリスト: [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md)。

### 3. 環境変数（任意）

| 変数 | デフォルト | 用途 |
|---|---|---|
| `MISTRAL_API_KEY` | （必須） | Mistral APIキー |
| `MMQ_TEMP_DB_PATH` | ユーザーごとのテンプディレクトリ下 | 共有キューDBファイルパス |
| `MMQ_BASE_WAIT_TIME` | `31` | 開始間隔（秒、無料ティアペーシング） |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | デフォルトモデル名 |
| `MMQ_FAKE_API` | オフ | オフライン/エンドツーエンド: フェイククライアント（`1`/`true`） |

その他の調整用パラメータ（`MMQ_MAX_WAIT_TIME`、`MMQ_MAX_RETRIES`、…）も存在。詳細は`mmq.py`を参照。

### MCPツール

サーバー実行中、クライアントは以下のツールを使用可能:

#### `ask_mistral`

| 引数 | 型 | デフォルト | 説明 |
|---|---|---|---|
| prompt | string | null | シングルショットユーザープロンプトテキスト |
| messages | array | null | 会話履歴（`[{"role": "...", "content": "..."}]`） |
| model | string | `"mistral-small-latest"` | Mistralモデル名 |
| system_prompt | string | null | カスタムシステムプロンプト（`prompt`使用時のみ） |
| priority | number | 2 | タスク優先度（1: 高、2: 標準、3: 低） |

#### `get_queue_status`

現在の共有キュー・レート制限ステータスをJSONで返却:

| フィールド | 型 | 説明 |
|---|---|---|
| pending | number | キュー内の待機タスク数 |
| processing | number | 処理中のタスク数 |
| seconds_until_next_slot | number | 共有APIゲートが開くまでの秒数 |
| current_wait_interval | number | アクティブな共有待機間隔（秒） |
| in_flight | boolean | 処理中タスクの有無 |

## 制御データの場所

調整用一時DBは、パーミッション`0700`で作成されるユーザーごとのディレクトリに保存される:

 * デフォルト: `<tempdir>/mcp_mistral_queue_<USER>/mcp_mistral_flow_control.db`
   （`tempfile.gettempdir()`、Linuxではしばしば`/tmp`）
 * 上書き: `MMQ_TEMP_DB_PATH`にフルパスを設定（親ディレクトリは`0700`で作成）

## テスト

```bash
# Unit + e2e (fake API; no network required)
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/ -v -m "not live"

# e2e only
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e -v -m "not live"

# Live API (optional; consumes free-tier quota)
export MISTRAL_API_KEY=...
uv run --with 'mcp[cli]>=1.0.0,<2' --with 'mistralai>=1.0.0,<2' \
  --with pytest --with pytest-asyncio --no-project \
  python -m pytest tests/e2e/test_live_api.py -v -m live
```


エンドツーエンドテストでは`MMQ_FAKE_API=1`と短い`MMQ_BASE_WAIT_TIME`を使用してプロセス境界（CLI / MCP stdio）をテスト。
Vibe UIの手動チェックは[docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md)を参照。

## 例: mmqのバッチスタイル使用（`scripts/translate_readme.py`）

CLIおよびMCPサーバーに加え、Pythonからキューを呼び出せる。このリポジトリにはサンプルを同梱:

**[`scripts/translate_readme.py`](scripts/translate_readme.py)** — 英語ソースからロケールREADMEを**`mmq`/`ask_mistral`と同じ無料ティアキュー**経由で再生成。

| アイデア | mmqに適合する理由 |
|------|-----------------|
| 偶発的なジョブ | ドキュメント変更はチャットトラフィックよりもはるかに頻度が低い |
| 約31秒待てる | 各言語（ja→fr）がゲート付きスロットを1つ消費 |
| 共有DB | マシン上の他の無料ティアクライアントをバイパスしない |
| プログラム的API | `execute_mistral_queue_async` + `MistralRequest`を使用 |


```bash
export MISTRAL_API_KEY=...
# optional: TRANSLATE_MODEL=mistral-small-latest

# From a git checkout (imports mmq.py on PYTHONPATH via the script)
python scripts/translate_readme.py --lang ja    # one language
python scripts/translate_readme.py --dry-run    # preview, no write
```


サンプルの動作:

1. 囲みコードブロック（行ベースFSM）とインライン``code``をプレースホルダーで保護
2. **`execute_mistral_queue_async`**経由で各言語の翻訳ジョブを1つずつ enqueue
3. プレースホルダーを復元、言語スイッチャーを修正、検証（例: 囲みブロックのバランス）
4. アトミックに出力を書き込み

その他の頻度の低いバッチジョブ（要約、構造化抽出）のテンプレートとして使用可能。無料ティアゲートを共有する。

## その他のドキュメント

 * [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) — Vibe / MCP手動スモーク
 * [docs/SEARCH_POSITIONING.md](docs/SEARCH_POSITIONING.md) — ウェブ検索の位置付け（mmqベース外）
 * [docs/tasks.md](docs/tasks.md) — バックログ
 * [docs/NOTES.md](docs/NOTES.md) — デザインノート

## ライセンス

MIT License

Copyright (c) 2026 utenadev
