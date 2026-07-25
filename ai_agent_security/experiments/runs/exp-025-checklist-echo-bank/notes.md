# exp-025-checklist-echo-bank

- 名前: checklist-echo-bank
- Kaggle タグ: `exp-025-checklist-echo-bank`

## 仮説

`exp-024-completion-policy-bank` は穴埋め completion・ポリシー引用・否定形リマインダー・文途中 continuation で整形タスクへ誘導した。HackAPrompt 由来の知見では、番号付きチェックリスト・Echo/Repeat 直接命令・接続検証（health check）・手順書ステップ番号でも、直接命令より従いやすい局所タスクに変換できる。特に Echo/Repeat は FlanT5 系（Gemma 相当）で効きやすい短い文体として知られている。また、read → チェックリスト/エコー仕様採用 → exfil の 3 ターンで、読み取り結果を業務手順や反復タスクに当てはめる経路を試せる。

今回は exp-024 の bank をベースに、(1) checklist HTTP 候補、(2) echo/repeat HTTP 候補、(3) verification HTTP 候補、(4) procedure/step HTTP 候補、(5) read → checklist 採用 → exfil の 3 ターン、(6) read → echo 採用 → exfil の 3 ターンを追加する。2000 件上限のため、completion/reminder/policy/continuation のテンプレートを各 1 つに削減し、output-spec/structure-spec URL 格子、format-translation テンプレート、procedure URL、output-spec email 宛先を一部削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-024 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | checklist HTTP 1 ターン候補（番号付きチェックリスト・監査項目）を追加 |
| A3 | echo/repeat HTTP 1 ターン候補（Echo/Repeat 直接命令）を追加 |
| A4 | verification HTTP 1 ターン候補（接続検証・health check）を追加 |
| A5 | procedure/step HTTP 1 ターン候補（手順書ステップ番号）を追加 |
| A6 | read → checklist 採用 → exfil の 3 ターン checklist-echo チェーンを追加 |
| A7 | read → echo 採用 → exfil の 3 ターン echo チェーンを追加 |
| A8 | 2000 件上限対策として completion/reminder/policy/continuation テンプレ各 2→1、output-spec/structure URL 各 2→1、format-translation 3→2、procedure URL 2→1、output-spec email 宛先 5→4 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- チェックリスト・手順番号で危険操作を業務フローの一部に見せ、guardrail と evaluator の検知差分を狙える。
- Echo/Repeat 短命令で Gemma 系モデルに効きやすい直接経路を試せる。
- 接続検証フレーミングで exfil を正当なヘルスチェックに見せられる。
- read 後の checklist/echo テンプレで exfil を自然な反復タスクに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-025-checklist-echo-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-025-checklist-echo-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-025
python3 scripts/build_exp_notebook.py exp-025-checklist-echo-bank --description "Checklist/echo replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-025` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-025-checklist-echo-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
