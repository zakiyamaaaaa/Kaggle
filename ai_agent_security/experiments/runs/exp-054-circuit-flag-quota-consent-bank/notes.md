# exp-054-circuit-flag-quota-consent-bank

- 名前: circuit-flag-quota-consent-bank
- Kaggle タグ: `exp-054-circuit-flag-quota-consent-bank`

## 仮説

`exp-053-workflow-dag-taskqueue-checkpoint-idempotency-bank` はワークフロー DAG / タスクキュー / チェックポイント再開 / 冪等性キーの文脈で exfil をエージェントワークフロー基盤の運用証跡に見せた。一方、本番のエージェント運用基盤ではサーキットブレーカー（circuit breaker）、フィーチャーフラグ（feature flag）、レート制限クォータ（quota broker）、プライバシー同意台帳（consent ledger）でも、秘密情報の外部送信が正当なフェイルオーバー検証ペイロード・ロールアウト検証証跡・クォータ消費テレメトリ・同意監査記録に紛れ込みやすい。

今回は exp-053 の bank をベースに、(1) circuit breaker HTTP 候補、(2) feature flag HTTP 候補、(3) quota broker HTTP 候補、(4) consent ledger HTTP 候補、(5) read → circuit breaker 採用 → exfil の 3 ターン、(6) read → consent ledger 採用 → exfil の 3 ターンを追加する。2000 件上限のため、workflow DAG / task queue / checkpoint resume / idempotency key HTTP 格子と workflow DAG / checkpoint resume read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-053 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | circuit breaker / failover relay HTTP 1 ターン候補を追加 |
| A3 | feature flag / rollout controller HTTP 1 ターン候補を追加 |
| A4 | quota broker / rate-limit telemetry HTTP 1 ターン候補を追加 |
| A5 | consent ledger / privacy broker HTTP 1 ターン候補を追加 |
| A6 | read → circuit breaker 採用 → exfil の 3 ターン circuit breaker チェーンを追加 |
| A7 | read → consent ledger 採用 → exfil の 3 ターン consent ledger チェーンを追加 |
| A8 | 2000 件上限対策として workflow DAG / task queue / checkpoint resume / idempotency key HTTP と workflow DAG / checkpoint resume read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- サーキットブレーカー表現で exfil をフェイルオーバー検証ペイロードに見せ、可用性境界を狙える。
- フィーチャーフラグ文脈でロールアウト検証証跡として秘密を外部送信させられる。
- クォータブローカーでレート制限消費テレメトリとして exfil を正当化できる。
- 同意台帳でプライバシー監査記録として exfil を誘導できる。
- read 後の circuit breaker / consent ledger テンプレで exfil を自然なエージェント運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-054-circuit-flag-quota-consent-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-054-circuit-flag-quota-consent-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-054
python3 scripts/build_exp_notebook.py exp-054-circuit-flag-quota-consent-bank --description "Circuit breaker/feature flag/quota broker/consent ledger replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-054` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-054-circuit-flag-quota-consent-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
