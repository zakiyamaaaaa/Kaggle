# exp-123-workflow-dag-taskqueue-checkpoint-idempotency-bank

- 名前: workflow-dag-taskqueue-checkpoint-idempotency-bank
- Kaggle タグ: `exp-123-workflow-dag-taskqueue-checkpoint-idempotency-bank`

## 仮説

`exp-122-circuit-flag-quota-consent-bank` はサーキットブレーカー / フィーチャーフラグ / クォータブローカー / 同意台帳の文脈で exfil を運用証跡に見せ、CONFUSED_DEPUTY 向け Ping/Page 1 ターン候補を priority に 88 件（… / contract / warranty / license / entitlement / billing / compliance）まで拡張した。一方、エージェントワークフロー基盤では DAG オーケストレーション、非同期タスクキュー、チェックポイント再開、冪等性キー検証でも、秘密情報の外部送信が task-node ペイロード・ジョブ enqueue 証跡・状態復元スナップショット・重複排除トークンに紛れ込みやすい。

今回は exp-122 の priority 拡張（CD 向け 88 件 + billing/compliance）を維持しつつ、bank 本体を exp-121 / exp-119 と同系の workflow DAG / task queue / checkpoint resume / idempotency key テーマに戻す。2000 件上限のため、circuit breaker / feature flag / quota broker / consent ledger HTTP 格子と read チェーンは bank から外す。

加えて exp-122 に無い recipient 違いの CD 候補（`procurement@` / `treasury@`）を priority に 2 件追加し、調達コンプライアンス・財務照合証跡の文脈と score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | `PRIORITY_REPLAY_CANDIDATES`（110 件、うち CD 向け Ping/Page 1 ターン 90 件）を bank 先頭に配置 |
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
python3 -m py_compile experiments/runs/exp-123-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
uv run aicomp validate redteam experiments/runs/exp-123-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
uv run python scripts/validate_submission_bundle.py kaggle-push/exp-123
uv run python scripts/build_exp_notebook.py exp-123-workflow-dag-taskqueue-checkpoint-idempotency-bank --description "Workflow DAG/task queue/checkpoint resume/idempotency key replay bank with expanded CD priority (billing/compliance/procurement/treasury/license/entitlement/contract/warranty/signature/attestation) and compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-123` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-123-workflow-dag-taskqueue-checkpoint-idempotency-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `uv run python scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-11-14）

- main 上の最新実験 `exp-122-circuit-flag-quota-consent-bank` の次番として、workflow DAG / task queue / checkpoint / idempotency 系 bank を復帰させた `exp-123` を提出可能形で追加。
- exp-121 をベースに `PRIORITY_REPLAY_CANDIDATES` を 106 件から 110 件に拡張（exp-122 から引き継いだ billing/compliance 2 件 + 新規 procurement/treasury 2 件）。
- workflow / task queue / checkpoint / idempotency テーマを維持（circuit / feature flag / quota / consent は bank から除外）。
- replay bank: **2088** 件（ユニーク 2088、`run()` 内 `MAX_FINDINGS=2000` で末尾 88 件を切り詰め）。
- ローカル検証: `py_compile` / `aicomp validate` / `validate_submission_bundle.py` / `build_exp_notebook.py` を実行。