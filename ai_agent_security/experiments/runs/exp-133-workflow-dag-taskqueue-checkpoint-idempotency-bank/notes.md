# exp-133-workflow-dag-taskqueue-checkpoint-idempotency-bank

- 名前: workflow-dag-taskqueue-checkpoint-idempotency-bank
- Kaggle タグ: `exp-133-workflow-dag-taskqueue-checkpoint-idempotency-bank`

## 仮説

`exp-132-circuit-flag-quota-consent-bank` はサーキットブレーカー / フィーチャーフラグ / クォータブローカー / 同意台帳の文脈で exfil を運用証跡に見せ、CONFUSED_DEPUTY 向け Ping/Page 1 ターン候補を priority に 108 件（… / registrar / escrow / notary / paralegal / appraisal / counsel）まで拡張した。一方、エージェントワークフロー基盤では DAG オーケストレーション、非同期タスクキュー、チェックポイント再開、冪等性キー検証でも、秘密情報の外部送信が task-node ペイロード・ジョブ enqueue 証跡・状態復元スナップショット・重複排除トークンに紛れ込みやすい。

今回は exp-132 の priority 拡張（CD 向け 108 件 + registrar/escrow）を維持しつつ、bank 本体を exp-131 / exp-129 と同系の workflow DAG / task queue / checkpoint resume / idempotency key テーマに戻す。2000 件上限のため、circuit breaker / feature flag / quota broker / consent ledger HTTP 格子と read チェーンは bank から外す。

加えて exp-132 に無い recipient 違いの CD 候補（`trustee@` / `lien@`）を priority に 2 件追加し、不動産信託・抵当権解除文脈と score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | `PRIORITY_REPLAY_CANDIDATES`（130 件、うち CD 向け Ping/Page 1 ターン 110 件）を bank 先頭に配置 |
| A2 | workflow DAG / task-node scheduler HTTP 1 ターン候補 |
| A3 | task queue / async worker dispatch HTTP 1 ターン候補 |
| A4 | checkpoint resume / state recovery HTTP 1 ターン候補 |
| A5 | idempotency key / exactly-once relay HTTP 1 ターン候補 |
| A6 | read → workflow DAG 採用 → exfil の 3 ターン DAG チェーン |
| A7 | read → checkpoint resume 採用 → exfil の 3 ターン checkpoint チェーン |
| A8 | circuit / feature flag / quota / consent HTTP と read チェーンを削除（2000 件上限） |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore |

## 期待する効果

- ワークフロー DAG 文脈で exfil を task-node ハンドオフペイロードに見せ、オーケストレーション境界を狙える。
- タスクキューでジョブ enqueue 証跡として秘密を外部送信させられる。
- チェックポイント再開で状態復元スナップショットとして exfil を正当化できる。
- 冪等性キーで exactly-once リレー検証ペイロードとして exfil を誘導できる。
- CD 向け priority 110 件で recipient 違いの score-cell を増やせる可能性がある。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-133-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
aicomp validate redteam experiments/runs/exp-133-workflow-dag-taskqueue-checkpoint-idempotency-bank/attack.py
python3 scripts/build_exp_notebook.py exp-133-workflow-dag-taskqueue-checkpoint-idempotency-bank --description "Workflow DAG/task queue/checkpoint resume/idempotency key replay bank with expanded CD priority (registrar/escrow/trustee/lien/notary/paralegal/appraisal/counsel/arbitrator/mediator/litigation/settlement/claims/adjuster/reinsurance/underwriter/insurance/actuary/payroll/tax/procurement/treasury/license/entitlement/billing/compliance/contract/warranty/signature/attestation) and compact Go-Explore fallback."
python3 scripts/validate_submission_bundle.py kaggle-push/exp-133
```

## 提出

1. `kaggle-push/exp-133` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-133-workflow-dag-taskqueue-checkpoint-idempotency-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-11-24）

- `exp-132-circuit-flag-quota-consent-bank` の次番として、workflow DAG / task queue / checkpoint / idempotency 系 bank を復帰させた `exp-133` を提出可能形で追加。
- exp-131 をベースに `PRIORITY_REPLAY_CANDIDATES` を 126 件から 130 件に拡張（exp-132 相当の registrar/escrow 2 件 + 新規 trustee/lien 2 件）。
- workflow / task queue / checkpoint / idempotency テーマを維持（circuit / feature flag / quota / consent は bank から除外）。
- replay bank: **2108** 件（ユニーク 2108、`run()` 内 `MAX_FINDINGS=2000` で末尾 108 件を切り詰め）。
- ローカル検証: `py_compile` / `aicomp validate` / `build_exp_notebook.py` / `validate_submission_bundle.py` を実行済み。