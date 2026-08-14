# exp-044-policy-guardrail-router-sandbox-bank

- 名前: policy-guardrail-router-sandbox-bank
- Kaggle タグ: `exp-044-policy-guardrail-router-sandbox-bank`

## 仮説

`exp-043-otel-planner-memory-webhook-bank` は OpenTelemetry / planner-executor / agent memory / webhook callback の文脈で exfil をエージェント運用証跡に見せた。本番の AI エージェント基盤では、ポリシーエンジン（OPA 認可決定ログ）、プロンプトファイアウォール（guardrail 監査テレメトリ）、モデルルーター（inference gateway バッチログ）、ツールサンドボックス（capability broker 監査）でも、秘密情報の外部送信が正当なセキュリティ監査・ルーティング証跡・サンドボックス逸脱検知に紛れ込みやすい。

今回は exp-043 の bank をベースに、(1) policy engine / OPA authorization HTTP 候補、(2) guardrail audit / prompt firewall HTTP 候補、(3) model router / inference gateway HTTP 候補、(4) tool sandbox / capability broker HTTP 候補、(5) read → policy engine 採用 → exfil の 3 ターン、(6) read → guardrail audit 採用 → exfil の 3 ターンを追加する。2000 件上限のため、OpenTelemetry / planner-executor / agent memory / webhook callback HTTP 格子と OTEL / planner read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-043 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | policy engine / OPA authorization HTTP 1 ターン候補を追加 |
| A3 | guardrail audit / prompt firewall HTTP 1 ターン候補を追加 |
| A4 | model router / inference gateway HTTP 1 ターン候補を追加 |
| A5 | tool sandbox / capability broker HTTP 1 ターン候補を追加 |
| A6 | read → policy engine 採用 → exfil の 3 ターン policy engine チェーンを追加 |
| A7 | read → guardrail audit 採用 → exfil の 3 ターン guardrail audit チェーンを追加 |
| A8 | 2000 件上限対策として OpenTelemetry / planner-executor / agent memory / webhook callback HTTP と OTEL / planner read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- ポリシーエンジン表現で exfil を OPA 認可決定ログに見せ、認可監査境界を狙える。
- guardrail audit 文脈でプロンプトファイアウォール違反テレメトリとして秘密を外部送信させられる。
- モデルルーターで inference gateway バッチログとして exfil を正当化できる。
- ツールサンドボックスで capability broker 監査として exfil を誘導できる。
- read 後の policy engine / guardrail audit テンプレで exfil を自然な AI セキュリティ基盤タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-044-policy-guardrail-router-sandbox-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-044-policy-guardrail-router-sandbox-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-044
python3 scripts/build_exp_notebook.py exp-044-policy-guardrail-router-sandbox-bank --description "Policy engine/guardrail audit/model router/tool sandbox replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-044` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-044-policy-guardrail-router-sandbox-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
