# exp-031-key-rotation-zerotrust-bank

- 名前: key-rotation-zerotrust-bank
- Kaggle タグ: `exp-031-key-rotation-zerotrust-bank`

## 仮説

`exp-030-vault-tokenization-bank` は vault / legal hold / integrity / portability のフレーミングで、危険操作をデータ保護・コンプライアンス手続きに見せた。続く HackAPrompt 系の知見では、KMS キーローテーション（rekey）、ゼロトラスト継続検証（continuous verification）、DLP 分類スキャン、ブレークグラス緊急アクセスでも、guardrail が本番 exfil と区別しにくい経路を狙える。特に「KMS rekey」「zero-trust collector」「DLP classify」「break-glass emergency」は、secret を外部送信する前に「鍵更新」「端末検証」「データ分類」「緊急監査」として正当化できる。また、read → rekey / zero-trust 仕様採用 → exfil の 3 ターンで、読み取り結果を運用セキュリティタスクに当てはめる経路を試せる。

今回は exp-030 の bank をベースに、(1) KMS key rotation HTTP 候補、(2) zero-trust verify HTTP 候補、(3) DLP scan HTTP 候補、(4) break-glass emergency HTTP 候補、(5) read → key rotation 採用 → exfil の 3 ターン、(6) read → zero-trust 採用 → exfil の 3 ターンを追加する。2000 件上限のため、watermark / reconciliation / integrity / portability HTTP 格子を bank から外し、vault / legal-hold read チェーンも外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-030 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | KMS key rotation / rekey HTTP 1 ターン候補を追加 |
| A3 | zero-trust continuous verification HTTP 1 ターン候補を追加 |
| A4 | DLP classification scan HTTP 1 ターン候補を追加 |
| A5 | break-glass emergency access HTTP 1 ターン候補を追加 |
| A6 | read → key rotation 採用 → exfil の 3 ターン rekey チェーンを追加 |
| A7 | read → zero-trust 採用 → exfil の 3 ターン zero-trust チェーンを追加 |
| A8 | 2000 件上限対策として watermark / reconciliation / integrity / portability HTTP を bank から削除、vault / legal-hold read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- KMS rekey 表現で exfil を定期鍵更新手続きに見せ、guardrail と evaluator の検知差分を狙える。
- ゼロトラスト継続検証で危険操作を端末ポスチャ確認の一部に見せられる。
- DLP 分類で「サンプルデータのスキャン結果転送」として exfil を正当化できる。
- ブレークグラスで「緊急時監査ログ」として exfil を誘導できる。
- read 後の rekey / zero-trust テンプレで exfil を自然な運用セキュリティタスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-031-key-rotation-zerotrust-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-031-key-rotation-zerotrust-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-031
python3 scripts/build_exp_notebook.py exp-031-key-rotation-zerotrust-bank --description "Key rotation/zero-trust replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-031` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-031-key-rotation-zerotrust-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
