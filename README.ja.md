# mistral-managed-queue

[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)

[![PyPI](https://img.shields.io/pypi/v/mistral-managed-queue)](https://pypi.org/project/mistral-managed-queue/)

CLIツールおよびMCP（Model Context Protocol）サーバーで、SQLite共有キューを介してMistral無料プラン（約30秒に1リクエスト）へのローカルおよびマルチプロセス/マルチクライアント呼び出しを調整します。
SQLite（WALモード）と非同期キューイングを使用し、1つの進行中タスクでリクエスト開始を間隔を空けて実行します。これはベストエフォートのトラフィック制御であり、公式のSLAではありません。

**パッケージ:** [`mistral-managed-queue`](https://pypi.org/project/mistral-managed-queue/) on PyPI · **コンソールスクリプト名:** `mmq`（パッケージ名ではない）· **現在のリリース:** `0.2.0`

## 機能

 * **自動レート制限調整**: 共有の約31秒間隔で開始。429エラー時に共有バックオフを実行し、再度ゲートに入る。成功時には基本の間隔にリセット。
 * **マルチプロセス・優先度制御**: 複数のプロセス/タスクが作業をキューに登録可能。優先度（デフォルト2。値が大きいほど先に処理）と単一の進行中タスクによりキューが並べられる。
 * **柔軟なモデル・メッセージオプション**: Mistralのチャットモデル名（デフォルトは`mistral-small-latest`。例: `mistral-large-latest`、`codestral-latest`）。
 * **ストリーミング・キャンセル処理**: Mistral APIレスポンスを内部でストリーミング（ツールは完全なテキストを返す）。クライアントによるキャンセル（`CancelledError`）時にタスクステータスをDBで更新。
 * **ローカル制御DB**: ユーザーごとの一時ディレクトリ下にモード`0700`で作成されるDB（パスは`MMQ_TEMP_DB_PATH`で上書き可能）。
 * **PyPI / uvx**: 一度インストールするか、エフェメラルに実行。エントリポイントは`mmq`。
 * **カタログ取得** (extras): プロバイダのモデルカタログ取得 — [docs/README_extras_Catalog.md](docs/README_extras_Catalog.md) を参照
 * **無料プランに最適**: ドキュメント翻訳などの、専用のレート制限スタックを消費せずに約31秒間隔で待機できるジョブに適しています。

## 前提条件

 * Python 3.10+
 * [uv](https://github.com/astral-sh/uv) 推奨（`uvx` / `uv run`）。`pip`でも動作
 * Mistral APIキー（`MISTRAL_API_KEY`）

```bash
export MISTRAL_API_KEY="your-mistral-api-key"
```


## インストール（PyPI）

[PyPI](https://pypi.org/project/mistral-managed-queue/)で公開・検証済み。

```bash
# One-shot (no permanent install) — recommended for MCP hosts
uvx --from mistral-managed-queue mmq --help

# Or install into an environment
uv pip install mistral-managed-queue
# pip install mistral-managed-queue

mmq --help
```


**簡易テスト（`MISTRAL_API_KEY`が必要。無料プランのクォータ消費あり）**:

```bash
uvx --from mistral-managed-queue mmq ask "Reply with pong only."
```


**注意**:

 * コンソールスクリプト名は**`mmq`**。誤: `uvx mistral-managed-queue ...`。正: `uvx --from mistral-managed-queue mmq ...`。
 * コア依存関係: `mcp[cli]>=1.0.0,<2`、`mistralai>=1.0.0,<2`。カタログ取得には `httpx` と `PyYAML` が必要（`pip install mistral-managed-queue[catalog]`）。

## 使用方法

CLIはサブコマンドベース: `mmq ask`、`mmq fetch`、`mmq work`、`mmq purge`、`mmq catalog`、`mmq mcp`。

### 1. `ask` — 直接API呼び出し（キューをバイパス）

プロンプトを直ちにMistral APIに送信し、レスポンスを出力します。

```bash
# Basic run (default model: mistral-small-latest)
uvx --from mistral-managed-queue mmq ask "Explain Python list comprehensions briefly"
# or: mmq ask "Explain Python list comprehensions briefly"

# Choose a model (e.g. mistral-large-latest, codestral-latest)
mmq ask -m mistral-large-latest "Explain a complex algorithm"

# Custom system prompt
mmq ask -s "You are an AI that speaks casually." "How is the weather today?"

# JSON output for easy parsing
mmq ask -j "What is ownership in Rust?"
```


### 2. `fetch` — 非同期処理用にキューに登録

プロンプトを共有キューに登録します。**処理はここで行われません** — キューを処理するには`mmq work`を実行してください。

```bash
# Enqueue with default priority (2)
mmq fetch "Summarize this document"

# Choose a model / system prompt / priority
mmq fetch -m mistral-large-latest -s "Be concise" -p 1 "Translate this to Japanese"
```


**優先度**: 値が大きいほど先に処理されます（`ORDER BY priority DESC`）。デフォルトは`2`。

### 3. `work` — キューを処理（ワーカーモード）

保留中のタスクを優先度順（高い順。同一優先度内はFIFO）で処理し、各タスクを共有レートゲートを通して実行します。

```bash
mmq work            # drain all currently pending tasks
mmq work --once     # process exactly one task and exit
mmq work --watch    # keep processing new tasks until interrupted (Ctrl-C)
```


### 4. `purge` — キュー内タスクのキャンセル

```bash
mmq purge --pending   # delete all pending tasks
mmq purge --all       # delete every task (including completed/failed)
mmq purge --id 42     # delete a specific task by ID
```


## 環境変数（オプション）

| 変数 | デフォルト | 用途 |
|---|---|---|
| `MISTRAL_API_KEY` | （必須） | Mistral APIキー |
| `MMQ_TEMP_DB_PATH` | ユーザーごとの一時ディレクトリ下 | 共有キューDBファイルパス |
| `MMQ_BASE_WAIT_TIME` | `31` | 開始間隔（無料プランペーシング） |
| `MMQ_MAX_WAIT_TIME` | `300` | 最大バックオフ待機時間 |
| `MMQ_MIN_SLEEP_INTERVAL` | `2` | リトライ間の最小スリープ時間 |
| `MMQ_BACKOFF_MULTIPLIER` | `2.0` | 429エラー時のバックオフ倍率 |
| `MMQ_PROCESSING_TIMEOUT` | `120` | ゾンビタスクタイムアウト（秒） |
| `MMQ_DEFAULT_MODEL` | `mistral-small-latest` | デフォルトモデル名 |
| `MMQ_ENABLE_MCP` | オフ | MCPサーバー / `mcp`サブコマンドを有効化（`1`/`true`） |
| `MMQ_CATALOG_BASE_WAIT_TIME` | `MMQ_BASE_WAIT_TIME` | カタログ取得ペーシング |
| `MMQ_CATALOG_MAX_WAIT_TIME` | `MMQ_MAX_WAIT_TIME` | カタログ取得最大バックオフ |
| `MMQ_FAKE_API` | オフ | オフライン / e2e: フェイククライアント（`1`/`true`） |
| `MMQ_FAKE_RESPONSE` | — | 固定フェイクレスポンストext（テスト用） |
| `MMQ_FAKE_FAIL` | — | `429`または`error`で障害をシミュレート（テスト用） |

## 制御データの保存場所

調整用の一時DBは、モード`0700`で作成されるユーザーごとのディレクトリに保存されます:

 * デフォルト: `<tempdir>/mistral_managed_queue_<USER>/mistral_managed_flow_control.db`
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


e2eテストでは`MMQ_FAKE_API=1`と短い`MMQ_BASE_WAIT_TIME`を使用してプロセス境界（CLI / MCP stdio）をテストします。
Vibe UIの手動チェックについては、[docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md)を参照してください。

## mmqのバッチ利用例（`scripts/translate_readme.py`）

CLIやMCPサーバーに加えて、Pythonからキューを呼び出すこともできます。このリポジトリにはサンプルが同梱されています:

**[`scripts/translate_readme.py`](scripts/translate_readme.py)** — 英語ソースからロケール別READMEを再生成（`mmq` / `ask_mistral`と同じ無料プランのキューを使用）。

| アイデア | mmqに適している理由 |
|------|-----------------|
| 断続的なジョブ | ドキュメント変更はチャットトラフィックよりもはるかに頻度が低い |
| 約31秒待機可能 | ja → frの各翻訳でゲート付きスロットを消費 |
| 共有DB | マシン上の他の無料プランクライアントをバイパスしない |
| プログラム的API | `execute_mistral_queue_async` + `MistralRequest`を使用 |


```bash
export MISTRAL_API_KEY=...
# optional: TRANSLATE_MODEL=mistral-small-latest

# From a git checkout (imports the mmq package on PYTHONPATH via the script)
python scripts/translate_readme.py --lang ja    # one language
python scripts/translate_readme.py --dry-run    # preview, no write
```


サンプルの動作:

1. 囲みコードブロック（行ベースFSM）とインラインの``code``をプレースホルダーで保護
2. **`execute_mistral_queue_async`**を通して各言語の翻訳ジョブをキューに登録
3. プレースホルダーを復元し、言語スイッチャーを修正、検証（例: 囲みブロックのバランス）
4. アトミックに出力を書き込み

頻繁でないバッチジョブ（要約、構造化抽出など）のテンプレートとして使用でき、無料プランゲートを共有します。

## 謝辞

- Mistral API無料プランに関する情報を共有してくれた**sioois**氏
([リンク](https://zenn.dev/sioois/articles/dea773011514b1))。
- SQLite WALモードでのキュー利用に関する知見を提供してくれた**@fujibee**氏（#agmsg）。
- AIに優しいCLI開発手法を提供してくれた**shunsuke_suzuki**氏
([リンク](https://zenn.dev/shunsuke_suzuki/articles/make-cli-ai-friendly))。

みなさまに感謝します！

## その他のドキュメント

 * [docs/SMOKE_VIBE.md](docs/SMOKE_VIBE.md) — Vibe / MCP手動テスト
 * [docs/SEARCH_POSITIONING.md](docs/SEARCH_POSITIONING.md) — ウェブ検索の位置付け（mmqベース外）
 * [docs/tasks.md](docs/tasks.md) — バックログ
 * [docs/NOTES.md](docs/NOTES.md) — 設計ノート

## ライセンス

MIT License

Copyright (c) 2026 utenadev
