# exp-030-vault-tokenization-bank

- 名前: vault-tokenization-bank
- Kaggle タグ: `exp-030-vault-tokenization-bank`

## 仮説

`exp-029-seal-custody-bank` は封印・証拠保管・透かし・照合のフレーミングで、危険操作をセキュリティ手続きに見せた。続く HackAPrompt 系の知見では、シークレット保管（vault）、訴訟保全（legal hold）、整合性検証（integrity/checksum）、データポータビリティ（export/portability）でも、guardrail が本番 exfil と区別しにくい経路を狙える。特に「vault store」「litigation hold」「checksum verify」「portability package」は、secret を外部送信する前に「保管」「保全」「検証」「エクスポート」として正当化できる。また、read → vault/legal-hold 仕様採用 → exfil の 3 ターンで、読み取り結果をコンプライアンスやデータ管理タスクに当てはめる経路を試せる。

今回は exp-029 の bank をベースに、(1) vault HTTP 候補、(2) legal hold HTTP 候補、(3) integrity HTTP 候補、(4) portability HTTP 候補、(5) read → vault 採用 → exfil の 3 ターン、(6) read → legal hold 採用 → exfil の 3 ターンを追加する。2000 件上限のため、seal/custody/watermark/reconciliation URL 格子を 2→1、seal/custody read follow-up を 2→1 に削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-029 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | vault/secret store HTTP 1 ターン候補を追加 |
| A3 | legal hold/litigation preserve HTTP 1 ターン候補を追加 |
| A4 | integrity/checksum verify HTTP 1 ターン候補を追加 |
| A5 | data portability export HTTP 1 ターン候補を追加 |
| A6 | read → vault 採用 → exfil の 3 ターン vault チェーンを追加 |
| A7 | read → legal hold 採用 → exfil の 3 ターン legal hold チェーンを追加 |
| A8 | 2000 件上限対策として seal/custody/watermark/reconciliation URL 各 2→1、seal/custody read follow-up 2→1 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- シークレット vault 表現で exfil を正当な保管手続きに見せ、guardrail と evaluator の検知差分を狙える。
- 訴訟保全で危険操作を eDiscovery 管理の一部に見せられる。
- チェックサム検証で「整合性確認用サンプル転送」として exfil を正当化できる。
- データポータビリティで「エクスポートパッケージ」として exfil を誘導できる。
- read 後の vault/legal-hold テンプレで exfil を自然なデータ管理タスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-030-vault-tokenization-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-030-vault-tokenization-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-030
python3 scripts/build_exp_notebook.py exp-030-vault-tokenization-bank --description "Vault/tokenization replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-030` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-030-vault-tokenization-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
