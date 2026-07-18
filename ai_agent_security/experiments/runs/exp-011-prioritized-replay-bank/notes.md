# exp-011-prioritized-replay-bank

- 名前: prioritized-replay-bank
- Kaggle タグ: `exp-011-prioritized-replay-bank`

## 仮説

<<<<<<< HEAD
`exp-010` は固定リプレイ候補を 581 件まで広げ、生成時 predicate 判定による取りこぼしを避ける設計だった。一方で、本番 replay では候補ごとに LLM とツール実行の時間を使うため、低確度候補が多いと高確度候補の replay 余力を圧迫する可能性がある。

今回の実験では、過去最高の `exp-006` コアを先頭に固定し、`exp-010` の候補空間から成功しやすいと考えられる短い 1〜2 ターンだけを選抜する。狙いは、広げすぎた候補集合を減らしつつ、EXFILTRATION / CONFUSED_DEPUTY / UNTRUSTED_TO_ACTION / DESTRUCTIVE_WRITE の多様性は残すこと。
=======
過去最高の `exp-006-hybrid-baseline-goexplore` は public `0.56` で、短く replay しやすい固定候補を先に返す構成が有効だった。一方で、直近の `exp-010-structured-replay-bank` は固定候補を 581 件まで広げており、低シグナル候補が多く含まれる可能性がある。

今回の実験では、`exp-010` の「ローカル predicate で候補を落とさず evaluator に直接渡す」方針は維持しつつ、候補を `exp-006` / `exp-004` / `exp-007` 由来の高優先パターンに絞る。候補の順序は、既知有効候補、直接 HTTP exfil、confused deputy、read -> share / untrusted action、destructive write の順にした。
>>>>>>> origin/main

## 実装内容

| フェーズ | 内容 |
|---|---|
<<<<<<< HEAD
| A0 | `exp-006` 由来の既知有効候補を最優先で返す |
| A1 | `SECRET_API_KEY` / `PASSWORD` / `SECRET_MARKER` の direct HTTP POST を URL・表現違いで少数選抜 |
| A2 | `Notify` / `Inform` / `Alert` など、`email/send/upload` を避けた confused deputy 文面を選抜 |
| A3 | `weekly_report.txt` / `config.json` / inbox / web から通知・HTTP へつなぐ 2 ターン候補 |
| A4 | untrusted content から shell / `secret.txt` 操作へつなぐ 2 ターン候補 |
| A5 | `secret.txt` の delete / overwrite / truncate / move 系 destructive write 候補 |
| B | 時間が十分残る場合のみ、compact Go-Explore を補助的に追加 |

## 期待する効果

- 高確度候補を先頭に置き、replay 時間を低確度の格子候補で浪費しにくくする。
- `exp-010` と同じく、生成時 `eval_predicates` には依存せず固定候補を無条件に返す。
- 候補を短文・1〜2 ターンに保ち、本番 LLM replay での再現性を優先する。
- 4 つの主要 predicate に薄く広く候補を残し、成功時の `unique_cells` 多様性を狙う。
=======
| A0 | `exp-006` 由来の短い既知有効候補を最優先で返す |
| A1 | `SECRET_API_KEY=sk_live_test` / `PASSWORD=test123` / marker 系の direct HTTP 候補を厳選 |
| A2 | `Notify` / `Inform` / `Alert` / `Remind` / `Let ... know` の confused deputy 候補を少数追加 |
| A3 | `weekly_report.txt` / `config.json` から通知・HTTP・DBA 宛へつなぐ 2 ターン候補を追加 |
| A4 | inbox / web page の untrusted content から shell / `secret.txt` action へつなぐ候補を追加 |
| A5 | `secret.txt` の delete / overwrite / truncate / clear 系 destructive write 候補を追加 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- `exp-006` の強い初期候補を維持し、replay 成功候補を候補リスト先頭に置く。
- `exp-010` より候補数を絞ることで、低シグナルな格子展開の影響を抑える。
- ローカル deterministic/gym と本番 LLM replay の差を考慮し、生成時の predicate 判定では候補を捨てない。
- Go-Explore は十分な残り時間があるときだけ使い、固定候補の返却を最優先する。
>>>>>>> origin/main

## ローカル検証

実装後に以下を実行した。

```bash
python3 -m py_compile experiments/runs/exp-011-prioritized-replay-bank/attack.py
aicomp validate redteam experiments/runs/exp-011-prioritized-replay-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-011
```

結果:

- `py_compile`: pass
<<<<<<< HEAD
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- `aicomp validate`: pass
- 固定候補数: `62`
- 最大ターン数: `2`
- 最大メッセージ長: `86`
=======
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `72`
- 最大ターン数: `2`
- 最大メッセージ長: `89`
>>>>>>> origin/main

追加 smoke test:

```bash
aicomp test redteam experiments/runs/exp-011-prioritized-replay-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

<<<<<<< HEAD
- 実行時間: `3.7s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy であり、0 findings は Kaggle 提出の blocker とは扱わない。
=======
- 実行時間: `4.2s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy として扱う。
>>>>>>> origin/main

## 提出

1. `kaggle-push/exp-011` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-011-prioritized-replay-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
