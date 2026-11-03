# Champion Arena

`Champion Arena`は、方策の候補を現在のチャンピオン集団に対戦させ、候補が十分な
成績を収めたときだけスロットの incumbent を更新する永続的なローカル評価器です。
試合そのものは既存の `local_arena.build_schedule` / `run_games` を使うため、seed、
seat swap、worker数による試合集合の差はありません。

## 設定

設定例は [`configs/champion_arena.json`](../configs/champion_arena.json) です。
各 `slots` は一つの archetype とその incumbent `champion` を持ち、候補はスロット内の
`candidates` に指定します。

```json
{
  "slots": {
    "general": {"champion": "baseline", "candidates": ["candidate"]},
    "replay_tape": {"champion": "public_salem", "candidates": []}
  },
  "games_per_matchup": 10,
  "seed": 20000,
  "swap_seats": true,
  "workers": 4,
  "promotion_threshold": 0.52,
  "output": "../outputs/champion_arena"
}
```

候補を複数スロットで管理する場合は、候補を
`{"name": "candidate", "slot": "general"}` の形でトップレベルの `candidates` に
書くこともできます。候補は、そのスロットの incumbent だけではなく、実行時点の
すべてのスロットの champion と対戦します。

## 実行

```bash
uv run python scripts/run_champion_arena.py \
  --config configs/champion_arena.json
```

試合数や出力先はCLIで上書きできます。

```bash
uv run python scripts/run_champion_arena.py \
  --games-per-matchup 25 --workers 4 --output outputs/champion_002
```

`--dry-run` は設定を読み込み、試合を実行せず予定数だけ表示します。`--smoke` は
matchupごとに1 seed（`swap_seats=true` なら2 seat）だけを1 workerで実行する短い
end-to-end確認です。

## 昇格規則

各ゲームを候補から見た勝敗に変換し、勝ちを1、引き分けを0.5、負けを0として全対戦の
平均を計算します。既定の `promotion_threshold=0.5` を厳密に上回り、候補に割り当て
られた全ゲームが `completed` である場合だけ昇格対象になります。従って、失敗ゲーム
が一つでもある候補は昇格しません。同じスロットに昇格対象が複数ある場合は平均値が
最大の候補を選び、同点は名前順で決めます。

## 出力とresume

出力ディレクトリには次のファイルが作られます。

- `state.json`: slotごとの champion、generation、昇格履歴。JSONキーをソートして保存します。
- `games.csv`: 実行した試合。完全一致する `game_id`、seed、seat、agent pair の
  `completed` 行だけを再利用します。失敗行は次回に再実行します。
- `promotion_report.csv`: 現generationで評価した候補ごとの対戦数、失敗数、平均score、
  eligibility、昇格結果。

stateとreport（およびcheckpointのgames）は一時ファイルを書いてから `os.replace` する
ため、途中終了で半端なファイルを残しにくくなっています。通常は同じ出力先で再実行
してください。seed、候補、champion、ゲーム数、seat設定のいずれかが変わると schedule
IDも変わり、その試合は安全に再評価されます。
