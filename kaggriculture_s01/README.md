# Kaggriculture S01

高速な通常Arenaに加え、固定checkpointのSHA-256、共通seed・seat交換、Bayesian
Bradley–Terry、outcome-profile密度補正、LCB採用gateをまとめたPopulation Arenaを提供します。
実行方法と評価tierは [docs/local-arena.md](docs/local-arena.md) を参照してください。
共通Parquet、終局scoreモデル、候補評価の履歴は
[docs/model-improvement.md](docs/model-improvement.md) に記録します。

Kaggleの **Kaggriculture** 用エージェント開発プロジェクトです。農場シミュレーションの観測値を読み、毎ターンの移動・作業・市場取引を決めるエージェントを作成します。

## 目的

空の農場からスタートし、作物・家畜・土地・市場を管理して、シーズン終了時の資金を他のエージェントより多くすることが目的です。勝敗は収益額そのものではなく、他エージェントとの対戦結果をもとにしたランキングで決まります。

このコンペは、LLMを必須とするものではありません。まずはルールベース・探索・最適化を土台にし、必要に応じてLLMを計画・説明・方策改善に使える構成にしています。

Kaggle概要ではPoints & Medals対象です。現在の公式タイムライン上の最終提出締切は **2026年9月30日 23:59 UTC（日本時間10月1日 08:59）** です。締切やルールは変更される可能性があるため、提出前に公式ページを確認してください。

## セットアップ

```bash
cd /Users/shoichiyamazaki/Kaggle/kaggriculture_s01
uv sync --dev
```

`uv` がPython 3.12環境と依存パッケージをプロジェクト内の `.venv` に用意します。

## ローカル対戦テスト

```bash
uv run python scripts/run_local.py
```

現在の雛形エージェントをKaggriculture環境で実行し、エピソード終了時の報酬を表示します。依存環境のバージョンは、競技環境とのずれを避けるため `kaggle-environments==1.32.7` に固定しています。

## 提出候補の履歴

候補を追加するたびに、この節へ特徴、固定panel評価、提出ID、ソースハッシュを追記します。
Public scoreは固定テストの点数ではなく、継続対戦で変動するlive ratingです。必ず取得時刻と
Public episode数を併記し、試合数が異なる候補をscoreだけで比較しません。

### 候補の特徴

| 候補 | ベース | 主な変更 | 位置づけ | Source SHA-256 |
|---|---|---|---|---|
| `candidate-calibration-v1` | 公開Salem 2900方策 | 変更なし | ローカル／Public校正基準。独自改善ではない | `3b1cb91f...dff8fe9` |
| `candidate-front-run-v2` | v1 | WHEATとFERTILIZERを1 step前の市場先回り売却へ追加 | 市場タイミング改善 | `8dc0fd92...be9362` |
| `candidate-liquidate-v3` | v2 | day 29にShedの残在庫を全売却 | 旧Arena champion | `5c113946...dedecd` |
| `candidate-early-milk-v1` | v3 | day 28の12時以降にMILKを先行売却し、day 29に残在庫を全売却 | Population Arenaの現champion。Public提出済み | `fd01b949...8305d` |

### 比較結果

固定ローカルpanelはseeds 17000–17031、両seat、`public_salem`対戦です。
この表のPublic値は履歴比較用です。最新値は [`docs/public-evaluation.md`](docs/public-evaluation.md) の
2026-09-20 CLIスナップショットを参照してください。

| 候補 | 固定panel戦績 | 平均reward差 | 直前版との採用検証 | Submission ID | Public episodes | Public rating |
|---|---:|---:|---|---:|---:|---:|
| v1 | reference | 0.00 | baselineへ64勝0敗 | `56348566` | 4 | 846.0 |
| v2 | 60勝4敗 | +270.30 | v1へ61勝3敗、+292.47 | `56348673` | 3 | 761.2 |
| v3 | 60勝4敗 | +727.09 | v2へ58勝6敗、+425.25 | `56348847` | 2 | 779.7 |
| early-milk-v1 | — | `56361538` | final tierでv3へ471勝41敗、平均差+588.69 | `56361538` | — | 977.7 |

