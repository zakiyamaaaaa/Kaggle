# Population rating

`scripts/rate_arena.py` は Arena の `games.csv` から Bayesian
Bradley–Terry rating を推定する。学習・候補選抜では平均値 `mu` だけでなく、
不確実性を差し引いた `LCB = mu - 2 * sigma` を採用判定に使う。

```bash
uv run python scripts/rate_arena.py outputs/arena_001/games.csv \
  --output outputs/arena_001/ratings-bt.json
```

## 仕様

- rating に使うのは終局時の勝ち・引き分け・負けだけで、cash差は使わない。
- 同じagent組み合わせの大量対戦が過信につながらないよう、既定では1組あたり
  500試合を有効試合数の上限にする。
- 片側だけrewardが欠けた失敗は、そのagentのエラー負けとして数える。
- 両側reward欠損など原因を特定できない失敗は除外し、件数を保存する。
- 比較グラフが分断されている場合は、根拠のない異集団ランキングを作らず停止する。
- 同じ `game_id` の重複は停止する。resume結果の二重集計を防ぐためである。
- 表示ratingは母集団平均1000の内部指標で、Kaggle Public scoreとは直接比較できない。

`ratings-bt.json` にはagent別の `mu`, `sigma`, `lcb`, 95%区間、試合数、
エラー数に加え、組み合わせ別の勝敗、モデル勝率、rating差の不確実性、共分散行列を
保存する。候補対incumbentの採用判定には個別LCBの差ではなく、共分散を含む
`(mu_candidate - mu_incumbent) - 2 * sigma_difference`を使う。

## 現時点の範囲

Population設定、paired-seatスケジュール、近似方策の密度補正、採用gateまでArenaへ
統合済みである。実行方法は `docs/local-arena.md` を参照する。

## Population設定

`configs/population.json` は比較母集団をregistry名、戦略family、archetype、役割、重みで
固定する。`frozen_checkpoint` はartifactのSHA-256も保持し、意図しない差し替えを
対戦前に検出する。

```bash
uv run python scripts/inspect_population.py
```

評価tierは次のseed範囲を使い、各seedでseatを交換する。

- `development`: 32 seeds × 2 seats = 64試合/組
- `adoption`: 128 seeds × 2 seats = 256試合/組
- `final`: 256 seeds × 2 seats = 512試合/組

各tierのseed範囲は重ならない。設定全体のfingerprintを評価結果へ記録することで、
異なる母集団やartifactを同じ実験として混ぜない。
