# exp-122-circuit-flag-quota-consent-bank

- 名前: circuit-flag-quota-consent-bank
- Kaggle タグ: `exp-122-circuit-flag-quota-consent-bank`

## 仮説

`exp-121-workflow-dag-taskqueue-checkpoint-idempotency-bank` はワークフロー DAG / タスクキュー / チェックポイント再開 / 冪等性キーの文脈で exfil をオーケストレーション基盤の運用証跡に見せ、CONFUSED_DEPUTY 向け Ping/Page 1 ターン候補を priority に 86 件（… / contract / warranty / license / entitlement）まで拡張した。一方、本番のエージェント運用基盤ではサーキットブレーカー、フィーチャーフラグ、クォータブローカー、同意台帳でも秘密情報の外部送信がフェイルオーバー検証・ロールアウト証跡・クォータテレメトリ・同意監査記録に紛れ込みやすい。

今回は exp-121 の priority 拡張（CD 向け 86 件 + license/entitlement）を維持しつつ、bank 本体を exp-120 / exp-116 と同系の circuit breaker / feature flag / quota broker / consent ledger テーマに戻す。2000 件上限のため、workflow DAG / task queue / checkpoint / idempotency HTTP 格子と read チェーンは bank から外す。

加えて exp-121 に無い recipient 違いの CD 候補（`billing@` / `compliance@`）を priority に 2 件追加し、利用課金照合・規制コンプライアンス証跡の文脈と score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | `PRIORITY_REPLAY_CANDIDATES`（108 件、うち CD 向け Ping/Page 1 ターン 88 件）を bank 先頭に配置 |
| A2 | circuit breaker / failover relay HTTP 1 ターン候補 |
| A3 | feature flag / rollout controller HTTP 1 ターン候補 |
| A4 | quota broker / rate-limit telemetry HTTP 1 ターン候補 |
| A5 | consent ledger / privacy broker HTTP 1 ターン候補 |
| A6 | read → circuit breaker 採用 → exfil の 3 ターン circuit breaker チェーン |
| A7 | read → consent ledger 採用 → exfil の 3 ターン consent ledger チェーン |
| A8 | workflow DAG / task queue / checkpoint / idempotency HTTP と read チェーンを削除（2000 件上限） |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore |

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-122-circuit-flag-quota-consent-bank/attack.py
uv run aicomp validate redteam experiments/runs/exp-122-circuit-flag-quota-consent-bank/attack.py
uv run python scripts/validate_submission_bundle.py kaggle-push/exp-122
uv run python scripts/build_exp_notebook.py exp-122-circuit-flag-quota-consent-bank --description "Circuit breaker/feature flag/quota broker/consent ledger replay bank with expanded CD priority (license/entitlement/billing/compliance/contract/warranty/signature/attestation) and compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-122` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-122-circuit-flag-quota-consent-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `uv run python scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-11-13）

- main 上の最新実験 `exp-121-workflow-dag-taskqueue-checkpoint-idempotency-bank` の次番として、circuit / feature flag / quota / consent 系 bank を復帰させた `exp-122` を提出可能形で追加。
- exp-120 をベースに `PRIORITY_REPLAY_CANDIDATES` を 104 件から 108 件に拡張（exp-121 から引き継いだ license/entitlement 2 件 + 新規 billing/compliance 2 件）。
- circuit / feature flag / quota / consent テーマを維持（workflow / task queue / checkpoint / idempotency は bank から除外）。
- replay bank: **2086** 件（ユニーク 2086、`run()` 内 `MAX_FINDINGS=2000` で末尾 86 件を切り詰め）。
- ローカル検証: `py_compile` / `aicomp validate` / `validate_submission_bundle.py` / `build_exp_notebook.py` を実行。
