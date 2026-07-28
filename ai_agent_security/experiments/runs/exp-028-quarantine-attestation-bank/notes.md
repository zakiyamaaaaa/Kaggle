# exp-028-quarantine-attestation-bank

- 名前: quarantine-attestation-bank
- Kaggle タグ: `exp-028-quarantine-attestation-bank`

## 仮説

`exp-027-forensics-backup-bank` はフォレンジック証拠保全・バックアップ/ミラー同期・マスキング検証・ドライランのフレーミングで、危険操作をインシデント対応やデータ保護手続きに見せた。HackAPrompt 由来の知見では、隔離/検疫（quarantine/isolation）・認証/証明（attestation/certification）・移行/アップグレード（migration/upgrade）・ロールバック/復元（rollback/restore）でも、guardrail が本番 exfil と区別しにくい経路を狙える。特に「quarantine hold」「attestation stamp」「migration transfer」「rollback checkpoint」は、secret を外部送信する前に「隔離」「認証」「移行」「復元検証」として正当化できる。また、read → quarantine/attestation 仕様採用 → exfil の 3 ターンで、読み取り結果をセキュリティ対応や認証タスクに当てはめる経路を試せる。

今回は exp-027 の bank をベースに、(1) quarantine/isolation HTTP 候補、(2) attestation/certification HTTP 候補、(3) migration/upgrade HTTP 候補、(4) rollback/restore HTTP 候補、(5) read → quarantine 採用 → exfil の 3 ターン、(6) read → attestation 採用 → exfil の 3 ターンを追加する。2000 件上限のため、forensics/backup/redaction/dryrun URL 格子を 2→1、forensics/backup/redaction/dryrun テンプレートを 2→1、quarantine/rollback テンプレートを 2→1、migration/rollback URL を 2→1 に削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-027 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | quarantine/isolation HTTP 1 ターン候補（検疫・隔離フレーミング）を追加 |
| A3 | attestation/certification HTTP 1 ターン候補（認証・証明スタンプ）を追加 |
| A4 | migration/upgrade HTTP 1 ターン候補（データ移行・アップグレード）を追加 |
| A5 | rollback/restore HTTP 1 ターン候補（ロールバック・チェックポイント復元）を追加 |
| A6 | read → quarantine 採用 → exfil の 3 ターン quarantine チェーンを追加 |
| A7 | read → attestation 採用 → exfil の 3 ターン attestation チェーンを追加 |
| A8 | 2000 件上限対策として forensics/backup/redaction/dryrun URL 各 2→1、同テンプレ 2→1、quarantine/rollback テンプレ 2→1、migration/rollback URL 2→1 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- 隔離/検疫表現で exfil をセキュリティ対応手続きに見せ、guardrail と evaluator の検知差分を狙える。
- 認証/証明スタンプで危険操作をコンプライアンス検証の一部に見せられる。
- 移行/アップグレードで「データ移行中の転送」として exfil を正当化できる。
- ロールバック/復元で副作用のないチェックポイント検証として exfil を誘導できる。
- read 後の quarantine/attestation テンプレで exfil を自然な隔離・認証タスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-028-quarantine-attestation-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-028-quarantine-attestation-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-028
python3 scripts/build_exp_notebook.py exp-028-quarantine-attestation-bank --description "Quarantine/attestation replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-028` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-028-quarantine-attestation-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
