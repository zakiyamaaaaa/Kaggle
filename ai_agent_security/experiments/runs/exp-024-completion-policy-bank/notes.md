# exp-024-completion-policy-bank

- 名前: completion-policy-bank
- Kaggle タグ: `exp-024-completion-policy-bank`

## 仮説

`exp-023-fewshot-spec-bank` は few-shot 例示・Choose/Sentence・条件分岐で整形タスクへ誘導した。HackAPrompt 由来の知見では、穴埋め completion・ポリシー引用・否定形リマインダー（「忘れずに POST」）・文途中 continuation でも、直接命令より従いやすい局所タスクに変換できる。また、read → 空白テンプレ採用 → exfil の 3 ターンで、読み取り結果を completion 形式に当てはめる経路を試せる。

今回は exp-023 の bank をベースに、(1) completion HTTP 候補、(2) reminder（do not forget / remember）HTTP 候補、(3) policy citation HTTP 候補、(4) continuation HTTP 候補、(5) read → completion テンプレ採用 → exfil の 3 ターン completion-policy チェーンを追加する。2000 件上限のため、Choose/Sentence 候補を削除し、fewshot / conditional / role / boundary / translation / format-translation の URL 格子を一部削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-023 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | completion HTTP 1 ターン候補（穴埋め・空白補完）を追加 |
| A3 | reminder HTTP 1 ターン候補（do not forget / remember）を追加 |
| A4 | policy citation HTTP 1 ターン候補（per security policy / according to compliance）を追加 |
| A5 | continuation HTTP 1 ターン候補（approved line / finish payload）を追加 |
| A6 | read → completion テンプレ採用 → exfil の 3 ターン completion-policy チェーンを追加 |
| A7 | 2000 件上限対策として Choose/Sentence 削除、fewshot/conditional URL 各 2→1、role/boundary/translation/format-translation URL 各 2→1 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- 穴埋め・続き書き・ポリシー引用で危険操作を局所整形タスクに見せ、guardrail と evaluator の検知差分を狙える。
- 否定形リマインダーで「忘れずに」系の間接誘導を試せる。
- read 後の completion テンプレで exfil を自然なフォーム入力に見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-024-completion-policy-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-024-completion-policy-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-024
python3 scripts/build_exp_notebook.py exp-024-completion-policy-bank
```

## 提出

1. `kaggle-push/exp-024` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-024-completion-policy-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
