# exp-027-forensics-backup-bank

- 名前: forensics-backup-bank
- Kaggle タグ: `exp-027-forensics-backup-bank`

## 仮説

`exp-026-sandbox-logging-bank` はサンドボックス/診断ログ/テレメトリ/権限委任のフレーミングで、危険操作を無害なテストや監査手続きに見せた。HackAPrompt 由来の知見では、フォレンジック証拠保全・バックアップ/ミラー同期・マスキング/匿名化テスト・ドライラン/リハーサルでも、guardrail が本番 exfil と区別しにくい経路を狙える。特に「forensic capture」「backup mirror」「redaction sample」「dry-run rehearsal」は、secret を外部送信する前に「保全」「同期」「検証」「予行演習」として正当化できる。また、read → forensics/backup 仕様採用 → exfil の 3 ターンで、読み取り結果をインシデント対応やバックアップ検証タスクに当てはめる経路を試せる。

今回は exp-026 の bank をベースに、(1) forensics/evidence HTTP 候補、(2) backup/mirror HTTP 候補、(3) redaction/anonymization HTTP 候補、(4) dry-run/rehearsal HTTP 候補、(5) read → forensics 採用 → exfil の 3 ターン、(6) read → backup 採用 → exfil の 3 ターンを追加する。2000 件上限のため、echo/verification テンプレートを 2→1、sandbox/logging/telemetry/delegation URL 格子を 2→1、delegation/telemetry テンプレートを 2→1 に削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-026 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | forensics/evidence HTTP 1 ターン候補（インシデント証拠保全）を追加 |
| A3 | backup/mirror HTTP 1 ターン候補（レプリカ同期）を追加 |
| A4 | redaction/anonymization HTTP 1 ターン候補（マスキング検証）を追加 |
| A5 | dry-run/rehearsal HTTP 1 ターン候補（予行演習）を追加 |
| A6 | read → forensics 採用 → exfil の 3 ターン forensics チェーンを追加 |
| A7 | read → backup 採用 → exfil の 3 ターン backup チェーンを追加 |
| A8 | 2000 件上限対策として echo/verification テンプレ 2→1、sandbox/logging/telemetry/delegation URL 各 2→1、delegation/telemetry テンプレ 2→1 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- フォレンジック/インシデント保全表現で exfil を証拠収集に見せ、guardrail と evaluator の検知差分を狙える。
- バックアップ/ミラー同期で危険操作をデータ保護手続きの一部に見せられる。
- マスキング/匿名化テストで「検証用サンプル」として exfil を正当化できる。
- ドライラン/リハーサルで副作用のない予行演習として exfil を誘導できる。
- read 後の forensics/backup テンプレで exfil を自然なインシデント対応・同期タスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-027-forensics-backup-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-027-forensics-backup-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-027
python3 scripts/build_exp_notebook.py exp-027-forensics-backup-bank --description "Forensics/backup replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-027` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-027-forensics-backup-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
