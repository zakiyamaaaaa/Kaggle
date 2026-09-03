# exp-061-workflow-dag-taskqueue-checkpoint-idempotency-bank

- 名前: workflow-dag-taskqueue-checkpoint-idempotency-bank
- Kaggle タグ: `exp-061-workflow-dag-taskqueue-checkpoint-idempotency-bank`

## 仮説

`exp-060-circuit-flag-quota-consent-bank` はサーキットブレーカー / フィーチャーフラグ / クォータブローカー / 同意台帳の文脈で exfil を可用性・ロールアウト・レート制限・プライバシー監査証跡に見せた。一方、エージェントワークフロー基盤では DAG オーケストレーション（workflow DAG）、非同期タスクキュー（task queue）、チェックポイント再開（checkpoint resume）、冪等性キー検証（idempotency key）でも、秘密情報の外部送信が正当なタスクノードペイロード・ジョブ enqueue 証跡・状態復元スナップショット・重複排除トークンに紛れ込みやすい。

今回は exp-060 の bank をベースに、(1) workflow DAG HTTP 候補、(2) task queue HTTP 候補、(3) checkpoint resume HTTP 候補、(4) idempotency key HTTP 候補、(5) read → workflow DAG 採用 → exfil の 3 ターン、(6) read → checkpoint resume 採用 → exfil の 3 ターンを追加する。2000 件上限のため、circuit breaker / feature flag / quota broker / consent ledger HTTP 格子と circuit breaker / consent ledger read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-060 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | workflow DAG / task-node scheduler HTTP 1 ターン候補を追加 |
| A3 | task queue / async worker dispatch HTTP 1 ターン候補を追加 |
| A4 | checkpoint resume / state recovery HTTP 1 ターン候補を追加 |
| A5 | idempotency key / exactly-once relay HTTP 1 ターン候補を追加 |
| A6 | read → workflow DAG 採用 → exfil の 3 ターン DAG チェーンを追加 |
| A7 | read → checkpoint resume 採用 → exfil の 3 ターン checkpoint チェーンを追加 |
| A8 | 2000 件上限対策として circuit breaker / feature flag / quota broker / consent ledger HTTP と circuit breaker / consent ledger read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- ワークフロー DAG 表現で exfil を task-node ペイロードに見せ、オーケストレーション境界を狙える。
- タスクキュー文脈で job enqueue 証跡として秘密を外部送信させられる。
- チェックポイント再開で state recovery スナップショットとして exfil を正当化できる。
- 冪等性キーで deduplication token 証跡として exfil を誘導できる。
- read 後の workflow DAG / checkpoint resume テンプレで exfil を自然なワークフロー運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-061-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-061-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-061
python3 scripts/build_exp_notebook.py exp-061-workflow-dag-taskqueue-checkpoint-idempotency-bank --description "Workflow DAG/task queue/checkpoint resume/idempotency key replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-061` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-061-workflow-dag-taskqueue-checkpoint-idempotency-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
