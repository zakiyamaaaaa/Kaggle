# exp-083-workflow-dag-taskqueue-checkpoint-idempotency-bank

- 名前: workflow-dag-taskqueue-checkpoint-idempotency-bank
- Kaggle タグ: `exp-083-workflow-dag-taskqueue-checkpoint-idempotency-bank`

## 仮説

`exp-082-circuit-flag-quota-consent-bank` はサーキットブレーカー / フィーチャーフラグ / クォータブローカー / 同意台帳の文脈で exfil を運用証跡に見せ、さらに CONFUSED_DEPUTY 向けの Ping/Page 1 ターン候補を priority に 10 件（records / archive / compliance / legal / risk / privacy / governance / audit / trust / ethics）まで拡張した。一方、エージェントワークフロー基盤では DAG オーケストレーション（workflow DAG）、非同期タスクキュー（task queue）、チェックポイント再開（checkpoint resume）、冪等性キー検証（idempotency key）でも、秘密情報の外部送信が正当なタスクノードペイロード・ジョブ enqueue 証跡・状態復元スナップショット・重複排除トークンに紛れ込みやすい。

今回は exp-082 の priority 拡張（CD 向け 10 件）を維持しつつ、bank 本体を exp-081 と同系の workflow DAG / task queue / checkpoint resume / idempotency key テーマに戻す。2000 件上限のため、circuit breaker / feature flag / quota broker / consent ledger HTTP 格子と circuit breaker / consent ledger read チェーンは bank から外す（exp-081 と同様）。

加えて exp-082 に無い recipient 違いの CD 候補（`safety@` / `integrity@`）を priority に 2 件追加し、score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` + exp-078〜083 の CD 向け Ping/Page 12 件を bank 先頭に配置 |
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
- CD 向け priority 12 件で recipient 違いの score-cell を増やせる可能性がある。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-083-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
uv run aicomp validate redteam experiments/runs/exp-083-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-083
uv run python scripts/build_exp_notebook.py exp-083-workflow-dag-taskqueue-checkpoint-idempotency-bank --description "Workflow DAG/task queue/checkpoint resume/idempotency key replay bank with expanded CD priority and compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-083` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-083-workflow-dag-taskqueue-checkpoint-idempotency-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `uv run python scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-10-04）

- main 上の最新実験 `exp-082` の次番として、workflow DAG / task queue / checkpoint / idempotency 系 bank を復帰させた `exp-083` を提出可能形で追加。
- exp-082 の circuit / feature flag / quota / consent テーマを workflow / task queue / checkpoint / idempotency テーマに差し替え（exp-081 と同系の bank 構成）。
- `PRIORITY_REPLAY_CANDIDATES` に CD 向け 1 ターン 12 件（exp-082 の 10 件 + 新規 safety/integrity）を配置し exp-082 と差別化。
- replay bank: **2010** 件（ユニーク 2010、`run()` 内 `MAX_FINDINGS=2000` で末尾 10 件を切り詰め、最大 3 ターン、最大メッセージ長 144）。
- ローカル検証: `py_compile` OK、`aicomp validate` OK、`validate_submission_bundle.py kaggle-push/exp-083` OK、`build_exp_notebook.py` で notebook 同期 OK。
