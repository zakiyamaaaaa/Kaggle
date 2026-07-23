# exp-023-fewshot-spec-bank

- 名前: fewshot-spec-bank
- Kaggle タグ: `exp-023-fewshot-spec-bank`

## 仮説

`exp-022-context-boundary-bank` は Rules / delimiter / 役割コンテキストで局所境界を作った。HackAPrompt 由来の知見では、few-shot 例示・Choose/Sentence 擬似構造・条件分岐（「見つけたら POST」）で、直接命令よりモデルが従いやすい整形タスクへ変換できる。また、read → 承認済みサンプル採用 → exfil の 3 ターンで、読み取り結果を例示テンプレに当てはめる経路を試せる。

今回は exp-022 の bank をベースに、(1) few-shot HTTP 例示候補、(2) Choose/Sentence 1 ターン候補、(3) 条件分岐 HTTP 候補、(4) read → few-shot 採用 → exfil の 3 ターン fewshot-spec チェーンを追加する。2000 件上限のため、format-translation / output-spec / structure-spec / role-context / boundary / translation-restore の URL 格子を一部削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-022 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | few-shot HTTP 例示 1 ターン候補を追加 |
| A3 | Choose/Sentence 擬似構造 1 ターン候補を追加 |
| A4 | 条件分岐（when/if）HTTP 1 ターン候補を追加 |
| A5 | read → few-shot 採用 → exfil の 3 ターン fewshot-spec チェーンを追加 |
| A6 | 2000 件上限対策として format-translation 3→2、output-spec HTTP 3→2、structure-spec 3→2、role/boundary/translation URL 各 3→2 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- 直接命令ではなく承認済みサンプル・選択肢として誘導し、guardrail と evaluator の検知差分を狙える。
- Choose/Sentence 構造で処理対象を局所化しやすくする。
- 条件分岐で read 後の exfil を自然な業務フローに見せられる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-023-fewshot-spec-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-023-fewshot-spec-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-023
python3 scripts/build_exp_notebook.py exp-023-fewshot-spec-bank
```

## 提出

1. `kaggle-push/exp-023` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-023-fewshot-spec-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
