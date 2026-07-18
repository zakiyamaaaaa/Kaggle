# exp-015-structured-replay-bank

- 名前: structured-replay-bank
- Kaggle タグ: `exp-015-structured-replay-bank`

## 仮説

過去最良の `exp-006` は、短く replay しやすい固定候補を先に使う構成で public `0.56` を出している。直近の `exp-009` では、生成時の `eval_predicates` で候補を落とさず、固定リプレイ候補をそのまま evaluator に渡す方針が採られていた。

今回の実験では、その方針を継承しつつ、候補を以下の攻撃ファミリーごとに構造化して増やした。ローカル deterministic/gym と本番 LLM replay の差が大きい前提で、生成時探索に時間を使いすぎず、短い候補を広く replay に載せることを優先する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | `exp-006` 由来の短い既知有効候補を最優先で返す |
| A1 | 既知 secret 文字列の direct HTTP POST 候補を payload / URL / 文面で格子化 |
| A2 | `Notify` / `Inform` / `Alert` / `Remind` / `Let ... know` による confused deputy 候補を拡張 |
| A3 | `weekly_report.txt` / `config.json` / inbox / web open から HTTP・通知へつなぐ 2 ターン候補 |
| A4 | untrusted content から shell / file action へつなぐ候補を追加 |
| A5 | `secret.txt` の delete / overwrite / truncate / move 系 destructive write 候補 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- 固定候補を無条件に返すことで、ローカル predicate 判定の取りこぼしを避ける。
- 1〜2 ターン、短文、異なる宛先・URL・payload・操作を増やし、replay 成功時の `unique_cells` 多様性を狙う。
- exp-007 のように Phase A の実行コストで Go-Explore 予算を圧迫する問題を避ける。
- direct exfiltration / confused deputy / untrusted-to-action / destructive write の 4 predicate すべてに薄く広く候補を置く。

## ローカル検証

実装後に以下を実行した。

```bash
python3 -m py_compile experiments/runs/exp-015-structured-replay-bank/attack.py
aicomp validate redteam experiments/runs/exp-015-structured-replay-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-010
```

結果:

- `py_compile`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- `aicomp validate`: pass
- 固定候補数: `581`
- 最大ターン数: `2`
- 最大メッセージ長: `90`

追加 smoke test:

```bash
aicomp test redteam experiments/runs/exp-015-structured-replay-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `34.7s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy であり、0 findings は Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-010` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-015-structured-replay-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
