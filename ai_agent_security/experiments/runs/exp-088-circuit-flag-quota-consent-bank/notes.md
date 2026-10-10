# exp-088-circuit-flag-quota-consent-bank

- 名前: circuit-flag-quota-consent-bank
- Kaggle タグ: `exp-088-circuit-flag-quota-consent-bank`

## 仮説

`exp-087-workflow-dag-taskqueue-checkpoint-idempotency-bank` はワークフロー DAG / タスクキュー / チェックポイント再開 / 冪等性キーの文脈で exfil をエージェントワークフロー基盤の運用証跡に見せ、さらに CONFUSED_DEPUTY 向けの Ping/Page 1 ターン候補を priority に 20 件（records / archive / compliance / legal / risk / privacy / governance / audit / trust / ethics / safety / integrity / reliability / assurance / continuity / availability / incident / observability / resilience / postmortem）まで拡張した。一方、本番のエージェント運用基盤ではサーキットブレーカー（circuit breaker）、フィーチャーフラグ（feature flag）、レート制限クォータ（quota broker）、プライバシー同意台帳（consent ledger）でも、秘密情報の外部送信が正当なフェイルオーバー検証ペイロード・ロールアウト検証証跡・クォータ消費テレメトリ・同意監査記録に紛れ込みやすい。

今回は exp-087 の priority 拡張（CD 向け 20 件）を維持しつつ、bank 本体を exp-086 と同系の circuit breaker / feature flag / quota broker / consent ledger テーマに戻す。2000 件上限のため、workflow DAG / task queue / checkpoint resume / idempotency key HTTP 格子と workflow DAG / checkpoint resume read チェーンは bank から外す（exp-084 / exp-086 と同様）。

加えて exp-087 に無い recipient 違いの CD 候補（`forensic@` / `remediation@`）を priority に 2 件追加し、score-cell の多様性をわずかに広げる。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-081 系の core replay / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` + exp-078〜088 の CD 向け Ping/Page 22 件を bank 先頭に配置 |
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
- CD 向け priority 22 件で recipient 違いの score-cell を増やせる可能性がある。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-088-circuit-flag-quota-consent-bank/attack.py
python3 -m aicomp validate redteam experiments/runs/exp-088-circuit-flag-quota-consent-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-088
python3 scripts/build_exp_notebook.py exp-088-circuit-flag-quota-consent-bank --description "Circuit breaker/feature flag/quota broker/consent ledger replay bank with expanded CD priority and compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-088` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-088-circuit-flag-quota-consent-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。

## 自動化実行メモ（2026-10-10）

- main 上の最新実験 `exp-087` の次番として、circuit / feature flag / quota / consent 系 bank を復帰させた `exp-088` を提出可能形で追加。
- exp-087 の workflow / task queue / checkpoint / idempotency テーマを circuit / feature flag / quota / consent テーマに差し替え（exp-086 と同系の bank 構成）。
- `PRIORITY_REPLAY_CANDIDATES` に CD 向け 1 ターン 22 件（exp-087 の 20 件 + 新規 forensic/remediation）を配置し exp-087 と差別化。
- replay bank: **2020** 件（ユニーク 2020、`run()` 内 `MAX_FINDINGS=2000` で末尾 20 件を切り詰め、最大 3 ターン、最大メッセージ長 144）。
- ローカル検証: `py_compile` OK、`aicomp validate` OK、`validate_submission_bundle.py kaggle-push/exp-088` OK、`build_exp_notebook.py` で notebook 同期 OK。
