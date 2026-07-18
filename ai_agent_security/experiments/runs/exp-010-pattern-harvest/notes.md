# exp-010-pattern-harvest

- 名前: pattern-harvest
- Kaggle タグ: `exp-010-pattern-harvest`

## 仮説

`exp-006-hybrid-baseline-goexplore` が手元の最高 public score `0.56` で、`exp-007-phase-a-boost` は固定候補を広げた結果、Go-Explore の予算を圧迫して score が下がった可能性がある。

そこで今回は、生成フェーズ中に `eval_predicates()` で候補をふるい落とさず、過去実験で有望だった固定メッセージ列を `AttackCandidate` として直接返す。Kaggle の本採点は replay 結果のみを見るため、ローカルの deterministic/gym で miss になった候補でも、本番モデルで成功する可能性を残せる。

狙い:

- `exp-006` の replay 実績がある短い候補を先頭に置く。
- `exp-004`/`exp-007` の deputy 系・read -> share/post 系を候補 bank として収穫する。
- 固定候補の生成コストをほぼ 0 にして、残りを軽量 Go-Explore に渡す。
- 返却順は「既存実績候補 -> deputy 単発 -> config/weekly 2ターン -> untrusted-to-action 系 -> Go-Explore」とする。

## 戦略

| フェーズ | 内容 |
|---|---|
| A1 | `exp-006` のコア候補を直接返す |
| A2 | confused deputy を狙う単発通知候補を直接返す |
| A3 | `config.json` 読み取り後の post/forward/encoding 候補を直接返す |
| A4 | `weekly_report.txt` 読み取り後の通知・post 候補を直接返す |
| A5 | email/web など untrusted source 由来の指示を action に接続する候補を直接返す |
| B | 時間が残ればコンパクトな Go-Explore (`branch_batch=6`, `max_turns=8`) |

この実装ではローカルメトリクス CSV は書き出さない。今回の目的は診断より提出スコアの改善であり、replay bank の候補を落とさず Kaggle 側に渡すことを優先した。

## 期待する結果

主目的:

- `exp-006` の強い候補を維持しながら、`exp-007` より Go-Explore 予算を多く残す。
- ローカル判定で miss になりがちな候補も本番 replay に回し、多様性ボーナスと private guardrail 側の成功機会を増やす。

リーダーボード上の目標:

- `exp-007` の手動提出スコア `0.310` を上回る
- できれば `exp-006` のスコア `0.560` まで戻す、または改善する

これが `exp-006` を上回らない場合は、Kaggle の replay 結果から成功した候補だけを残し、次回は bank を縮小して Go-Explore 予算をさらに増やす。

## ローカル検証

完了済み:

```bash
python3 -m py_compile experiments/runs/exp-010-pattern-harvest/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-010-pattern-harvest/attack.py
$HOME/.local/bin/aicomp test redteam experiments/runs/exp-010-pattern-harvest/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
python3 scripts/validate_submission_bundle.py kaggle-push/exp-010
```

結果:

- `py_compile`: 成功
- `aicomp validate`: 成功
- `validate_submission_bundle.py`: 成功
- direct replay bank 返却候補: 66 件
- 最大ターン数: 2
- 最大メッセージ長: 89 文字
- `aicomp test deterministic/gym`: 4.2 秒で完了、score 0 / findings 0

注意: この実験は固定候補を即時返却するため、ローカル `deterministic/gym` は形式確認と候補 replay の smoke test として扱う。本番のスコアは Kaggle evaluator の LLM replay で確定する。

## 提出

1. `kaggle-push/exp-010` の bundle を push する。
2. Kaggle version description は `exp-010-pattern-harvest | direct replay bank + compact go-explore` にする。
3. CI で kernel version が作られたら、Kaggle UI の **Submit to Competition** から notebook を提出する。
4. スコアが反映されたら `python3 scripts/exp.py sync` を実行する。
