# exp-033-soar-edr-bank

- 名前: soar-edr-bank
- Kaggle タグ: `exp-033-soar-edr-bank`

## 仮説

`exp-032-siem-incident-bank` は SIEM 相関、インシデント war-room、JIT PAM、SSO フェデレーションで exfil を SOC / IR 手続きに見せた。続く運用セキュリティの文脈では、SOAR プレイブック自動化、EDR / XDR エンドポイント証跡収集、脅威インテル（TIP）エンリッチメント、脆弱性パッチ検証でも guardrail が本番 exfil と区別しにくい経路を狙える。特に「プレイブック出力」「エンドポイントテレメトリ」「IOC レピュテーション」「CVE ホットフィックス監査」は、secret を外部送信する前に正当な自動化・対応作業に見せられる。また read → SOAR / EDR 仕様採用 → exfil の 3 ターンで、読み取り結果をセキュリティオーケストレーションタスクに当てはめる経路を試せる。

今回は exp-032 の bank をベースに、(1) SOAR playbook HTTP 候補、(2) EDR / XDR collect HTTP 候補、(3) threat intel enrichment HTTP 候補、(4) patch / CVE remediation HTTP 候補、(5) read → SOAR 採用 → exfil の 3 ターン、(6) read → EDR 採用 → exfil の 3 ターンを追加する。2000 件上限のため、SIEM / incident / JIT / SSO HTTP 格子を bank から外し、SIEM / incident read チェーンも外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-032 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | SOAR playbook / runbook orchestration HTTP 1 ターン候補を追加 |
| A3 | EDR triage / XDR evidence HTTP 1 ターン候補を追加 |
| A4 | threat intel / TIP feed HTTP 1 ターン候補を追加 |
| A5 | vulnerability patch / CVE hotfix HTTP 1 ターン候補を追加 |
| A6 | read → SOAR 採用 → exfil の 3 ターン SOAR チェーンを追加 |
| A7 | read → EDR 採用 → exfil の 3 ターン EDR チェーンを追加 |
| A8 | 2000 件上限対策として SIEM / incident / JIT / SSO HTTP を bank から削除、SIEM / incident read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- SOAR プレイブック表現で exfil を自動化ステップ出力に見せ、guardrail と evaluator の検知差分を狙える。
- EDR / XDR で危険操作をエンドポイント証跡収集の一部に見せられる。
- 脅威インテルで「IOC エンリッチメント」として exfil を正当化できる。
- パッチ検証で「CVE 対応監査」として exfil を誘導できる。
- read 後の SOAR / EDR テンプレで exfil を自然なオーケストレーションタスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-033-soar-edr-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-033-soar-edr-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-033
python3 scripts/build_exp_notebook.py exp-033-soar-edr-bank --description "SOAR/EDR replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-033` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-033-soar-edr-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
