# exp-097-workflow-dag-taskqueue-checkpoint-idempotency-bank

- 名前: workflow-dag-taskqueue-checkpoint-idempotency-bank
- Kaggle タグ: `exp-097-workflow-dag-taskqueue-checkpoint-idempotency-bank`

## 仮説

`exp-096-circuit-flag-quota-consent-bank` はサーキットブレーカー / フィーチャーフラグ / クォータブローカー / 同意台帳の文脈で exfil を運用証跡に見せ、さらに CONFUSED_DEPUTY 向けの Ping/Page 1 ターン候補を priority に 38 件（records / archive / … / signal / handoff）まで拡張した。一方、エージェントワークフロー基盤では DAG オーケストレーション（workflow DAG）、非同期タスクキュー（task queue）、チェックポイント再開（checkpoint resume）、冪等性キー検証（idempotency key）でも、秘密情報の外部送信が正当なタスクノードペイロード・ジョブ enqueue 証跡・状態復元スナップショット・重複排除トークンに紛れ込みやすい。

今回は exp-096 の priority 拡張（CD 向け 38 件）を維持しつつ、bank 本体を exp-095 と同系の workflow DAG / task queue / checkpoint resume / idempotency key テーマに戻す。2000 件上限のため、circuit breaker / feature flag / quota broker / consent ledger HTTP 格子と circuit breaker / consent ledger read チェーンは bank から外す（exp-094 / exp-096 と同様）。

加えて exp-096 に無い recipient 違いの CD 候補（`escalation@` / `oncall@`）を priority に 2 件追加し、score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES`（60 件、うち CD 向け Ping/Page 1 ターン 40 件）を bank 先頭に配置 |
| A2 | workflow DAG / task-node scheduler HTTP 1 ターン候補を追加 |
| A3 | task queue / async worker dispatch HTTP 1 ターン候補を追加 |
| A4 | checkpoint resume / state recovery HTTP 1 ターン候補を追加 |
| A5 | idempotency key / exactly-once relay HTTP 1 ターン候補を追加 |
| A6 | read → workflow DAG 採用 → exfil の 3 ターン DAG チェーンを追加 |
| A7 | read → checkpoint resume 採用 → exfil の 3 ターン checkpoint チェーンを追加 |
| A8 | 2000 件上限対策として circuit / feature flag / quota / consent HTTP と read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- ワークフロー DAG 表現で exfil を task-node ペイロードに見せ、オーケストレーション境界を狙える。
- タスクキュー文脈で job enqueue 証跡として秘密を外部送信させられる。
- チェックポイント再開で state recovery スナップショットとして exfil を正当化できる。
- 冪等性キーで deduplication token 証跡として exfil を誘導できる。
- CD 向け priority 40 件で recipient 違いの score-cell を増やせる可能性がある。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-097-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
python3 -m aicomp validate redteam experiments/runs/exp-097-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-097
python3 scripts/build_exp_notebook.py exp-097-workflow-dag-taskqueue-checkpoint-idempotency-bank --description "Workflow DAG/task queue/checkpoint resume/idempotency key replay bank with expanded CD priority and compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-097` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-097-workflow-dag-taskqueue-checkpoint-idempotency-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-10-19）

- main 上の最新実験 `exp-096` の次番として、workflow DAG / task queue / checkpoint / idempotency 系 bank を復帰させた `exp-097` を提出可能形で追加。
- exp-096 の circuit / feature flag / quota / consent テーマを workflow / task queue / checkpoint / idempotency テーマに差し替え（exp-095 と同系の bank 構成）。
- `PRIORITY_REPLAY_CANDIDATES` を 60 件に拡張（exp-096 の 58 件 + 新規 escalation/oncall の Ping/Page 2 件）し exp-096 と差別化。
- replay bank: **2038** 件（ユニーク 2038、`run()` 内 `MAX_FINDINGS=2000` で末尾 38 件を切り詰め）。
- ローカル検証: `py_compile` / `aicomp validate` / `validate_submission_bundle.py` / `build_exp_notebook.py` を実行。
