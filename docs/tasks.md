# タスク管理

本ドキュメントは、mcp-mistral-queue の開発タスクを管理します。

---

## 📋 タスク状況概要

| 状況 | タスク | 優先度 | 見積 |
|------|------|--------|------|
| ✅ 完了 | P0: 例外処理完全化 | P0 | 2h |
| ✅ 完了 | P0: 429 エラーバックオフ | P0 | 2h |
| ✅ 完了 | P1: Magic Numbers 定数化 | P1 | 1h |
| ✅ 完了 | P1: ロギングモジュール導入 | P1 | 1h |
| ✅ 完了 | P1: 関数分割 | P1 | 2h |
| ✅ 完了 | P1: テスト追加 | P1 | 2h |
| ✅ 完了 | Vibe CLI 対応 | P1 | 1h |
| ✅ 完了 | .gitignore 作成 | P1 | 0.5h |
| ✅ 完了 | pyproject.toml 作成 | P1 | 0.5h |

---

## 🎯 今後のタスク

### 高優先度 (P1)

| 状況 | タスク | 説明 | 見積 | 依存 |
|------|-------|------|------|------|
| ⏳ | uv 最小バージョンを必須に | 前提条件を明確化 | 0.2h | - |
| ⏳ | `export` コマンドのバッククオート統一 | README.md 内のコードブロックを整形 | 0.5h | - |

### 中優先度 (P2)

| 状況 | タスク | 説明 | 見積 | 依存 |
|------|-------|------|------|------|
| ⏳ | `get_secure_temp_db_path()` のセキュリティ強化 | ownership 検証を追加 | 1h | - |
| ⏳ | Mistral SDK バージョン固定 | SDK のバージョンを固定 | 0.5h | - |
| ⏳ | `/tmp` から `XDG_RUNTIME_DIR` へ移行 | DB 保存先を変更 | 1h | - |
| ⏳ | 非同期 DB 接続 (aiosqlite) | DB 操作を非同期化 | 2h | - |
| ⏳ | 429 エラーのリトライ前に待機 | バックオフ待機を実装 | 1h | - |
| ⏳ | Progress total の動的化 | ストリームの総数を動的に | 1h | - |
| ⏳ | DB 操作を全て `asyncio.to_thread` に | 一貫性を保つ | 1h | - |
| ⏳ | HTTP ステータスコード優先判定 | エラーチェックを強化 | 0.5h | - |
| ⏳ | pyproject.toml build 設定修正 | パッケージ化をサポート | 0.5h | - |
| ⏳ | 両方指定時エラー | `prompt` と `messages` 同時指定を防ぐ | 0.5h | - |
| ⏳ | status/priority インデックス | DB パフォーマンス向上 | 1h | - |
| ⏳ | 構造化エラー返却 | エラー情報を充実 | 1h | - |
| ⏳ | LICENSE 末尾改行 | 形式を整える | 0.1h | - |

---

## 🚀 機能追加メモ

### 1. ライブラリ機能のブラッシュアップ

_nanobot や API サーバーから Python モジュールとしてインポートしやすくするための整備_

- [ ] **`__all__` による公開 API の明示 (`mmq.py`)**

  ```python
  __all__ = ["MistralRequest", "execute_mistral_queue_async", "ask_mistral"]
  ```

- [ ] **設定パラメータのコード側オーバーライド対応**

  - `execute_mistral_queue_async(req, db_path=..., ...)` のように、環境変数 (`MMQ_TEMP_DB_PATH` 等) に依存せず、呼び出し時の引数で DB パスや待機時間を直接指定できるようにする。

### 2. PyPI パッケージ公開

_絶対パス指定や Git URL 指定をなくし、`uvx`・`pip` 一発で使えるようにする_

- [ ] **PyPI への公開 (`uv build` → `uv publish`)**

  - **MCP 設定の簡略化:** Claude Desktop / Vibe での起動コマンドを `uvx mcp-mistral-queue --mcp` に変更 (ローカルパス指定を不要に)

  - **他プロジェクト依存の簡略化:** `pyproject.toml` に `"mcp-mistral-queue"` と書くだけで連携可能に

  - **CLI 実行:** どこからでも `mmq` コマンドで単発実行できるように整備

### 3. `--purge` コマンド（緊急ブレーキ機能）

_AI Agent の誤作動や大量連投をリセットするための JOB 強制取り消し_

- [ ] **`--purge` オプションの追加**

  - `pending` 状態のタスクを一括で `cancelled` にする処理を実装する。

  ```sql
  UPDATE tasks SET status = 'cancelled' WHERE status = 'pending';
  ```

- [ ] **`--purge-all` オプションの追加**

  - `pending` + `processing` 状態のタスクを全削除

  ```sql
  UPDATE tasks SET status = 'cancelled' WHERE status IN ('pending', 'processing');
  ```

- [ ] **タスクID指定**: `purge <task_id>` で特定タスクを削除

  ```sql
  UPDATE tasks SET status = 'cancelled' WHERE id = ?;
  ```

### 4. 機能追加・デフォルト設定の変更

- [ ] **`get_queue_status` MCPツールの実装**

  - 待ち件数や次回実行スロットまでの秒数などを親エージェントに返すステータス確認ツールを追加。

  - レスポンス構造イメージ:

    ```json
    {
      "pending": 2,
      "processing": 1,
      "seconds_until_next_slot": 18.4,
      "current_wait_interval": 31.0,
      "in_flight": true
    }
    ```

  - **受け入れ条件（必須）:**
    - unit テスト（待ち件数・次スロット秒数・空キュー等のエッジ）
    - MCP e2e（`list_tools` に載る / call のレスポンス形）
    - README への記載は **実装＋テスト完了後**。en / ja を同時更新する
    - **未実装のまま README に載せない**（公開面の overclaim 禁止）

- [ ] **デフォルトモデルの更新**

  - デフォルトモデルを `mistral-medium-3-5` に変更（コード `DEFAULT_MODEL`・テスト・全言語 README を同時）。
  - コードを変える前に README だけ先に書き換えない。

- [ ] _(保留)_ CLI完了通知 (macOS/Linux)

  - 外部依存が増えるため優先度は下げ、必要に応じて検討。

### 5. ソースコードの英語化

- [ ] **ソースコード内のメッセージ英語化**

  - Docstring (`MistralRequest`, `ask_mistral`, `main` など)

  - `argparse` の `help` および `epilog`

  - 例外メッセージ (`ValueError` など)

### 6. ドキュメントの再構成・多言語対応

- [ ] **README ファイル構成の変更**

  - メイン `README.md` を英語化 (PyPI / GitHub 表示の標準に設定)。

  - 既存の日本語ファイルを `README.ja.md` に変更。

  - フランス語用の `README.fr.md` を追加。

  - 各 README の先頭に相互リンクを追加:

    ```markdown
    [English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)
    ```

- [ ] **README 記載内容の更新**

  - デフォルトモデルを `mistral-medium-3-5` に修正（コード変更と同時。現状コードは `mistral-small-latest`）。

  - `uvx` / `pip` 経由の起動例・MCP設定例 (`uvx mcp-mistral-queue --mcp`) は **PyPI 公開後** に。entry point は `mmq`（`mcp-mistral-queue` ではない点に注意）。公開前は path ベース `uv run` を主導線にする。

  - ツール一覧に `get_queue_status` を追加するのは **§4 実装＋テスト完了後**（未実装の先行記載はしない）。

---

## 📂 ファイル構成

```
docs/
├── NOTES.md          # 機能検討ログ・バックログ
└── tasks.md          # タスク管理 (本ファイル)
```

---

*最終更新: 2026-07-31*
