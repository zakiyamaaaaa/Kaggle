# 高速ローカルArena

このArenaは `kaggle-environments==1.32.7` のKaggricultureを、試合単位で独立した
プロセスに割り当てます。提出用の `agent(obs)` は変更せず、同じ2エージェント・seat・seed・
環境バージョンなら同じ結果になることをテストしています。

## 実行方法

ベンチマーク:

```bash
uv run python scripts/benchmark_local.py --games 100 --workers 4 --seed 1000 \
  --output outputs/benchmarks/run.json
```

互換性調査やReplay相当の全step保持が必要な場合は `--legacy-runner` を追加すると、
通常の `env.run()` 経路へ戻せます。通常のArenaはhistory-free fast runnerを使用します。

paired Arena（100 seed × 2 seat = 200試合）:

```bash
uv run python scripts/run_arena.py \
  --agents baseline,candidate \
  --games-per-pair 100 \
  --workers 4 \
  --seed 1000 \
  --swap-seats \
  --output outputs/arena_001
```

Population評価（全相手に共通の32 seed × 2 seat）:

```bash
uv run python scripts/run_population_arena.py \
  --candidate candidate \
  --tier development \
  --workers 14 \
  --output outputs/population/candidate-development-v1
```

Population設定は `configs/population.json` にあり、`development`（32 seeds）、
`adoption`（128 seeds）、`final`（256 seeds）を選べます。全相手へ同じseed blockを使うため、
相手別のpaired outcome profileを比較できます。通常のresumeと同様に完了済みgame_idは再利用し、
失敗試合だけ再実行します。

Population実行は通常の`games.csv`, `matchups.csv`, `benchmark.json`, `summary.json`に加え、
Bayesian Bradley–Terryの`ratings.csv`と`ratings-bt.json`、類似方策を逆密度で弱めた
`profiles.csv`、`gate.json`、設定とagentソースSHA-256を固定した`manifest.json`を生成します。
採用gateは全試合完了、candidate error 0、incumbentに対する
rating差の事後分散から計算したLCBが閾値を上回ることを要求します。個別LCBの単純な差では
共分散を失うため使用しません。cash差はratingにもgateにも使用しません。

開発用の共通trajectoryを保存する場合は `--trajectory` を追加します。例えば32 seedを
seat交換付きで走らせると64試合（32 pair）になり、親プロセスが次のParquetをまとめて書きます。

```bash
uv run python scripts/run_arena.py \
  --agents candidate,public_salem \
  --games-per-pair 32 \
  --workers 14 \
  --seed 10000 \
  --swap-seats \
  --trajectory \
  --output outputs/datasets/development_32seed_v1
```

`transitions.parquet` は player/seat ごとの各decision stepを1行にしたlong tableです。
`split=development` と `evaluation_stage=development`、pair/seed/seat、policy/opponent、
step/day/hour、正規化された `chosen_action_json`、最終reward・差分・win、および固定長の
scalar feature群を含みます。完全なnested observationは保存しません。`episodes.parquet`
は試合ごとの最終結果、`pairs.parquet` は同じseedのdirect/swapped席を対応付けた1行です。
trajectory modeでもworkerはファイルを書かず、rowsを親へ返します。既存の `games.csv` の
resumeはそのまま有効で、途中再開時は既存Parquetのtransitionを重複排除して結合します。

最初の開発データは上記条件で生成済みです。64/64試合が完了し、92,032 transition、
64 episode、32 pairを保存しました。candidateはpublic Salemに64敗、paired reward差の平均は
-158,687.30でした。この大差は強弱の教師信号にはなりますが、次の収集では中間的なspecialistや
過去checkpointを加えて状態・行動分布を広げる必要があります。

`--swap-seats` では各seedを2回使い、2回目だけplayer 0/1を交換します。したがって、
paired評価でseedが2行に現れるのは意図した仕様です。異なる方策間でShop・雑草の乱数系列が
同じになるとは仮定しません。

## worker数

省略時は論理CPU数を上限に使い、指定値も論理CPU数を超えないように丸めます。このマシン
（14論理CPU）では12試合の短い測定で1/2/4/14 workerがそれぞれ
1.58/2.88/5.19/8.42 games/s、100試合では4 workerが5.25 games/s、14 workerが
12.62 games/sでした。最大スループットには14、他作業と共存させる通常運用には4を推奨します。
各workerのpeak RSSは約210–218 MBだったため、メモリが少ない環境ではworkerを減らしてください。

