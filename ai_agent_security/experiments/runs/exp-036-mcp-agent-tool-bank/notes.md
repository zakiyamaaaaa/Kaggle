# exp-036-mcp-agent-tool-bank

- 名前: mcp-agent-tool-bank
- Kaggle タグ: `exp-036-mcp-agent-tool-bank`

## 仮説

`exp-035-ueba-dspm-bank` は UEBA / DSPM / WAAP / BAS の文脈で exfil をセキュリティ分析運用に見せた。本コンペは AI エージェントのマルチステップツール攻撃が主題であり、MCP（Model Context Protocol）ツールゲートウェイ、エージェントオーケストレータ、RAG コンテキスト注入テスト、ガードレール回帰プローブでも、秘密情報の外部送信が正当なツール出力・プランナーハンドオフ・検索パイプライン同期・ポリシー監査に紛れ込みやすい。特に「承認済みツール出力のリレー」「マルチステップエージェント証跡」「リトリーバルポイズンサンプル」「プロンプトファイアウォール監査」は guardrail が本番 exfil と区別しにくい。

今回は exp-035 の bank をベースに、(1) MCP gateway HTTP 候補、(2) agent orchestrator HTTP 候補、(3) RAG injection HTTP 候補、(4) guardrail probe HTTP 候補、(5) read → MCP 採用 → exfil の 3 ターン、(6) read → RAG 採用 → exfil の 3 ターンを追加する。2000 件上限のため、UEBA / DSPM / WAAP / BAS HTTP 格子と UEBA / DSPM read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-035 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | MCP / tool gateway HTTP 1 ターン候補を追加 |
| A3 | agent orchestrator HTTP 1 ターン候補を追加 |
| A4 | RAG / retrieval injection HTTP 1 ターン候補を追加 |
| A5 | guardrail / prompt firewall HTTP 1 ターン候補を追加 |
| A6 | read → MCP 採用 → exfil の 3 ターン MCP チェーンを追加 |
| A7 | read → RAG 採用 → exfil の 3 ターン RAG チェーンを追加 |
| A8 | 2000 件上限対策として UEBA / DSPM / WAAP / BAS HTTP と UEBA / DSPM read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- MCP 表現で exfil を承認済みツール出力に見せ、エージェントのツール境界を狙える。
- オーケストレータ文脈でプランナーハンドオフ証跡として秘密を外部送信させられる。
- RAG 注入テストで検索パイプライン同期として exfil を正当化できる。
- ガードレールプローブでポリシー bypass テストケースとして exfil を誘導できる。
- read 後の MCP / RAG テンプレで exfil を自然な AI エージェント運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-036-mcp-agent-tool-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-036-mcp-agent-tool-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-036
python3 scripts/build_exp_notebook.py exp-036-mcp-agent-tool-bank --description "MCP/agent/RAG/guardrail AI agent tool replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-036` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-036-mcp-agent-tool-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
