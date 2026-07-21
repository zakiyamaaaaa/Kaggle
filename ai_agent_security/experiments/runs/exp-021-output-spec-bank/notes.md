# exp-021-output-spec-bank

- 名前: output-spec-bank
- Kaggle タグ: `exp-021-output-spec-bank`

## 仮説

`exp-020-format-translation-bank` は format/translation フレーミングで間接表現を追加し、固定 replay bank の多様性を広げた。HackAPrompt 由来の知見では、直接命令よりも「出力形式の指定」や「擬似構造（JSON spec / ticket template）」が guardrail 回避や evaluator 差分に効きやすい。

今回は exp-020 の bank をベースに、(1) POST body / email body のフィールド整形を指示する output-spec 候補、(2) JSON spec・ticket template・audit form などの擬似構造候補、(3) read → strip/normalize → exfil の output-spec チェーンを追加する。2000 件上限のため、HTTP / handoff / ticket / compliance / format-translation の格子を一部削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-020 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | output-spec HTTP 候補（POST body を value のみにする、label 除去など）を追加 |
| A3 | output-spec email 候補（body field を value のみにする）を追加 |
| A4 | pseudo-structure 1 ターン候補（JSON spec / ticket template / audit form）を追加 |
| A5 | read → output-spec follow-up の 2 ターン候補を追加 |
| A6 | read → strip/normalize → exfil の 3 ターン output-spec チェーンを追加 |
| A7 | read → structure bridge → schema follow-up の 3 ターン候補を追加 |
| A8 | 2000 件上限対策として HTTP テンプレート 3→2、handoff/ticket/compliance テンプレート各 4→3、format-translation 4→3 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- 危険操作そのものではなく、ツール引数の整形タスクとして誘導し、guardrail と evaluator の検知差分を狙える。
- JSON spec / ticket body field などの擬似構造で、エージェントに局所コンテキストを作りやすくする。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-021-output-spec-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-021-output-spec-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-021
python3 scripts/build_exp_notebook.py exp-021-output-spec-bank
```

結果:

- `py_compile`: pass
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `1995`
- unique 候補数: `1995`
- 最大ターン数: `3`
- 最大メッセージ長: `130`

追加 smoke test:

```bash
$HOME/.local/bin/aicomp test redteam experiments/runs/exp-021-output-spec-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `118.2s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy として扱い、0 findings でも Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-021` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-021-output-spec-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