## resume

同じコマンドと出力ディレクトリを再指定すると、`games.csv` の `status=completed` の
`game_id` を再利用します。失敗行は再実行します。最初から実行する場合は `--no-resume` を
指定します。結果ファイルは親プロセスだけがまとめて書き込むため、worker間の競合はありません。

## 出力

- `games.csv`: seed、seat、reward、winner、719 step、経過時間、status、失敗理由
- `matchups.csv`: seatをagent A/Bへ戻して集計した勝敗・平均reward・reward差
- `ratings.csv`: game_id順に計算したElo（初期1500、K=32）
- `summary.json`: スケジュール数、再利用数、失敗数、速度、実行環境
- `benchmark.json`: そのArena実行の平均・p50・p95、games/s、decisions/s

個別ベンチマークは指定したJSONへPython、OS、CPU、環境バージョン、CPU時間、peak RSS、
agent/framework時間比、ERROR/TIMEOUT/INVALID件数も保存し、同じ内容をstdoutへ出します。

## ベンチマーク結果

Apple arm64、macOS 26.6.2、Python 3.12.13、14論理CPU、kaggle-environments 1.32.7。
変更前の `scripts/run_local.py`（debug出力有効）は1試合0.94秒でした。変更後は通常実行で
debug/stdout/replay出力を無効にし、1 worker・10試合で6.286秒（1.591 games/s、
2288 agent calls/s、平均0.625秒）。100試合は4 workerで19.039秒（5.252 games/s）、
最初の並列Arenaは14 worker・100試合で7.588秒（13.179 games/s）でした。さらに
history-free fast runnerを導入した同seed比較では、legacy 7.138秒から3.550秒
（28.171 games/s）へ2.01倍高速化しました。実Arenaは3.642秒（27.457 games/s）です。
最初の変更前逐次100試合68.59秒との比較では、実Arena全体で約18.8倍です。

fast runnerは、各agentに独立したdeep-copy観測を渡す一方、汎用runnerによるschema全体の
再構築、stdout/stderrログ保持、720状態のReplay保持を省きます。actionの公式top-level
default、timeout、ERROR/INVALID状態、overage time、最終step処理は維持しています。
10試合・1 workerの同seed比較はlegacy 6.279秒、fast 2.876秒（2.18倍）でした。
peak RSSは約221 MBから195–200 MBへ約10%減少しました。

プロファイルではagentが総時間の約0.27%、Kaggriculture interpreterが約3.9%、残りの大半が
frameworkでした。内訳の主な重複計測値は共有状態copy 0.207秒、`structify` 0.185秒、
schema処理0.175秒/試合です。外部ログI/Oは通常実行では0、`make()` は約0.010秒/試合でした。このため、
方策のmicro-optimizationではなく、ログ無効化、試合単位multiprocessing、適応chunksize、
親側バッチ保存を優先しました。

## registryへagentを追加する

`src/kaggriculture_agent/registry.py` にトップレベルのcallableを追加し、`AGENTS` に名前を登録します。
callableは既存と同じ `agent(obs) -> action dict` を保ってください。checkpoint系はworkerからimport
可能なトップレベルfactory/関数にし、試合ごとの可変状態をモジュールglobalで共有しないでください。

## 既知の制約と次の候補

- fast runnerは `kaggle-environments==1.32.7` のKaggriculture action schemaと状態遷移に
  合わせたものです。環境バージョンを更新した場合はlegacyとの全step差分テストを再実行してください。
- engine内の不正な農作業は仕様上silent no-opです。Arenaはframeworkが付ける
  `ERROR`、`TIMEOUT`、`INVALID` を全step走査しますが、合法形式の無効操作数までは数えられません。
- peak RSSはプロセス単位の値です。全workerの同時使用量は概ねworker数に比例します。
- Replay、renderer、agent stdout/stderrログが必要な調査では `--legacy-runner` を使ってください。
- 次の候補はaction schemaと共有観測のversion guard、およびagent観測をcopy-on-write化できるかの
  検証です。agentによる観測変更の隔離を壊すため、単純な参照共有は行わないでください。
