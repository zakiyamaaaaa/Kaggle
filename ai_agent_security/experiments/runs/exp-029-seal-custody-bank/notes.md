# exp-029-seal-custody-bank

- 名前: seal-custody-bank
- Kaggle タグ: `exp-029-seal-custody-bank`

## 仮説

`exp-028-quarantine-attestation-bank` は隔離/認証/移行/ロールバックのフレーミングで、危険操作をセキュリティ対応手続きに見せた。HackAPrompt 由来の知見では、暗号学的封印（seal/signing）・証拠保管（custody/chain-of-custody）・透かし/指紋（watermark/fingerprint）・照合/決済（reconciliation/settlement）でも、guardrail が本番 exfil と区別しにくい経路を狙える。特に「seal stamp」「custody record」「watermark tag」「reconcile settlement」は、secret を外部送信する前に「署名」「保管」「識別」「照合」として正当化できる。また、read → seal/custody 仕様採用 → exfil の 3 ターンで、読み取り結果をセキュリティ対応や証拠管理タスクに当てはめる経路を試せる。

今回は exp-028 の bank をベースに、(1) seal/signing HTTP 候補、(2) custody/chain-of-custody HTTP 候補、(3) watermark/fingerprint HTTP 候補、(4) reconciliation/settlement HTTP 候補、(5) read → seal 採用 → exfil の 3 ターン、(6) read → custody 採用 → exfil の 3 ターンを追加する。2000 件上限のため、quarantine/attestation URL 格子を 2→1、migration テンプレ 2→1、quarantine/attestation read follow-up を 2→1、sandbox/logging/fewshot/checklist/conditional/role/boundary/translation/output-spec テンプレを削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-028 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | seal/signing HTTP 1 ターン候補（暗号封印・署名フレーミング）を追加 |
| A3 | custody/chain-of-custody HTTP 1 ターン候補（証拠保管・連鎖記録）を追加 |
| A4 | watermark/fingerprint HTTP 1 ターン候補（透かし・指紋タグ）を追加 |
| A5 | reconciliation/settlement HTTP 1 ターン候補（照合・決済検証）を追加 |
| A6 | read → seal 採用 → exfil の 3 ターン seal チェーンを追加 |
| A7 | read → custody 採用 → exfil の 3 ターン custody チェーンを追加 |
| A8 | 2000 件上限対策として quarantine/attestation URL 各 2→1、migration テンプレ 2→1、各種 HTTP テンプレ削減、quarantine/attestation read follow-up 2→1 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- 封印/署名表現で exfil を暗号検証手続きに見せ、guardrail と evaluator の検知差分を狙える。
- 証拠保管/連鎖記録で危険操作をフォレンジック管理の一部に見せられる。
- 透かし/指紋タグで「識別用サンプル転送」として exfil を正当化できる。
- 照合/決済で「データ整合性検証」として exfil を誘導できる。
- read 後の seal/custody テンプレで exfil を自然な署名・保管タスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-029-seal-custody-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-029-seal-custody-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-029
python3 scripts/build_exp_notebook.py exp-029-seal-custody-bank --description "Seal/custody replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-029` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-029-seal-custody-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
