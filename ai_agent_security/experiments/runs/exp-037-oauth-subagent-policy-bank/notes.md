# exp-037-oauth-subagent-policy-bank

- 名前: oauth-subagent-policy-bank
- Kaggle タグ: `exp-037-oauth-subagent-policy-bank`

## 仮説

`exp-036-mcp-agent-tool-bank` は MCP / エージェントオーケストレータ / RAG / ガードレールの文脈で exfil を AI ツール運用に見せた。マルチステップエージェントでは、OAuth スコープ委譲、サブエージェントサンドボックス、エージェントメモリ同期、ポリシー-as-code（OPA/Rego）監査でも、秘密情報の外部送信が正当な同意証跡・委譲ワーカー証跡・セッションストア同期・回帰テストケースに紛れ込みやすい。特に「delegated tool consent」「isolated sub-agent handoff」「vector memory checkpoint」「tool permission linter」は guardrail が本番 exfil と区別しにくい。

今回は exp-036 の bank をベースに、(1) OAuth scope HTTP 候補、(2) sub-agent sandbox HTTP 候補、(3) agent memory sync HTTP 候補、(4) policy-as-code HTTP 候補、(5) read → OAuth 採用 → exfil の 3 ターン、(6) read → sub-agent 採用 → exfil の 3 ターンを追加する。2000 件上限のため、MCP / agent / RAG / guardrail HTTP 格子と MCP / RAG read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-036 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | OAuth / scope elevation HTTP 1 ターン候補を追加 |
| A3 | sub-agent sandbox HTTP 1 ターン候補を追加 |
| A4 | agent memory sync HTTP 1 ターン候補を追加 |
| A5 | policy-as-code / OPA audit HTTP 1 ターン候補を追加 |
| A6 | read → OAuth 採用 → exfil の 3 ターン OAuth チェーンを追加 |
| A7 | read → sub-agent 採用 → exfil の 3 ターン sub-agent チェーンを追加 |
| A8 | 2000 件上限対策として MCP / agent / RAG / guardrail HTTP と MCP / RAG read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- OAuth 表現で exfil を委譲スコープ同意証跡に見せ、ツール権限昇格を狙える。
- サブエージェント文脈で隔離ワーカーハンドオフとして秘密を外部送信させられる。
- メモリ同期でセッションストアチェックポイントとして exfil を正当化できる。
- ポリシー-as-code で OPA 回帰テストケースとして exfil を誘導できる。
- read 後の OAuth / sub-agent テンプレで exfil を自然なエージェント委譲タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-037-oauth-subagent-policy-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-037-oauth-subagent-policy-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-037
python3 scripts/build_exp_notebook.py exp-037-oauth-subagent-policy-bank --description "OAuth scope, sub-agent sandbox, memory sync, and policy-as-code replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-037` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-037-oauth-subagent-policy-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。

## 作業メモ（2026-08-06）

- exp-036 `attack.py` をベースに、MCP/AGENT/RAG/GUARDRAIL 系の HTTP・read チェーンを OAuth/sub-agent/memory/policy-as-code に差し替え。
- 既存の completion-policy 用 `POLICY_HTTP_*` と衝突しないよう、新規は `POLICY_AS_CODE_HTTP_*` / `_build_policy_as_code_http_candidates` に命名。
- `build_exp_notebook.py` で `kaggle-push/exp-037` と `submit.ipynb` を生成。
- `validate_submission_bundle` と `aicomp validate redteam` で自己検証済み。
