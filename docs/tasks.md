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
| ✅ 完了 | ソース英語化（docstring / argparse / 例外） | P1 | 1h |
| ✅ 完了 | README 多言語構成（en / ja / fr） | P1 | 2h |
| ✅ 完了 | README 実装整合（path 主導・overclaim 除去） | P1 | 1h |
| ✅ 完了 | B: 小粒クリーンアップ（LICENSE / both-args / `__all__` / to_thread） | P1 | 1h |
| ✅ 完了 | A: `get_queue_status` + テスト + 三言語 README | P1 | 2h |
| ✅ 完了 | C: `--purge` / `--purge-all` / `--purge-id` | P1 | 1.5h |
| ✅ 完了 | D: PyPI 公開 (`mcp-mistral-queue` 0.1.0) | P1 | 0.5h |

---

## 🎯 今後のタスク

### 高優先度 (P1)

| 状況 | タスク | 説明 | 見積 | 依存 |
|------|-------|------|------|------|
| ⏳ | uv 最小バージョンを必須に | 前提条件を明確化（README / pyproject） | 0.2h | - |
| ✅ | `export` / コードブロック整形 | 現行 README は fenced block で問題なし | 0.5h | - |
| ✅ | PyPI へ `uv publish` | `mcp-mistral-queue==0.1.0` 公開済み | 0.5h | - |
### 中優先度 (P2)

| 状況 | タスク | 説明 | 見積 | 依存 |
|------|-------|------|------|------|
| ⏳ | `get_secure_temp_db_path()` のセキュリティ強化 | ownership 検証を追加 | 1h | - |
| ⏳ | Mistral SDK バージョン固定 | 現状は `>=1.0.0,<2` レンジ。厳密ピンが必要なら | 0.5h | - |
| ⏳ | `/tmp` から `XDG_RUNTIME_DIR` へ移行 | DB 保存先を変更（現状は `tempfile.gettempdir()`） | 1h | - |
| ⏳ | 非同期 DB 接続 (aiosqlite) | DB 操作を非同期化 | 2h | - |
| ✅ | 429 エラーのリトライ前に待機 | P0 で実装済み（共有バックオフ → ゲート再通過） | 1h | - |
| ⏳ | Progress total の動的化 | ストリームの総数を動的に | 1h | - |
| ✅ | DB 操作を全て `asyncio.to_thread` に | async 経路から `init_db` / `clean_zombie` を offload 済み | 1h | - |
| ⏳ | HTTP ステータスコード優先判定 | エラーチェックを強化 | 0.5h | - |
| ✅ | pyproject.toml build 設定修正 | hatch wheel/sdist + `mmq` script 済み | 0.5h | - |
| ✅ | 両方指定時エラー | `prompt` と `messages` 同時指定を拒否 | 0.5h | - |
| ⏳ | status/priority インデックス | DB パフォーマンス向上 | 1h | - |
| ⏳ | 構造化エラー返却 | エラー情報を充実 | 1h | - |
| ✅ | LICENSE 末尾改行 | 末尾改行を追加済み | 0.1h | - |

---

## 🚀 機能追加メモ

### 1. ライブラリ機能のブラッシュアップ

_nanobot や API サーバーから Python モジュールとしてインポートしやすくするための整備_

- [x] **`__all__` による公開 API の明示 (`mmq.py`)**

  ```python
  __all__ = ["MistralRequest", "execute_mistral_queue_async", "ask_mistral", "get_queue_status"]
  ```

- [ ] **設定パラメータのコード側オーバーライド対応**

  - `execute_mistral_queue_async(req, db_path=..., ...)` のように、環境変数 (`MMQ_TEMP_DB_PATH` 等) に依存せず、呼び出し時の引数で DB パスや待機時間を直接指定できるようにする。

### 2. PyPI パッケージ公開

_絶対パス指定や Git URL 指定をなくし、`uvx`・`pip` 一発で使えるようにする_

- [x] **`uv build` 成功** (`dist/mcp_mistral_queue-0.1.0-*.whl` / sdist; entry point `mmq`)
- [x] **PyPI への公開 (`uv publish`)** — `mcp-mistral-queue==0.1.0`  
  https://pypi.org/project/mcp-mistral-queue/

  - **MCP 設定:** `uvx --from mcp-mistral-queue mmq --mcp`（README に path 形と併記）
  - **CLI:** `mmq "..."` / `uvx --from mcp-mistral-queue mmq "..."`

### 3. `--purge` コマンド（緊急ブレーキ機能）

_AI Agent の誤作動や大量連投をリセットするための JOB 強制取り消し_

- [x] **`--purge` オプションの追加** — pending → cancelled
- [x] **`--purge-all` オプションの追加** — pending + processing → cancelled
- [x] **`--purge-id ID`** — 指定タスクを cancelled

### 4. 機能追加・デフォルト設定の変更

- [x] **`get_queue_status` MCPツールの実装**

  - unit + MCP e2e + en/ja/fr README 反映済み

- [ ] **デフォルトモデルの更新**

  - デフォルトモデルを `mistral-medium-3-5` に変更（コード `DEFAULT_MODEL`・テスト・全言語 README を同時）。
  - コードを変える前に README だけ先に書き換えない。

- [ ] _(保留)_ CLI完了通知 (macOS/Linux)

  - 外部依存が増えるため優先度は下げ、必要に応じて検討。

### 5. ソースコードの英語化

- [x] **ソースコード内のメッセージ英語化**

  - [x] Docstring (`MistralRequest`, `ask_mistral`, `main` など)
  - [x] `argparse` の `help` および `epilog`
  - [x] 例外メッセージ (`ValueError` など)

  _コミット済み。_

### 6. ドキュメントの再構成・多言語対応

- [x] **README ファイル構成の変更**
- [x] **README 記載内容の実装整合（公開前）**
- [x] **ツール一覧に `get_queue_status`**
- [x] **`uvx --from mcp-mistral-queue mmq --mcp` 形を README に併記**（インデックス未公開の注記付き）
- [ ] **デフォルトモデルを `mistral-medium-3-5` に修正**（コード変更と同時）
- [x] **PyPI 公開後:** 「until on the index」注記を削除

---

## 📂 ファイル構成

```
docs/
├── NOTES.md          # 機能検討ログ・バックログ
├── SMOKE_VIBE.md     # Vibe 手動スモーク
└── tasks.md          # タスク管理 (本ファイル)
```

---

## 🧭 実行プラン進捗

| ステップ | 状況 |
|----------|------|
| commit（英語化 + tasks） | ✅ |
| B クリーンアップ | ✅ |
| A `get_queue_status` | ✅ |
| C `--purge*` | ✅ |
| D PyPI | ✅ `mcp-mistral-queue==0.1.0` 公開 |

---

*最終更新: 2026-07-31*
