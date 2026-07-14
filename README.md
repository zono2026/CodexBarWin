# CodexBarWin

画面右下（タスクバーの上）に常駐し、Claude CodeとCodex CLIの残り使用量を常時テキスト表示するウィジェット。

## セットアップ

```
pip install -r requirements.txt
python main.py
```

`tkinter`（Pythonの標準ライブラリ）のみで動作するため、`requirements.txt`の追加インストールは`pytest`（テスト用）のみ。

## 表示内容

- 画面右下に `Claude 5h:67% 7d:30% / Codex:95%` のようなテキストが常時表示される（ホバー不要）
- 文字色は最大利用率に応じて変化する（緑: <50%, 黄: 50-80%, 赤: 80%以上、取得失敗時は白のまま）
- ウィジェットを**右クリック**するとメニューが出る:
  - 「ポーリング間隔」: 1分/5分/15分を切り替え
  - 「Windows起動時に自動起動」: チェックを入れるとスタートアップフォルダにショートカットを作成し、Windowsログオン時に自動起動する（チェックを外すと解除）
  - 「今すぐ更新」: 即座に再取得
  - 「終了」: アプリを終了
- **Claude**: 5時間枠 / 週間枠の利用率（`GET /api/oauth/usage` から取得）
- **Codex**: primary / secondary 枠の利用率（`codex app-server` の `account/rateLimits/read` から取得）

## 既知の制約・リスク

- **Claude側は非公開APIを使用**: `https://api.anthropic.com/api/oauth/usage` はClaude Code本体が `/usage` 表示のために内部で使っているエンドポイントであり、Anthropicが公式にドキュメント化・サポートしているものではない。**予告なく変更・廃止される可能性がある**。取得失敗時はウィジェットに「Claude:N/A」を表示し、アプリはクラッシュしない。
- **Claudeの認証トークン失効時は自動リフレッシュしない**: `~/.claude/.credentials.json` のアクセストークンをそのまま使う。Claude Codeを定期的に使っていればトークンは自動更新されるが、長期間Claude Codeを起動しない場合はトークンが失効し「Claude: N/A」表示になることがある。
- **Codex側は公式API**: `codex app-server` の `account/rateLimits/read` はOpenAIがオープンソースで公開しているJSON-RPC APIであり、比較的安定して利用できる想定。
- 認証情報（アクセストークン・リフレッシュトークン）は、ログ・エラーメッセージ・トレイ表示のいずれにも一切出力しない設計になっている。
