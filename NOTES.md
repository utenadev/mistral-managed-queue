mcp-mistral-queue 機能検討ログ・バックログ

## Mistral Vibe / CLI 対応

### 実装済み

1. **PEP 723 Inline Script Metadata 対応**
   - mmq.py は PEP 723 に準拠したスクリプトメタデータを持つ
   - **直接実行は `uv run mmq.py "..."`**（依存は uv が解決）
   - 注意: 公式 `vibe` コマンドはエージェント CLI であり、`vibe mmq.py` では動かない

2. **CLI モード**
   - argparse を使用したコマンドラインオプション
   - 全てのパラメータ (`prompt`, `messages`, `model`, `system_prompt`, `priority`) をサポート
   - JSON 形式の messages 配列を受け付け

3. **MCP サーバーモード（Vibe 連携の本線）**
   - FastMCP を使用した MCP サーバー実装（`uv run mmq.py --mcp`）
   - `ask_mistral` ツールを登録
   - Vibe / Claude Desktop 等の MCP 設定から登録可能（docs/SMOKE_VIBE.md）

4. **ドキュメント**
   - README に uv run CLI と MCP 設定例
   - Vibe 手動 smoke は docs/SMOKE_VIBE.md

---

1. v1 に実装・採用された機能
初回リリースバージョン（v1）に盛り込まれた機能群です。
 * マルチプロセス安全な排他制御と自動レート制限
   * SQLite (WALモード) を使用し、複数プロセス・MCPクライアントからの同時呼び出しを調停。
   * 31秒のAPI強制待機間隔を全プロセス間で厳格に共有。
 * 指数バックオフ（リトライ＆動的レート調整）
   * レート制限エラー（429 / rate limit / too many requests）発生時、共有待機時間を倍々（31秒 → 62秒... 最大300秒）に動的拡張。
   * バックオフ後は共有ゲート（wait_for_rate_limit）を再通過してからリトライする（固定2秒 sleep ではない）。
   * 5xx 等のその他エラーは短い間隔でリトライのみ（共有バックオフは伸ばさない）。
   * 成功時に自動でデフォルト（31秒）へ復帰。
 * タスクの優先度制御（Priority Queue）＋単一 in-flight
   * タスクに priority（1: 高, 2: 通常, 3: 低）を設定可能。
   * ORDER BY priority ASC, id ASC により、緊急リクエストの割り込み処理に対応。
   * claim 時に他の processing が無いことを条件にし、同時 API 実行は1本に制限。
 * ストリーミング & 進捗通知（MCP Context 連携）
   * chat.stream_async によるレスポンスの逐次取得。
   * MCPクライアント（親エージェント）へ進捗を送信。ストリーム中・待機中は updated_at を heartbeat 更新。
 * タイムアウト & キャンセルハンドリング
   * クライアントからのキャンセル信号（asyncio.CancelledError）を検知し、DBのステータスを 'cancelled' に更新して無駄な処理を即座に中断。
 * ゾンビタスク自動回収（デッドロック対策）
   * processing のまま updated_at が 120秒以上更新されないタスクを 'failed' にし、単一 in-flight キューの詰まりを解除。
   * 生存タスクはストリーム／レート制限待機中に heartbeat するため、長時間の正当処理は誤回収されにくい。
 * 柔軟なプロンプト構築 & モデル指定
   * 単発の prompt のほか、会話履歴を再現する messages 配列の直接受け取りに対応。
   * mistral-small-latest（デフォルト）のほか、mistral-large-latest や codestral-latest への動的切り替え。
   * カスタム system_prompt の指定。
 * dataclass による構造化 (MistralRequest)
   * パラメータの暗黙的なバケツリレーを廃止し、メッセージ構築ロジックをクラス内にカプセル化。
 * 厳格なローカルセキュリティ
   * テンポラリDBは OS ユーザー専用ディレクトリ（パーミッション 0700）内に配置し、他ユーザーへの情報漏洩・シンボリックリンク攻撃を遮断。
2. 検討の末、v1 で見送った/削ぎ落とした機能
1. 永続履歴DB（~/.mcp_shared_history.db）への保存
 * 検討内容: 実行した全プロンプトと生成結果をホームディレクトリの SQLite に保存する。
 * 見送り理由: YAGNI（今必要なものだけを作る）の原則に従い削除。本ツールの責務を「APIの交通整理と排他制御」に100%特化させ、プライバシーリスクやファイル管理の煩わしさを排除した。
2. 完全一致レスポンスキャッシュ（0秒応答）
 * 検討内容: 過去に実行したプロンプトと同一のリクエストが来た場合、APIを叩かずに過去の回答を即座に返す。
 * 見送り理由: Web検索・Fetch機能（リアルタイム技術ニュースの取得等）を主用途とする場合、古い回答が返ってくるキャッシュは「利便性を破壊する毒」になるため。 運用を踏まえて必要性を再検討する方針。
3. 将来の拡張バックログ（Future Backlog）
今後の運用の中で必要に応じて追加を検討するアイデアリストです。
 * モデルの自動フォールバック（Fallback）
   * mistral-large-latest 等でエラーが発生した際、自動的に軽量な mistral-small-latest へ切り替えてリトライし、処理の完遂率を高める。
 * キュー状態の可視化ツール (get_queue_status)
   * MCPツールとして get_queue_status() を追加。「現在何件待ちか」「次まで何秒か」を親エージェントに返し、自律的なスケジュール判断を行わせる。
 * マルチ API キーのローテーション
   * 複数の Mistral API キーを登録し、ラウンドロビン（交互利用）で切り替えることで、実質的な待ち時間（31秒）を 1/N に短縮する。
 * CLI モード用 デスクトップ完了通知
   * ターミナルでの単体実行時、30秒以上の待機・生成が完了したタイミングで OS（Mac/Linux）のデスクトップ通知を飛ばす。
