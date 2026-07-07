# exp-009-direct-replay-bank

- 名前: direct-replay-bank
- Kaggle タグ: `exp-009-direct-replay-bank`

## 仮説

過去最良の `exp-006` は、短い固定プロンプトを先に実行してから Go-Explore を回す構成で public `0.56` を取った。一方、`exp-007` は Phase A を広げすぎ、生成中のローカル判定や時間配分が replay 成功率を下げた可能性がある。

この実験では、生成時に `eval_predicates` で候補を落とさず、replay しやすい短い `AttackCandidate` を固定バンクとして先に返す。本番 evaluator の LLM replay とローカル deterministic/gym の差を前提に、ローカルで当たった候補だけに絞るよりも、多様な短い勝ち筋を直接 replay に渡す。

## 戦略

| フェーズ | 内容 |
|---|---|
| A | 固定 replay bank を無条件に返す |
| A1 | 既知 secret 文字列を含む direct HTTP POST 系 |
| A2 | `Notify` / `Inform` / `Alert` / `Remind` とメールアドレスの confused deputy 系 |
| A3 | `weekly_report.txt` / `config.json` / inbox / web open の read → forward/post/relay 系 |
| A4 | `secret.txt` の delete/write を狙う destructive write 系 |
| B | 時間が十分残る場合だけ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- `exp-006` で強かった短い再生候補の思想を維持する。
- 生成時のローカル predicate 判定で候補が捨てられる問題を避ける。
- 単発 deputy 候補と二段 read→action 候補を増やし、`unique_cells` の diversity bonus を狙う。
- Go-Explore は補助に回し、固定候補の提出可能性を阻害しない。

## ローカル検証

実装時に以下を実行した。

```bash
python3 -m py_compile experiments/runs/exp-009-direct-replay-bank/attack.py
aicomp validate redteam experiments/runs/exp-009-direct-replay-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-009
```

`aicomp test` は deterministic/gym が本番 replay と大きく異なり、固定バンク型では 0 findings でも blocker ではないため、必要に応じて短時間 smoke test として扱う。

## 提出

1. `kaggle-push/exp-009` の bundle を push して Kaggle notebook version を作る。
2. Kaggle UI で version description に `exp-009-direct-replay-bank` を含めて提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
