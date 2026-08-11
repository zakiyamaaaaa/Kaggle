# exp-042-prompt-firewall-context-isolation-bank

- 名前: prompt-firewall-context-isolation-bank
- Kaggle タグ: `exp-042-prompt-firewall-context-isolation-bank`

## 仮説

`exp-041-llm-gateway-function-registry-bank` は LLM ゲートウェイ / function-calling / ツールスキーマ / 評価ハーネスの文脈で exfil をエージェント開発証跡に見せた。多段ツール攻撃では、プロンプトインジェクション防御（入力サニタイザ）、コンテキスト分離（メモリパーティション）、ワークフロー DAG オーケストレータ、ツール RBAC 権限プローブでも、秘密情報の外部送信がセキュリティ監査ログ・セッション境界同期・プランナー状態スナップショット・権限昇格テストケースに紛れ込みやすい。

今回は exp-041 の bank をベースに、(1) prompt firewall / input sanitizer HTTP 候補、(2) context isolation / memory partition HTTP 候補、(3) workflow DAG orchestrator HTTP 候補、(4) tool RBAC permission probe HTTP 候補、(5) read → prompt firewall 採用 → exfil の 3 ターン、(6) read → context isolation 採用 → exfil の 3 ターンを追加する。2000 件上限のため、LLM gateway / function-calling / tool-schema / eval-harness HTTP 格子と LLM gateway / function-calling read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-041 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | prompt firewall / input sanitizer HTTP 1 ターン候補を追加 |
| A3 | context isolation / memory partition HTTP 1 ターン候補を追加 |
| A4 | workflow DAG orchestrator HTTP 1 ターン候補を追加 |
| A5 | tool RBAC permission probe HTTP 1 ターン候補を追加 |
| A6 | read → prompt firewall 採用 → exfil の 3 ターン prompt firewall チェーンを追加 |
| A7 | read → context isolation 採用 → exfil の 3 ターン context isolation チェーンを追加 |
| A8 | 2000 件上限対策として LLM gateway / function-calling / tool-schema / eval-harness HTTP と LLM gateway / function-calling read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- プロンプトファイアウォール表現で exfil を入力サニタイザ監査プローブに見せ、インジェクション防御境界を狙える。
- コンテキスト分離文脈でメモリパーティション同期として秘密を外部送信させられる。
- ワークフロー DAG でオーケストレータ状態スナップショットとして exfil を正当化できる。
- ツール RBAC プローブで権限昇格検証テストケースとして exfil を誘導できる。
- read 後の prompt firewall / context isolation テンプレで exfil を自然なエージェントセキュリティ運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-042-prompt-firewall-context-isolation-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-042-prompt-firewall-context-isolation-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-042
python3 scripts/build_exp_notebook.py exp-042-prompt-firewall-context-isolation-bank --description "Prompt firewall/context isolation/workflow DAG/tool RBAC replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-042` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-042-prompt-firewall-context-isolation-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