ローカルの最終reward差は診断指標です。Kaggle ratingはcoin差ではなく勝敗だけで更新されるため、
候補昇格の一次指標には複数の強い相手に対するpaired勝率を使います。詳細な履歴と変動理由は
[`docs/public-evaluation.md`](docs/public-evaluation.md)、各提出の再現条件は
`submissions/<candidate>/MANIFEST.md`を参照してください。

### 独立方策の開発

Salem系とは別に、固定Replayを使わず現在観測だけから毎step再計画する独立方策を開発しています。
現在の独立系列代表は、50区画・12 hands・牛4頭と羊4頭・小麦/イチゴ/メロンを組み合わせた `economy_mix50` です。

| 方策 | 耕作区画 | baseline戦績 | 直前版との比較 | candidate戦績 | 状態 |
|---|---:|---:|---:|---:|---|
| `independent_v0` | 10 | 64勝0敗 | reference | 0勝64敗 | 保存 |
| `independent_crop_v1` | 8 | 64勝0敗 | v0へ63勝1敗、平均差+2,022.70 | 0勝64敗 | 旧単一farmer代表 |
| `independent-workers-v2` | 25＋8 hands | 64勝0敗、平均cash 30,144 | crop_v1へscreen 8勝0敗 | 0勝64敗 | 独立系列の提出可能版。v1から方策差分なし |
| `independent_12` | 12 | — | screenでv0に全敗 | — | 不採用 |
| `independent_v1` | 16 | 16勝0敗 | screenでv0に全敗 | — | 不採用 |

単一farmerでは8区画が最適でしたが、期限付きタスクを重複なく割り当てる8 handsスケジューラにより
NW全25区画へ拡張できました。独立版は提出・Public校正に使える実行品質ですが、Salem系とは
まだ大差があるため主力 `candidate` は置き換えません。

2026-09-20の採用確認は128 seed・両seat、全3,072試合で実行失敗0。牛8頭版は旧workers版に256勝0敗でした。
`candidate` 戦の平均cashは旧版14,570.87から47,861.68へ改善しましたが、戦績は0勝256敗でした。
この段階では牛8頭版を独立系列の代表とし、提出用 `submissions/independent-planner-cows-v3.zip` を検証しました（未提出）。
GBDT計画選択は勝敗改善を示せず不採用、CNNは保留とします。
詳細は[改善サイクルの結果](docs/strategy-cycle-2026-09-20.md)、代表の記録は `configs/independent_champion.json` を参照してください。

続く経済計画の改善では、牛・羊と作物を分散する50区画版を採用しました。未使用256 seed・両seat・5相手の最終評価7,680試合は実行失敗0。牛8頭版に対する平均score差は+0.0910（95%区間[+0.0754, +0.1055]）でした。主力相手は2勝510敗で、主力 `candidate` を維持します。
提出ID `56396545` は2026-09-21確認時点でCOMPLETE、Public scoreは599.5でした。収支分解・実装・全評価・採用判断・Public結果は[経済計画の最終結果](docs/economic-plan-v4.md)と[Public評価履歴](docs/public-evaluation.md)に記録しました。

## エージェントの場所

- `src/kaggriculture_agent/agent.py`: Kaggle提出用の `agent(obs)`
- `main.py`: 依存なしで単体提出できる初期ベースライン
- `scripts/run_local.py`: ローカル実行・対戦確認
- `tests/`: 最低限のスキーマ・動作テスト
- `notebooks/`: Kaggle Notebookへ移植する際の作業場所

Kaggle提出時は、提出ファイルのルートに `agent(obs)` を置くか、Kaggle Notebookからこの関数を呼び出します。

## 公式ページ

- [Kaggriculture（Kaggle）](https://www.kaggle.com/competitions/kaggriculture/)
- [Kaggle Environments](https://github.com/Kaggle/kaggle-environments)
- [ローカル確認済みエンジン仕様](docs/engine-spec.md)
- [戦略メモ](docs/strategy-notes.md)
- [今後の改善計画](docs/improvement-plan.md)
- [One More Wheat次期戦略と需要控除型先売り](docs/strategy-next-2026-09-21.md)
- [Local / Public評価履歴](docs/public-evaluation.md)

公式ページの締切・ルール・現在の環境仕様を最終確認してから提出してください。
