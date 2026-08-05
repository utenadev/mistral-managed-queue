# mcp-mistral-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

[![PyPI](https://img.shields.io/pypi/v/mcp-mistral-queue)](https://pypi.org/project/mcp-mistral-queue/)

MCP（Model Context Protocol）サーバーおよびCLIツール。SQLite共有キューを介して、Mistral無料プラン（約30秒に1リクエスト）へのローカルおよびマルチプロセス/マルチクライアント呼び出しを調整します。
SQLite（WALモード）と非同期キューイングを使用し、1つの進行中タスクでリクエスト開始を間隔を空けて実行します。これはベストエフォートのトラフィック制御であり、公式のSLAではありません。

**パッケージ:** [`mcp-mistral-queue`](https://pypi.org/project/mcp-mistral-queue/)（PyPI） · **コンソールスクリプト名:** `mmq`（パッケージ名ではない） · **現在のリリース:** `0.1.2`

## 機能

 * **自動レート制限調整**: 共有の約31秒間隔で開始。429エラー時は共有バックオフ後に再度ゲートに入る。成功時は基本間隔にリセット。
 * **マルチプロセス・優先度制御**: 複数のプロセス/タスクが作業をキューに登録可能。優先度（1-3）と単一進行中処理によりキューが順序付けられる。
 * **柔軟なモデル・メッセージオプション**: Mistralのチャットモデル名（デフォルトは`mistral-small-latest`。例: `mistral-large-latest`、`codestral-latest`）と、`messages`配列による完全な会話履歴をサポート。
 * **ストリーミング・キャンセル処理**: Mistral APIレスポンスを内部でストリーミング（ツールは完全なテキストを返却）。クライアントキャンセル時（`CancelledError`）はDB内のタスクステータスを更新。
 * **ローカル制御DB**: パーミッション`0700`のユーザーごとの一時ディレクトリ内にDBを作成（パスは`MMQ_TEMP_DB_PATH`で上書き可能）。
 * **PyPI / uvx**: 一度インストールするか、エフェメラルに実行。エントリポイントは`mmq`。
 * **Mistral Vibe / Grok / Claude Desktop**: MCPサーバーとして登録（`mmq --mcp`）。`vibe mmq.py "..."`は使用しないこと。これはVibeのエージェントCLIであり、このツールではない。
 * **無料プランに最適**: ドキュメント翻訳などの散発的なジョブに適しており、専用のレート制限スタックを消費せずに約31秒間隔で呼び出し可能。
 * **AIフレンドリーなCLI**: Vibe、Claude Codeなどのコーディングエージェント向けに設計。`docs list` / `docs show`サブコマンド、ヘルプテキスト内のエージェント向けガイド、パースしやすいJSON出力を提供。

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


**簡易テスト（`MISTRAL_API_KEY`が必要。無料プランの割当を消費）**:

```bash
uvx --from mcp-mistral-queue mmq "Reply with pong only."
```


**注意事項**:
 * コンソールスクリプト名は**`mmq`**。誤: `uvx mcp-mistral-queue --mcp`。正: `uvx --from mcp-mistral-queue mmq --mcp`。
 * 依存関係: `mcp[cli]>=1.0.0,<2`、`mistralai>=1.0.0,<2`（パッケージにより自動インストール）。

## 使用方法

### 1. CLIモード

PyPIインストール後または`uvx`経由で、**`mmq`** を実行。
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

# New structured purge subcommand (recommended for scripts/AI)
mmq purge --pending   # cancel all pending tasks
mmq purge --all       # cancel all pending + processing tasks
mmq purge --id 42     # cancel specific task by ID
```


### AIフレンドリーなドキュメントコマンド

Vibe、Claude Codeなどのコーディングエージェント向け:

```bash
# List all available documentation
mmq docs list

# Show specific documentation (returns markdown content)
mmq docs show usage
mmq docs show install
mmq docs show mcp
mmq docs show rate-limit
mmq docs show troubleshooting
mmq docs show examples
```


**`docs list`** コマンドはJSON形式で出力され、パースしやすい説明を含む:

```json
{
  "results": [
    {"name": "usage", "description": "Usage guide and examples for mcp-mistral-queue CLI"},
    {"name": "install", "description": "Installation instructions for mcp-mistral-queue"}
  ],
  "help": "If you are a coding agent, run `mmq docs show {name}` to see details."
}
```


### 2. MCPサーバーモード（Vibe / Grok / Claude Desktop / …）

MCPホストに**`ask_mistral`** と**`get_queue_status`** を公開。
CLIプロンプトとはパスを分離。

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


既に`mmq`が`PATH`（venv / `uv pip install`）にインストールされている場合:

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


設定変更後はクライアントを再起動。Vibe UIの手動チェックは [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) を参照。

### 3. 環境変数（オプション）

| 変数 | デフォルト | 用途 |
|---|---|---|
| `MISTRAL_API_KEY` | （必須） | Mistral APIキー |
| `MMQ_TEMP_DB_PATH` | ユーザーごとのtempdir配下 | 共有キューDBファイルパス |
| `MMQ_BASE_WAIT_TIME` | `31` | 開始間隔（秒、無料プランペーシング） |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | デフォルトモデル名 |
| `MMQ_FAKE_API` | オフ | オフライン/エンドツーエンドテスト: フェイククライアント（`1`/`true`） |

その他の調整用パラメータ（`MMQ_MAX_WAIT_TIME`、`MMQ_MAX_RETRIES`、…）も存在。詳細は`mmq.py`を参照。

### MCPツール

サーバー実行中、クライアントは以下のツールを使用可能:

#### `ask_mistral`

| 引数 | 型 | デフォルト | 説明 |
|---|---|---|---|
| prompt | string | null | 単発のユーザープロンプトテキスト |
| messages | array | null | 会話履歴（`[{"role": "...", "content": "..."}]`） |
| model | string | `"mistral-small-latest"` | Mistralモデル名 |
| system_prompt | string | null | カスタムシステムプロンプト（`prompt`使用時のみ） |
| priority | number | 2 | タスク優先度（1: 高、2: 標準、3: 低） |

#### `get_queue_status`

現在の共有キュー・レート制限ステータスをJSONで返却:

| フィールド | 型 | 説明 |
|---|---|---|
| pending | number | キュー内の待機タスク数 |
| processing | number | 現在処理中のタスク数 |
| seconds_until_next_slot | number | 共有APIゲートが開くまでの秒数 |
| current_wait_interval | number | アクティブな共有待機間隔（秒） |
| in_flight | boolean | 現在処理中のタスクがあるかどうか |

## 制御データの保存場所

調整用の一時DBは、パーミッション`0700`で作成されるユーザーごとのディレクトリに保存:

 * デフォルト: `<tempdir>/mcp_mistral_queue_<USER>/mcp_mistral_flow_control.db`
   （`tempfile.gettempdir()`、Linuxでは`/tmp`が一般的）
 * 上書き: `MMQ_TEMP_DB_PATH` にフルパスを設定（親ディレクトリは`0700`で作成）

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


e2eテストでは`MMQ_FAKE_API=1`と短い`MMQ_BASE_WAIT_TIME`を使用してプロセス境界（CLI / MCP stdio）を検証。
Vibe UIの手動チェックは [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) を参照。

## サンプル: mmqのバッチ的な使用法（`scripts/translate_readme.py`）

CLIやMCPサーバーの他に、Pythonからキューを呼び出すことも可能。このリポジトリにはサンプルが同梱されている:

**[`scripts/translate_readme.py`](scripts/translate_readme.py)** — 英語ソースからロケール版READMEを**`mmq` / `ask_mistral`と同じ無料プランのキュー**を介して再生成。

| アイデア | mmqに適している理由 |
|------|-----------------|
| 散発的なジョブ | ドキュメント変更はチャットほど頻繁ではない |
| 約31秒待てる | ja → fr の各翻訳でゲート付きスロットを使用 |
| 共有DB | マシン上の他の無料プランクライアントを回避しない |
| プログラム的API | `execute_mistral_queue_async` + `MistralRequest` を使用 |

```bash
export MISTRAL_API_KEY=...
# optional: TRANSLATE_MODEL=mistral-small-latest

# From a git checkout (imports mmq.py on PYTHONPATH via the script)
python scripts/translate_readme.py --lang ja    # one language
python scripts/translate_readme.py --dry-run    # preview, no write
```


サンプルの動作:
1. 囲みコードブロック（行ベースFSM）とインライン``code``をプレースホルダーで保護
2. **`execute_mistral_queue_async`** を介して各言語の翻訳ジョブを1つずつキューに登録
3. プレースホルダーを復元、言語スイッチャーを修正、検証（例: 囲みブロックのバランス）
4. アトミックに出力を書き込み

散発的なバッチジョブ（要約、構造化抽出など）のテンプレートとして使用可能。無料プランゲートを共有する。

## 謝辞

- Mistral API無料プランに関する情報を共有してくれた **sioois** 氏
([リンク](https://zenn.dev/sioois/articles/dea773011514b1))。
- SQLite WALモードでのキュー使用に関する知見を提供してくれた **@fujibee** 氏（#agmsg）。
- AIフレンドリーなCLI開発手法を提供してくれた **shunsuke_suzuki** 氏
([リンク](https://zenn.dev/shunsuke_suzuki/articles/make-cli-ai-friendly))。

皆様に感謝します！

## 関連ドキュメント

 * [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) — Vibe / MCP マニュアルスモーク
 * [docs/SEARCH_POSITIONING.md](docs/SEARCH_POSITIONING.md) — ウェブ検索の位置付け（mmqベース外）
 * [docs/tasks.md](docs/tasks.md) — バックログ
 * [docs/NOTES.md](docs/NOTES.md) — 設計ノート

## ライセンス

MIT License

Copyright (c) 2026 utenadev
