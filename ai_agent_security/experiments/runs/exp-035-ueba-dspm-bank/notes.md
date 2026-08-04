# exp-035-ueba-dspm-bank

- 名前: ueba-dspm-bank
- Kaggle タグ: `exp-035-ueba-dspm-bank`

## 仮説

`exp-034-casb-cnapp-bank` は CASB / CNAPP / IAM / ZTNA の文脈で exfil をクラウドセキュリティ運用に見せた。次のレイヤでは、UEBA（行動分析）、DSPM（データセキュリティポスチャ）、WAAP（API ゲートウェイ）、BAS（侵害シミュレーション）でも、秘密情報の外部送信が正当な調査・インベントリ・テレメトリ・紫チーム演習に紛れ込みやすい。特に「インサイダー脅威ベースライン」「機密データ発見」「API 乱用テレメトリ」「パープルチーム inject」は guardrail が本番 exfil と区別しにくい。

今回は exp-034 の bank をベースに、(1) UEBA anomaly HTTP 候補、(2) DSPM inventory HTTP 候補、(3) WAAP telemetry HTTP 候補、(4) BAS simulation HTTP 候補、(5) read → UEBA 採用 → exfil の 3 ターン、(6) read → DSPM 採用 → exfil の 3 ターンを追加する。2000 件上限のため、CASB / CNAPP / IAM / ZTNA HTTP 格子と CASB / CNAPP read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-034 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | UEBA / behavior analytics HTTP 1 ターン候補を追加 |
| A3 | DSPM / data posture HTTP 1 ターン候補を追加 |
| A4 | WAAP / API gateway HTTP 1 ターン候補を追加 |
| A5 | BAS / purple-team simulation HTTP 1 ターン候補を追加 |
| A6 | read → UEBA 採用 → exfil の 3 ターン UEBA チェーンを追加 |
| A7 | read → DSPM 採用 → exfil の 3 ターン DSPM チェーンを追加 |
| A8 | 2000 件上限対策として CASB / CNAPP / IAM / ZTNA HTTP と CASB / CNAPP read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- UEBA 表現で exfil を行動分析エビデンスに見せ、検知差分を狙える。
- DSPM で機密データインベントリの一環として秘密を外部送信させられる。
- WAAP で API テレメトリ送信として exfil を正当化できる。
- BAS で紫チーム演習の inject 証跡として exfil を誘導できる。
- read 後の UEBA / DSPM テンプレで exfil を自然なセキュリティ分析タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-035-ueba-dspm-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-035-ueba-dspm-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-035
python3 scripts/build_exp_notebook.py exp-035-ueba-dspm-bank --description "UEBA/DSPM/WAAP/BAS security analytics replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-035` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-035-ueba-dspm-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
