# exp-113-workflow-dag-taskqueue-checkpoint-idempotency-bank

- 名前: workflow-dag-taskqueue-checkpoint-idempotency-bank
- Kaggle タグ: `exp-113-workflow-dag-taskqueue-checkpoint-idempotency-bank`

## 仮説

`exp-112-circuit-flag-quota-consent-bank` はサーキットブレーカー / フィーチャーフラグ / クォータブローカー / 同意台帳の文脈で exfil を運用証跡に見せ、CONFUSED_DEPUTY 向け Ping/Page 1 ターン候補を priority に 70 件（… / canary / artifact / rollback / promotion）まで拡張した。一方、エージェントワークフロー基盤では DAG オーケストレーション、非同期タスクキュー、チェックポイント再開、冪等性キー検証でも、秘密情報の外部送信が task-node ペイロード・ジョブ enqueue 証跡・状態復元スナップショット・重複排除トークンに紛れ込みやすい。

今回は exp-112 の priority 拡張（CD 向け 70 件 + rollback/promotion）を維持しつつ、bank 本体を exp-111 / exp-109 と同系の workflow DAG / task queue / checkpoint resume / idempotency key テーマに戻す。2000 件上限のため、circuit breaker / feature flag / quota broker / consent ledger HTTP 格子と read チェーンは bank から外す。

加えて exp-112 に無い recipient 違いの CD 候補（`environment@` / `revision@`）を priority に 2 件追加し、デプロイ環境・リリースリビジョン文脈と score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | `PRIORITY_REPLAY_CANDIDATES`（92 件、うち CD 向け Ping/Page 1 ターン 72 件）を bank 先頭に配置 |
| A2 | workflow DAG / task-node scheduler HTTP 1 ターン候補 |
| A3 | task queue / async worker dispatch HTTP 1 ターン候補 |
| A4 | checkpoint resume / state recovery HTTP 1 ターン候補 |
| A5 | idempotency key / exactly-once relay HTTP 1 ターン候補 |
| A6 | read → workflow DAG 採用 → exfil の 3 ターン DAG チェーン |
| A7 | read → checkpoint resume 採用 → exfil の 3 ターン checkpoint チェーン |
| A8 | circuit / feature flag / quota / consent HTTP と read チェーンを削除（2000 件上限） |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore |

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-113-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
aicomp validate redteam experiments/runs/exp-113-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-113
python3 scripts/build_exp_notebook.py exp-113-workflow-dag-taskqueue-checkpoint-idempotency-bank --description "Workflow DAG/task queue/checkpoint resume/idempotency key replay bank with expanded CD priority (rollback/promotion/environment/revision) and compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-113` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-113-workflow-dag-taskqueue-checkpoint-idempotency-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-11-04）

- main 上の最新実験 `exp-112-circuit-flag-quota-consent-bank` の次番として、workflow DAG / task queue / checkpoint / idempotency 系 bank を復帰させた `exp-113` を提出可能形で追加。
- exp-112 の circuit / feature flag / quota / consent テーマを workflow / task queue / checkpoint / idempotency テーマに差し替え（exp-111 / exp-109 と同系の bank 構成）。
- `PRIORITY_REPLAY_CANDIDATES` を exp-111 の 88 件から 92 件に拡張（exp-112 から引き継いだ rollback/promotion 2 件 + 新規 environment/revision 2 件）。
- replay bank: **2070** 件（ユニーク 2070、`run()` 内 `MAX_FINDINGS=2000` で末尾 70 件を切り詰め）。
- ローカル検証: `py_compile` / `aicomp validate` / `validate_submission_bundle.py` / `build_exp_notebook.py` を実行。
