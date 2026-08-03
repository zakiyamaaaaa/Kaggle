# exp-034-casb-cnapp-bank

- 名前: casb-cnapp-bank
- Kaggle タグ: `exp-034-casb-cnapp-bank`

## 仮説

`exp-033-soar-edr-bank` は SOAR / EDR / 脅威インテル / パッチ対応の文脈で exfil を SOC 自動化に見せた。クラウドセキュリティ運用では、CASB（クラウドアクセスセキュリティブローカー）、CNAPP（クラウドネイティブアプリ保護）、IAM エンタイトルメント認証、ZTNA / SASE ゲートウェイ監査でも、秘密情報の外部送信が正当なポリシー同期やポスチャ評価に紛れ込みやすい。特に「SaaS シャドー IT 証跡」「クラウド設定ミスエビデンス」「特権アクセス認証」「ゼロトラストセッションコンテキスト」は、guardrail が本番 exfil と区別しにくい。

今回は exp-033 の bank をベースに、(1) CASB policy HTTP 候補、(2) CNAPP posture HTTP 候補、(3) IAM entitlement HTTP 候補、(4) ZTNA gateway HTTP 候補、(5) read → CASB 採用 → exfil の 3 ターン、(6) read → CNAPP 採用 → exfil の 3 ターンを追加する。2000 件上限のため、SOAR / EDR / threat intel / patch HTTP 格子と SOAR / EDR read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-033 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | CASB / SaaS broker HTTP 1 ターン候補を追加 |
| A3 | CNAPP / cloud posture HTTP 1 ターン候補を追加 |
| A4 | IAM entitlement / PAM attestation HTTP 1 ターン候補を追加 |
| A5 | ZTNA / SASE gateway HTTP 1 ターン候補を追加 |
| A6 | read → CASB 採用 → exfil の 3 ターン CASB チェーンを追加 |
| A7 | read → CNAPP 採用 → exfil の 3 ターン CNAPP チェーンを追加 |
| A8 | 2000 件上限対策として SOAR / EDR / threat intel / patch HTTP と SOAR / EDR read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- CASB 表現で exfil をクラウドアクセス証跡に見せ、検知差分を狙える。
- CNAPP で設定ミス調査の一環として秘密を外部送信させられる。
- IAM 認証フローで特権情報の「エンタイトルメント証跡」として exfil を正当化できる。
- ZTNA でセッションコンテキスト送信として exfil を誘導できる。
- read 後の CASB / CNAPP テンプレで exfil を自然なクラウドセキュリティタスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-034-casb-cnapp-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-034-casb-cnapp-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-034
python3 scripts/build_exp_notebook.py exp-034-casb-cnapp-bank --description "CASB/CNAPP cloud security replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-034` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-034-casb-cnapp-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
