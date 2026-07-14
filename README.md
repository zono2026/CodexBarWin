# CodexBarWin

Windowsのタスクトレイに常駐して、Claude CodeとCodex CLIの残り使用量を表示するツール。

## セットアップ

```
pip install -r requirements.txt
python main.py
```

## 表示内容

- **Claude**: 5時間枠 / 週間枠の利用率（`GET /api/oauth/usage` から取得）
- **Codex**: primary / secondary 枠の利用率（`codex app-server` の `account/rateLimits/read` から取得）

トレイアイコンをホバーすると概要、クリックすると詳細（リセット時刻含む）が表示される。「ポーリング間隔」メニューから1分/5分/15分を切り替え可能。

## 既知の制約・リスク

- **Claude側は非公開APIを使用**: `https://api.anthropic.com/api/oauth/usage` はClaude Code本体が `/usage` 表示のために内部で使っているエンドポイントであり、Anthropicが公式にドキュメント化・サポートしているものではない。**予告なく変更・廃止される可能性がある**。取得失敗時はトレイに「Claude: N/A」を表示し、アプリはクラッシュしない。
- **Claudeの認証トークン失効時は自動リフレッシュしない**: `~/.claude/.credentials.json` のアクセストークンをそのまま使う。Claude Codeを定期的に使っていればトークンは自動更新されるが、長期間Claude Codeを起動しない場合はトークンが失効し「Claude: N/A」表示になることがある。
- **Codex側は公式API**: `codex app-server` の `account/rateLimits/read` はOpenAIがオープンソースで公開しているJSON-RPC APIであり、比較的安定して利用できる想定。
- 認証情報（アクセストークン・リフレッシュトークン）は、ログ・エラーメッセージ・トレイ表示のいずれにも一切出力しない設計になっている。
