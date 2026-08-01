# exp-032-siem-incident-bank

- 名前: siem-incident-bank
- Kaggle タグ: `exp-032-siem-incident-bank`

## 仮説

`exp-031-key-rotation-zerotrust-bank` は KMS ローテーション、ゼロトラスト、DLP、ブレークグラスで exfil を運用セキュリティ手続きに見せた。続く HackAPrompt 系の知見では、SIEM 相関・脅威ハンティング、インシデント対応 war-room、JIT 特権昇格（PAM）、SSO フェデレーションでも guardrail が本番 exfil と区別しにくい経路を狙える。特に「IOC 相関」「インシデントタイムライン」「一時的 admin 昇格」「SAML ブローカー」は、secret を外部送信する前に正当な SOC / IR 作業に見せられる。また read → SIEM / incident 仕様採用 → exfil の 3 ターンで、読み取り結果をインシデント運用タスクに当てはめる経路を試せる。

今回は exp-031 の bank をベースに、(1) SIEM threat-hunt HTTP 候補、(2) incident war-room HTTP 候補、(3) JIT PAM HTTP 候補、(4) SSO federation HTTP 候補、(5) read → SIEM 採用 → exfil の 3 ターン、(6) read → incident 採用 → exfil の 3 ターンを追加する。2000 件上限のため、vault / legal-hold / key-rotation / zero-trust / DLP / break-glass HTTP 格子を bank から外し、seal / custody / key-rotation / zero-trust read チェーンも外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-031 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | SIEM correlation / threat-hunt HTTP 1 ターン候補を追加 |
| A3 | incident response war-room HTTP 1 ターン候補を追加 |
| A4 | JIT privileged access HTTP 1 ターン候補を追加 |
| A5 | SSO federation HTTP 1 ターン候補を追加 |
| A6 | read → SIEM 採用 → exfil の 3 ターン SIEM チェーンを追加 |
| A7 | read → incident 採用 → exfil の 3 ターン incident チェーンを追加 |
| A8 | 2000 件上限対策として vault / legal-hold / key-rotation / zero-trust / DLP / break-glass HTTP を bank から削除、seal / custody / key-rotation / zero-trust read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- SIEM 相関表現で exfil を脅威ハンティングの IOC 送信に見せ、guardrail と evaluator の検知差分を狙える。
- インシデント war-room で危険操作をタイムライン証跡の一部に見せられる。
- JIT PAM で「一時昇格のための credential 中継」として exfil を正当化できる。
- SSO フェデレーションで identity sync として exfil を誘導できる。
- read 後の SIEM / incident テンプレで exfil を自然な SOC 運用タスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-032-siem-incident-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-032-siem-incident-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-032
python3 scripts/build_exp_notebook.py exp-032-siem-incident-bank --description "SIEM/incident replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-032` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-032-siem-incident-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
