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

---

## 🎯 今後のタスク

### 高優先度 (P1)

| 状況 | タスク | 説明 | 見積 | 依存 |
|------|-------|------|------|------|
| ⏳ | uv 最小バージョンを必須に | 前提条件を明確化（README / pyproject） | 0.2h | - |
| ✅ | `export` / コードブロック整形 | 現行 README は fenced block で問題なし | 0.5h | - |

### 中優先度 (P2)

| 状況 | タスク | 説明 | 見積 | 依存 |
|------|-------|------|------|------|
| ⏳ | `get_secure_temp_db_path()` のセキュリティ強化 | ownership 検証を追加 | 1h | - |
| ⏳ | Mistral SDK バージョン固定 | 現状は `>=1.0.0,<2` レンジ。厳密ピンが必要なら | 0.5h | - |
| ⏳ | `/tmp` から `XDG_RUNTIME_DIR` へ移行 | DB 保存先を変更（現状は `tempfile.gettempdir()`） | 1h | - |
| ⏳ | 非同期 DB 接続 (aiosqlite) | DB 操作を非同期化 | 2h | - |
| ✅ | 429 エラーのリトライ前に待機 | P0 で実装済み（共有バックオフ → ゲート再通過） | 1h | - |
| ⏳ | Progress total の動的化 | ストリームの総数を動的に | 1h | - |
| ⏳ | DB 操作を全て `asyncio.to_thread` に | `init_db` / `clean_zombie_tasks` はまだ同期直呼び | 1h | - |
| ⏳ | HTTP ステータスコード優先判定 | エラーチェックを強化 | 0.5h | - |
| ✅ | pyproject.toml build 設定修正 | hatch wheel/sdist + `mmq` script 済み | 0.5h | - |
| ⏳ | 両方指定時エラー | `prompt` と `messages` 同時指定を防ぐ | 0.5h | - |
| ⏳ | status/priority インデックス | DB パフォーマンス向上 | 1h | - |
| ⏳ | 構造化エラー返却 | エラー情報を充実 | 1h | - |
| ⏳ | LICENSE 末尾改行 | 現状末尾改行なし | 0.1h | - |

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

  - **MCP 設定の簡略化:** 公開後は README 主導線を `uvx` / インストール済み `mmq --mcp` に切替可能（entry point は **`mmq`**。パッケージ名 `mcp-mistral-queue` と混同しない）

  - **他プロジェクト依存の簡略化:** `pyproject.toml` に `"mcp-mistral-queue"` と書くだけで連携可能に

  - **CLI 実行:** どこからでも `mmq` コマンドで単発実行できるように整備

  - **公開前:** path ベース `uv run …/mmq.py --mcp` を主導線のまま（現状 README en/ja/fr 準拠）

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
    - README への記載は **実装＋テスト完了後**。en / ja / fr を同時更新する
    - **未実装のまま README に載せない**（公開面の overclaim 禁止）

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

  _注: 作業ツリー上 `mmq.py` に反映済み。未コミットなら commit 対象。_

### 6. ドキュメントの再構成・多言語対応

- [x] **README ファイル構成の変更**

  - [x] メイン `README.md` を英語化
  - [x] 日本語を `README.ja.md` に
  - [x] フランス語 `README.fr.md` を追加
  - [x] 先頭に相互リンク

- [x] **README 記載内容の実装整合（公開前）**

  - [x] path ベース `uv run …/mmq.py --mcp` を主導線に
  - [x] 未実装 `get_queue_status` を README に載せない
  - [x] default model 表記をコードと一致（`mistral-small-latest`）
  - [x] DB パスを `tempfile.gettempdir()` + `MMQ_TEMP_DB_PATH` に合わせて記載

- [ ] **README 記載内容の更新（機能・公開とセット）**

  - [ ] デフォルトモデルを `mistral-medium-3-5` に修正（§4 コード変更と同時）
  - [ ] `uvx` / 公開後の起動例（entry point `mmq`）を PyPI 公開後に
  - [ ] ツール一覧に `get_queue_status`（§4 実装＋テスト完了後）

---

## 📂 ファイル構成

```
docs/
├── NOTES.md          # 機能検討ログ・バックログ
├── SMOKE_VIBE.md     # Vibe 手動スモーク
└── tasks.md          # タスク管理 (本ファイル)
```

---

## 🧭 次にやること候補（議論用）

公開前のドキュメント/英語化は一通り揃った。残りは「機能」「運用」「公開」のどれを取るか。

| 優先候補 | 内容 | 理由 |
|----------|------|------|
| **A. `get_queue_status`** | MCP ツール + unit/e2e + 三言語 README | エージェントが待ち時間を判断できる。受け入れ条件は既に明文化済み |
| **B. 小粒クリーンアップ** | LICENSE 末尾改行 / `prompt`+`messages` 同時指定エラー / `__all__` / `init_db` の `to_thread` | 30分〜2h。公開前の体裁と API 明確化 |
| **C. `--purge`** | pending / all / id 取り消し | 誤爆連投時の緊急ブレーキ。CLI 運用向け |
| **D. PyPI 公開** | `uv build` → publish → README を `mmq`/`uvx` 主導に切替 | インストール摩擦を下げる。entry point 名に注意 |
| **E. デフォルトモデル変更** | `mistral-medium-3-5` へ（コード+テスト+README 同時） | 製品判断。無料枠・品質のトレードオフ確認が先 |

**おすすめの並び（案）:** 未コミット `mmq.py` 英語化を commit → **B（10分）** → **A（本丸）** → 必要なら C → 準備できたら D。  
E は A と独立だが「README をまた触る」ので A の README 更新と同じ PR に載せるか、別 PR で明示する。

---

*最終更新: 2026-07-31*
