# exp-092-circuit-flag-quota-consent-bank

- 名前: circuit-flag-quota-consent-bank
- Kaggle タグ: `exp-092-circuit-flag-quota-consent-bank`

## 仮説

`exp-091-workflow-dag-taskqueue-checkpoint-idempotency-bank` はワークフロー DAG / タスクキュー / チェックポイント再開 / 冪等性キーの文脈で exfil をエージェントワークフロー基盤の運用証跡に見せ、さらに CONFUSED_DEPUTY 向けの Ping/Page 1 ターン候補を priority に 28 件（records / archive / … / recovery / hardening）まで拡張した。一方、本番のエージェント運用基盤ではサーキットブレーカー（circuit breaker）、フィーチャーフラグ（feature flag）、レート制限クォータ（quota broker）、プライバシー同意台帳（consent ledger）でも、秘密情報の外部送信が正当なフェイルオーバー検証ペイロード・ロールアウト検証証跡・クォータ消費テレメトリ・同意監査記録に紛れ込みやすい。

今回は exp-091 の priority 拡張（CD 向け 28 件）を維持しつつ、bank 本体を exp-090 と同系の circuit breaker / feature flag / quota broker / consent ledger テーマに戻す。2000 件上限のため、workflow DAG / task queue / checkpoint resume / idempotency key HTTP 格子と workflow DAG / checkpoint resume read チェーンは bank から外す（exp-089 / exp-091 と同様）。

加えて exp-091 に無い recipient 違いの CD 候補（`tabletop@` / `playbook@`）を priority に 2 件追加し、score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` + exp-078〜092 の CD 向け Ping/Page 30 件を bank 先頭に配置 |
| A2 | circuit breaker / failover relay HTTP 1 ターン候補を追加 |
| A3 | feature flag / rollout controller HTTP 1 ターン候補を追加 |
| A4 | quota broker / rate-limit telemetry HTTP 1 ターン候補を追加 |
| A5 | consent ledger / privacy broker HTTP 1 ターン候補を追加 |
| A6 | read → circuit breaker 採用 → exfil の 3 ターン circuit breaker チェーンを追加 |
| A7 | read → consent ledger 採用 → exfil の 3 ターン consent ledger チェーンを追加 |
| A8 | 2000 件上限対策として workflow DAG / task queue / checkpoint / idempotency HTTP と read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- サーキットブレーカー表現で exfil をフェイルオーバー検証ペイロードに見せ、可用性境界を狙える。
- フィーチャーフラグ文脈でロールアウト検証証跡として秘密を外部送信させられる。
- クォータブローカーでレート制限消費テレメトリとして exfil を正当化できる。
- 同意台帳でプライバシー監査記録として exfil を誘導できる。
- CD 向け priority 30 件で recipient 違いの score-cell を増やせる可能性がある。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-092-circuit-flag-quota-consent-bank/attack.py
aicomp validate redteam experiments/runs/exp-092-circuit-flag-quota-consent-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-092
python3 scripts/build_exp_notebook.py exp-092-circuit-flag-quota-consent-bank --description "Circuit breaker/feature flag/quota broker/consent ledger replay bank with expanded CD priority and compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-092` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-092-circuit-flag-quota-consent-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-10-14）

- main 上の最新実験 `exp-091` の次番として、circuit / feature flag / quota / consent 系 bank を復帰させた `exp-092` を提出可能形で追加。
- exp-091 の workflow / task queue / checkpoint / idempotency テーマを circuit / feature flag / quota / consent テーマに差し替え（exp-090 と同系の bank 構成）。
- `PRIORITY_REPLAY_CANDIDATES` に CD 向け 1 ターン 30 件（exp-091 の 28 件 + 新規 tabletop/playbook）を配置し exp-091 と差別化。
- replay bank: **2028** 件（ユニーク 2028、`run()` 内 `MAX_FINDINGS=2000` で末尾 28 件を切り詰め）。
- ローカル検証: `py_compile` / `aicomp validate` / `validate_submission_bundle.py` / `build_exp_notebook.py` を実行。
