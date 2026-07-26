# exp-026-sandbox-logging-bank

- 名前: sandbox-logging-bank
- Kaggle タグ: `exp-026-sandbox-logging-bank`

## 仮説

`exp-025-checklist-echo-bank` はチェックリスト・Echo/Repeat・接続検証・手順番号で整形タスクへ誘導した。HackAPrompt 由来の知見では、サンドボックス/ステージング環境・診断ログ記録・テレメトリ収集・権限委任（on behalf of）のフレーミングでも、危険操作を無害なテストや監査手続きに見せられる。特に「sandbox test」「diagnostic log」「telemetry sample」「authorized relay」は、guardrail が本番 exfil と区別しにくい経路を狙える。また、read → sandbox/logging 仕様採用 → exfil の 3 ターンで、読み取り結果を検証タスクやログ記録に当てはめる経路を試せる。

今回は exp-025 の bank をベースに、(1) sandbox/staging HTTP 候補、(2) diagnostic logging HTTP 候補、(3) telemetry/metrics HTTP 候補、(4) delegation/authority HTTP 候補、(5) read → sandbox 採用 → exfil の 3 ターン、(6) read → logging 採用 → exfil の 3 ターンを追加する。2000 件上限のため、checklist/echo/verification URL 格子を 2→1、procedure テンプレートを 2→1、notice topics を 4→3 に削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-025 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | sandbox/staging HTTP 1 ターン候補（テスト環境フレーミング）を追加 |
| A3 | diagnostic logging HTTP 1 ターン候補（ログ記録・診断キャプチャ）を追加 |
| A4 | telemetry/metrics HTTP 1 ターン候補（メトリクス報告）を追加 |
| A5 | delegation/authority HTTP 1 ターン候補（権限委任・承認済みリレー）を追加 |
| A6 | read → sandbox 採用 → exfil の 3 ターン sandbox-logging チェーンを追加 |
| A7 | read → logging 採用 → exfil の 3 ターン logging チェーンを追加 |
| A8 | 2000 件上限対策として checklist/echo/verification URL 各 2→1、procedure テンプレ 2→1、notice topics 4→3 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- サンドボックス/ステージング表現で exfil を無害なテストに見せ、guardrail と evaluator の検知差分を狙える。
- 診断ログ・テレメトリ収集で危険操作を監査手続きの一部に見せられる。
- 権限委任フレーミングで「承認済みリレー」として exfil を正当化できる。
- read 後の sandbox/logging テンプレで exfil を自然な検証・記録タスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-026-sandbox-logging-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-026-sandbox-logging-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-026
python3 scripts/build_exp_notebook.py exp-026-sandbox-logging-bank --description "Sandbox/logging replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-026` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-026-sandbox-logging-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
