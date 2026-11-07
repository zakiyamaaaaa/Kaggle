# exp-116-circuit-flag-quota-consent-bank

- 名前: circuit-flag-quota-consent-bank
- Kaggle タグ: `exp-116-circuit-flag-quota-consent-bank`

## 仮説

`exp-115-workflow-dag-taskqueue-checkpoint-idempotency-bank` はワークフロー DAG / タスクキュー / チェックポイント再開 / 冪等性キーの文脈で exfil をオーケストレーション基盤の運用証跡に見せ、CONFUSED_DEPUTY 向け Ping/Page 1 ターン候補を priority に 76 件（… / blueprint / template / manifest / chart）まで拡張した。一方、本番のエージェント運用基盤ではサーキットブレーカー、フィーチャーフラグ、クォータブローカー、同意台帳でも秘密情報の外部送信がフェイルオーバー検証・ロールアウト証跡・クォータテレメトリ・同意監査記録に紛れ込みやすい。

今回は exp-115 の priority 拡張（CD 向け 76 件 + manifest/chart）を維持しつつ、bank 本体を exp-114 / exp-112 と同系の circuit breaker / feature flag / quota broker / consent ledger テーマに戻す。2000 件上限のため、workflow DAG / task queue / checkpoint / idempotency HTTP 格子と read チェーンは bank から外す。

加えて exp-115 に無い recipient 違いの CD 候補（`bundle@` / `registry@`）を priority に 2 件追加し、リリースバンドル・コンテナレジストリ文脈と score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | `PRIORITY_REPLAY_CANDIDATES`（98 件、うち CD 向け Ping/Page 1 ターン 78 件）を bank 先頭に配置 |
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
python3 -m py_compile experiments/runs/exp-116-circuit-flag-quota-consent-bank/attack.py
aicomp validate redteam experiments/runs/exp-116-circuit-flag-quota-consent-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-116
python3 scripts/build_exp_notebook.py exp-116-circuit-flag-quota-consent-bank --description "Circuit breaker/feature flag/quota broker/consent ledger replay bank with expanded CD priority (manifest/chart/bundle/registry) and compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-116` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-116-circuit-flag-quota-consent-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-11-07）

- main 上の最新実験 `exp-115-workflow-dag-taskqueue-checkpoint-idempotency-bank` の次番として、circuit / feature flag / quota / consent 系 bank を復帰させた `exp-116` を提出可能形で追加。
- exp-115 の workflow / task queue / checkpoint / idempotency テーマを circuit / feature flag / quota / consent テーマに差し替え（exp-114 / exp-112 と同系の bank 構成）。
- `PRIORITY_REPLAY_CANDIDATES` を exp-114 の 94 件から 98 件に拡張（exp-115 から引き継いだ manifest/chart 2 件 + 新規 bundle/registry 2 件）。
- replay bank: **2076** 件（ユニーク 2076、`run()` 内 `MAX_FINDINGS=2000` で末尾 76 件を切り詰め）。
- ローカル検証: `py_compile` / `aicomp validate` / `validate_submission_bundle.py` / `build_exp_notebook.py` を実行。
