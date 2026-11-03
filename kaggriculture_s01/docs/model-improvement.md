# Model improvement log

## Common dataset v3

現在のagentコードで、候補と3つの強いSalem系相手を共通seed 33000–33031、seat交換で
再収集した。`outputs/datasets/common_strong_32seed_v3` は次を含む。

- 192 games / 96 paired seeds
- 276,096 transitions
- game/seatあたり719 transitions
- duplicate key、null、failed gameはいずれも0
- WHEAT、FERTILIZER、MELON、MILK、STRAWBERRY、WOOLの個別market price、
  market inventory、own seed、own shed特徴

旧`development_32seed_v1`は収集時点のcandidateが現在と異なり、Public Salemへ0勝64敗の
古い分布である。再現用には残すが、新しいモデルの学習には使わない。

## Outcome model v1

`outputs/models/outcome_candidate_strong_v1`に、勝=1、引分=0.5、負=0を予測する
seed-grouped modelを保存した。24 train seeds / 8 validation seedsで、実効validation標本は
48 gamesである。選択には各gameの最終観測におけるBrier scoreを使う。

| Model | Validation last-state Brier |
|---|---:|
| Constant baseline | 0.1617 |
| Basic | 0.1540 |
| Terminal/market | 0.1333 |
| Full | 0.1307 |

Full modelはbaselineを約19.1%改善した。ただしこれはstate-value modelであり、未実行actionの
価値を直接比較できない。提出agentへ組み込まず、次のcandidate-action datasetとrerankerの
基礎artifactとして扱う。

## Weed-recovery hybrid

現行front-run + day29 liquidationを固定し、weed replayだけ4/12/16 stepsへ変更した。
16-seed総当たりscreenでは12-stepがBT首位となったため、別seedの正式Population developmentへ
進めた。

12-step候補は384/384試合を完了し、errorは0。現行incumbentへの直接成績は13勝11敗40分、
family-balanced scoreは現行の0.7496から0.7605へ改善した。一方、rating差LCBは−73.18で
採用gateを通らなかった。したがってregistryには実験候補として残すが、`candidate`は変更せず、
128-seed adoptionへも昇格しない。

## Terminal MILK liquidation

共通Parquetの品目別特徴を使い、day 28に一品目だけ先行売却する候補をscreenした。
WHEAT、FERTILIZER、MELON、MILK、STRAWBERRY、WOOLのうち、MILKが最も安定して強かった。
探索seedと最終seedを分離し、各tierで全相手とのseat交換を行った。

| Tier | Seed range | Games | Family-balanced score | v3との差LCB | Errors |
|---|---:|---:|---:|---:|---:|
| Development | 30000–30031 | 384 | 0.9085 | +209.14 | 0 |
| Adoption | 40000–40127 | 1,536 | 0.9333 | +327.30 | 0 |
| Final | 60000–60255 | 3,072 | 0.9394 | +367.47 | 0 |

Final tierの強敵別成績は`public_salem`へ469勝42敗1分、
`salem_front_wheat_fertilizer`へ416勝96敗、旧champion `salem_liquidate_29`へ
471勝41敗だった。全試合の完走率は100%である。この結果に基づき、day 28の12時以降に
MILKだけを全売却し、day 29に残在庫を全売却する方策をArenaの`candidate`へ昇格した。

追加検証では、売却開始時刻6/12/15/18時が同じdevelopment結果となり、9時だけ僅かに低下した。
MILKにSTRAWBERRYを加えた候補は候補同士のscreenでは強かったが、Population developmentで
`public_salem`勝率59.4%、front-runner勝率39.1%まで低下したため棄却した。売却をday 27へ
前倒しした候補もscore 0.4936、差のLCB −460.32で棄却した。これは候補同士だけの総当たりを
採用判定に使わず、方策familyを分散した固定populationを維持する必要性を示している。

提出可能artifactは`submissions/candidate-early-milk-v1.zip`。ZIP内の単一ファイル版とArena版を
seed 71001、同一seatで比較し、最終reward、status、719 stepsの一致を確認した。
