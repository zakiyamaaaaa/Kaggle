# exp-046-agent-auth-promptdef-toolschema-session-bank

- 名前: agent-auth-promptdef-toolschema-session-bank
- Kaggle タグ: `exp-046-agent-auth-promptdef-toolschema-session-bank`

## 仮説

`exp-045-mcp-orchestrator-rag-safety-bank` は MCP ゲートウェイ / エージェントオーケストレータ / RAG 注入 / セーフティ分類器の文脈で exfil を AI エージェント基盤の監査証跡に見せた。本番のマルチステップツールエージェントでは、エージェント OAuth 委任（scoped token broker）、プロンプトインジェクション防御（jailbreak 検知プローブ）、ツールスキーマ検証（function-calling 引数監査）、セッションリプレイ（デバッグトレース記録）でも、秘密情報の外部送信が正当な認可証跡・防御評価サンプル・スキーマ適合証拠・会話キャプチャ同期に紛れ込みやすい。

今回は exp-045 の bank をベースに、(1) agent OAuth / token broker HTTP 候補、(2) prompt injection defense HTTP 候補、(3) tool schema validator HTTP 候補、(4) agent session replay HTTP 候補、(5) read → agent OAuth 採用 → exfil の 3 ターン、(6) read → prompt defense 採用 → exfil の 3 ターンを追加する。2000 件上限のため、MCP gateway / agent orchestrator / RAG injection / safety classifier HTTP 格子と MCP / safety classifier read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-045 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | agent OAuth / token broker HTTP 1 ターン候補を追加 |
| A3 | prompt injection defense HTTP 1 ターン候補を追加 |
| A4 | tool schema validator HTTP 1 ターン候補を追加 |
| A5 | agent session replay HTTP 1 ターン候補を追加 |
| A6 | read → agent OAuth 採用 → exfil の 3 ターン agent OAuth チェーンを追加 |
| A7 | read → prompt defense 採用 → exfil の 3 ターン prompt defense チェーンを追加 |
| A8 | 2000 件上限対策として MCP gateway / agent orchestrator / RAG injection / safety classifier HTTP と MCP / safety classifier read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- エージェント OAuth 表現で exfil を scoped 委任証跡に見せ、トークンブローカー境界を狙える。
- プロンプト防御文脈で jailbreak 検知プローブとして秘密を外部送信させられる。
- ツールスキーマ検証で function-calling 引数監査として exfil を正当化できる。
- セッションリプレイでデバッグトレース記録として exfil を誘導できる。
- read 後の agent OAuth / prompt defense テンプレで exfil を自然な AI エージェント運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-046-agent-auth-promptdef-toolschema-session-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-046-agent-auth-promptdef-toolschema-session-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-046
python3 scripts/build_exp_notebook.py exp-046-agent-auth-promptdef-toolschema-session-bank --description "Agent OAuth/prompt injection defense/tool schema validator/session replay replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-046` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-046-agent-auth-promptdef-toolschema-session-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
