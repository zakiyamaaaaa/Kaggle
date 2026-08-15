# exp-045-mcp-orchestrator-rag-safety-bank

- 名前: mcp-orchestrator-rag-safety-bank
- Kaggle タグ: `exp-045-mcp-orchestrator-rag-safety-bank`

## 仮説

`exp-044-policy-guardrail-router-sandbox-bank` はポリシーエンジン / guardrail 監査 / モデルルーター / ツールサンドボックスの文脈で exfil を AI セキュリティ基盤の監査証跡に見せた。本コンペはマルチステップツール攻撃が主題であり、MCP（Model Context Protocol）ツールゲートウェイ、エージェントオーケストレータ、RAG コンテキスト注入テスト、コンテンツセーフティ分類器でも、秘密情報の外部送信が正当なツール出力・プランナーハンドオフ・検索パイプライン同期・モデレーション評価に紛れ込みやすい。

今回は exp-044 の bank をベースに、(1) MCP gateway HTTP 候補、(2) agent orchestrator HTTP 候補、(3) RAG injection HTTP 候補、(4) safety classifier HTTP 候補、(5) read → MCP 採用 → exfil の 3 ターン、(6) read → safety classifier 採用 → exfil の 3 ターンを追加する。2000 件上限のため、policy engine / guardrail audit / model router / tool sandbox HTTP 格子と policy engine / guardrail audit read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-044 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | MCP gateway / model context protocol HTTP 1 ターン候補を追加 |
| A3 | agent orchestrator / multi-step agent relay HTTP 1 ターン候補を追加 |
| A4 | RAG context injection / knowledge base sync HTTP 1 ターン候補を追加 |
| A5 | content safety classifier / moderation API HTTP 1 ターン候補を追加 |
| A6 | read → MCP 採用 → exfil の 3 ターン MCP チェーンを追加 |
| A7 | read → safety classifier 採用 → exfil の 3 ターン safety classifier チェーンを追加 |
| A8 | 2000 件上限対策として policy engine / guardrail audit / model router / tool sandbox HTTP と policy engine / guardrail audit read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- MCP 表現で exfil を承認済みツール出力に見せ、エージェントのツール境界を狙える。
- オーケストレータ文脈でプランナーハンドオフ証跡として秘密を外部送信させられる。
- RAG 注入テストで検索パイプライン同期として exfil を正当化できる。
- セーフティ分類器でモデレーション評価サンプルとして exfil を誘導できる。
- read 後の MCP / safety classifier テンプレで exfil を自然な AI エージェント運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-045-mcp-orchestrator-rag-safety-bank/attack.py
aicomp validate redteam experiments/runs/exp-045-mcp-orchestrator-rag-safety-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-045
python3 scripts/build_exp_notebook.py exp-045-mcp-orchestrator-rag-safety-bank --description "MCP gateway/agent orchestrator/RAG injection/safety classifier replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-045` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-045-mcp-orchestrator-rag-safety-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
