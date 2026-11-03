# Kaggriculture 戦略メモ

Kaggricultureで有効そうな仕様、観測、Discussionの実測報告、戦略仮説をまとめる。実装前の判断材料と実験ログの入口として使う。

- 最終更新: 2026-09-12
- 対象環境: `kaggle-environments==1.32.7`
- 詳細仕様: [engine-spec.md](engine-spec.md)
- 保存済みDiscussion: [index.csv](../discussions/index.csv)

## 情報の確度

| ラベル | 意味 |
|---|---|
| **確認済み** | ローカルの1.32.7エンジン実装で確認 |
| **運営確認** | Competition運営の投稿・コメントで確認 |
| **参加者実測** | Discussion投稿者の環境で測定。再検証が必要 |
| **仮説** | このプロジェクトで今後検証する案 |

## 現時点の基本方針

最初からend-to-end RLを狙わず、次の順序で強くする。

1. 正しいpaired evaluationを作る
2. 期限付き作業を落とさない決定論的executorを作る
3. 安定した固定生産計画を探索する
4. Shop構成と市場在庫に反応する
5. 相手の生産・売却圧力に反応する
6. 必要ならマクロ戦略の選択だけ探索・学習する

最終形は「日次戦略 → 作業スケジューラ → 永続タスクexecutor」の3層構造を想定する。

## 勝敗と評価

- **確認済み:** 終了時のrewardは現金 `farm.money` のみ。
- **確認済み:** Shed在庫、作業員の所持品、盤面の未収穫物に終了時価値は付かない。
- **含意:** 終盤は在庫価値より現金化を優先する。
- **参加者実測:** day 28以降に売却reserveを解除して約`+$2.8K/game`になった例がある。
- **参加者実測:** Live ratingは数十試合では大きく変動し、約60試合で概ね収束するという報告がある。
- **参加者実測:** 数十rating程度の差はノイズの可能性がある。
- **運営ルール由来:** 最終評価はLive ratingの履歴ではなく、締切後の対戦結果を用いる。

### ローカル評価の原則

- 同じseedをseat 0/1で1回ずつ実行する。
- 2試合の結果を平均して1サンプルとして扱う。
- tuning用seedと、一度も見ずに採否判定するholdout seedを分ける。
- 1種類の相手だけでなく、固定baseline、公開強豪、過去の自分を含むpanelで評価する。
- 平均cash差だけでなく、勝率を主要指標にする。
- Shop系列が元Replayから変わった試合と、維持された試合を分ける。
- 変更は原則1実験1仮説にする。

### 記録する指標

- paired win rate
- 最終cashとcash差
- 商品別の生産量、収穫量、売却注文量、実約定量、実売上
- 歩行数、作業数、PASS数
- silent no-op推定回数
- 水やり・給餌・収穫の期限切れ
- 動物逃亡数
- Shed overflow量
- 終了時の未売却在庫
- 商品別平均約定価格とprice impact
- 土地購入日、日別hands数
- Shop構成とengine seed

## 期限付き作業

### 作物

- **確認済み:** 植えた当日に水をやらないと、その日の終了時に雑草化する。
- **確認済み:** 2日連続で未給水になると雑草化する。
- **確認済み:** Tomatoはage 8から毎日、最大4回生産する。
- **確認済み:** Strawberryはage 10から2日おき、最大4回生産する。
- **確認済み:** Strawberryは無限生産ではない。
- **確認済み:** 肥料は使用日を含めて3日間有効。
- **確認済み:** 肥料が生産日や収量加算期間と重ならなければ、収量増加に寄与しない。
- **参加者実測:** 生産予定が2日以内のtileだけ施肥することで、無駄な施肥を減らせた例がある。

### 動物

- **確認済み:** 2日連続で給餌されないと動物が逃げる。
- **確認済み:** FEEDはWheatを1個消費する。
- **確認済み:** CARE bonusは同じ日にCAREとFEEDが両方成功した場合だけ`+1`される。
- **確認済み:** 生産日に未給餌だと蓄積CARE bonusを生産に使えず、その後リセットされる。
- **確認済み:** 生産日のCAREはその日の生産ではなく次回以降に効く。
- **参加者実測:** CAREを給餌済み動物だけに限定して、Milk `+25%`、Wool `+51%`になった例がある。
- **参加者実測:** 給餌タスクを完了まで中断しないことで、動物逃亡が約10頭から約1頭になった例がある。

### executorの優先順位案

1. 植えた当日のWATER
2. 逃亡を防ぐFEED
3. 生産日のFEED
4. 収穫可能物のHARVEST
5. FEEDと対になったCARE
6. 生産日に重なるFERTILIZE
7. COLLECT_FERTILIZER
8. 新規PLANT・動物PLACE
9. 通常の運搬

同順位では、締切までの余裕、移動距離、失敗時の損失で並べる。

## workerと経路

- **確認済み:** handsは日末に全員消える。
- **確認済み:** 日末にhandsの所持品はShedへ回収され、容量超過分は消滅する。
- **確認済み:** HIRE費用は日ごとに`1, 1, 2, 3, 5, 8, ...`と増え、翌日リセットされる。
- **確認済み:** LOCKED tile上へ移動できるが、通常のtile操作はできない。
- **確認済み:** Shedアクセス地点は `(4,4), (5,4), (4,5), (5,5)`。
- **参加者実測:** 強い公開戦略の中には大量のhandsを使うものがある一方、別の測定ではworker追加の限界価値が0だったという報告もある。
- **判断:** hands数は固定観念で決めず、作業期限を満たす最小人数をseed panelで探索する。

### 永続タスク

次のような複数stepタスクは、途中で別の仕事へ切り替えない。

- `PICKUP animal → 移動 → PLACE`
- `PICKUP WHEAT → 移動 → FEED`
- `HARVEST → Shedへ移動 → DROP`
- `PICKUP FERTILIZER → 移動 → FERTILIZE`

workerが保持するのは目標の私的コピーではなく、現在のタスクと対象だけにする。毎step、実際のtile状態を読み直して成功・失敗・完了を判定する。

## 市場

- **確認済み:** 市場売買は1個ずつ処理され、各単位で価格が変化する。
- **確認済み:** `SELL item 100` は100個が同じ価格で売れる注文ではない。
- **確認済み:** Shed在庫が尽きると注文の残りは停止する。
- **確認済み:** 売価が1のとき、売却しても市場在庫は増えない。
- **確認済み:** 売却できるのはShed内の商品だけ。
- **確認済み:** 肥料も売却可能。
- **参加者実測:** あるReplayで、1,751個の売却注文に対して実約定は1,456個、単純見積り107,392に対して実売上90,079だった。
- **含意:** 注文数量×現在価格で戦略を評価しない。エンジンと同じ単位約定ledgerを使う。

### 1.32.7の不足価格

- **運営確認:** CARROT、TOMATO、EGGは在庫不足が閾値を超えると価格が急上昇する。
- **運営公表値:** 生産がない場合の発火目安はTOMATO 50%、CARROT 26%、EGG 22%のゲーム。
- **参加者実測:** Carrotは変更後すぐ広く採用された。
- **参加者実測:** Tomatoは高い価格上限が観測されたが、採用率は低かった。
- **参加者実測:** Eggの上昇は3商品の中で比較的弱かった。
- **判断:** 常時生産ではなく、Shop構成と市場在庫から不足局面を検出して切り替える。

### Shopから考えられるシグナル

| Shop | 注目商品 | 初期仮説 |
|---|---|---|
| PET_CAFE | CARROT×2 | 複数出現時にCarrot増産 |
| PIZZA_SHOP | TOMATO, MILK, WHEAT | Tomato不足を監視 |
| FARMERS_MARKET | 全作物系 | 作物在庫の広い下支え |
| BAKERY | EGG, WHEAT | Gooseと飼料需要を評価 |
| BRUNCH_SPOT | EGG, WHEAT, STRAWBERRY | Egg/Strawberry候補 |
| YARN_STORE | WOOL×2 | Sheepの有力条件 |
| SMOOTHIE_SHOP | STRAWBERRY, MILK | 長期作物・Cow候補 |
| ICE_CREAM_SHOP | STRAWBERRY, MILK, WHEAT | 複合生産候補 |

Shopは復元抽出で、同じ種類が複数出現する。商品選択にはShop名だけでなく、現在在庫、残り日数、自分の市場impactを含める。

## 対戦中に見える相手情報

### 直接観測できるもの

- 現在cash
- 全tileの状態
- farmerとhandsの位置
- hands数と当日の雇用回数
- 解放済み区画
- 作物の種類、植付日、水やり、未給水日数、蓄積収量、施肥期限
- COOP、PASTUREの位置
- 動物の種類、配置日、蓄積生産物、未給餌日数、給餌、CARE、CARE bonus、肥料回収可否

### 直接見えないもの

- 相手のShed在庫
- 相手の種在庫
- 相手farmer・handsの所持品
- 相手の現在action、未約定注文、内部計画
- Shedにある未配置動物

### 差分から推定できるもの

- 座標差から移動
- tile変化からPLANT、WATER、HARVEST、BUILD、PLACE、DIG
- flag変化からFEED、CARE、FERTILIZE、COLLECT_FERTILIZER
- hands・土地変化からHIRE、BUY_LAND
- cashと市場在庫の変化から売買候補
- 収穫履歴からShed在庫の上限
- 作物・動物構成から将来生産量とWheat需要

市場の変化には両者の注文とTown需要が混ざるため、売買数量の完全な特定は難しい。

### 相手情報の使い道

優先度順に検証する。

1. 相手の商品別将来生産量を予測する。
2. 相手の収穫履歴から売却可能量を推定する。
3. 同じ商品の同時大量売却を避ける。
4. 相手が生産しない不足商品を選ぶ。
5. 終盤の相手の潜在資産を含めて、リード・ビハインドを判断する。
6. 序盤行動から既知戦略familyを分類する。

推定状態の例:

```text
相手の推定最終資産
= 現在cash
+ 盤面上の収穫可能価値
+ 推定Shed在庫価値
- 今後必要な飼料・雇用費
```

- **参加者実測:** 相手familyをstep 12前後で特定して反応する価値が約38/gameだった例がある。
- **判断:** 高度な相手分類より、商品別の生産量と売却圧力の推定を先に作る。

## Replay/tape環境

- **参加者実測:** 公開上位Replayの720ターンを再生するtape戦略がLeaderboardに多い。
- **参加者実測:** 26試合中25試合の相手が既知tapeと60%以上一致したという報告がある。
- **参加者実測:** 14公開実装の総当たりでは、新しい実装が古い実装をほぼ順当に上回り、じゃんけん構造が弱かった。
- **含意:** 公開tapeに勝つことと、独立した未知戦略に強いことは同じではない。
- **含意:** 最新公開tapeは提出物としてではなく、benchmarkと行動監査の材料に使う。

### Replay評価の落とし穴

- step 0は初期化。action抽出のoff-by-oneに注意する。
- 自分のReplayから抽出したactionを自分のagentと比較し、100%一致を確認する。
- 元のseatを保持し、両seatで検証する。
- 自分の盤面状態が変わると雑草抽選の乱数消費が変わり、Shop系列も変化し得る。
- 記録済み相手が本来と異なるShop系列で動くと、自分が過大評価される可能性がある。

## RL・探索

- **参加者実測:** flat end-to-end PPOは個別に妥当な操作を覚えても、719step全体の経済計画が崩れやすい。
- **参加者実測:** JAXで約10,000 steps/sec、heuristic模倣後にPPO、50% self-play・25% active・25% checkpoint bankで学習した例がある。
- **参加者実測:** 学習temperature 0.8、評価0.5、60%勝率でbank追加、70%でactive昇格という例がある。
- **候補:** 日・phase単位のHierarchical RL。
- **候補:** 作業実行は決定論的にし、経済計画だけを学習する。
- **候補:** simulatorで少数の完全な代替戦略を分岐評価し、value targetを生成する。
- **判断:** RLはexecutorと評価基盤が完成した後。最初はマクロaction selectorに限定する。

マクロaction候補:

```text
KEEP_PLAN
INCREASE_CARROT
INCREASE_TOMATO
ADD_GOOSE
ADD_COW
ADD_SHEEP
BUY_LAND
HOLD_INVENTORY
LIQUIDATE
```

## 現在の優先実験

| 優先度 | 仮説 | 主な評価指標 | 状態 |
|---:|---|---|---|
| 1 | paired evaluationでseat偏りを除ける | paired win rate | 未着手 |
| 2 | 永続taskで作業中断を減らせる | 逃亡、歩行、no-op | 未着手 |
| 3 | 給餌済みCAREだけを行う | 生産量、勝率 | 未着手 |
| 4 | 生産2日前以内の施肥が効率的 | 肥料当たり増産量 | 未着手 |
| 5 | day 28以降の清算でcashが増える | 未売却在庫、勝率 | 未着手 |
| 6 | Shop適応で不足価格を取れる | 実約定単価、勝率 | 未着手 |
| 7 | 相手売却圧力で販売時期を変える | price impact、勝率 | 未着手 |

## 実験ログ用テンプレート

```markdown
### EXP-XXX: 実験名

- 日付:
- 変更:
- 仮説:
- 比較対象:
- seed:
- opponent panel:
- 試合数:
- paired win rate:
- 平均cash差:
- 副作用:
- 結論: 採用 / 棄却 / 保留
- 次の実験:
```

## 参照Discussion

- [仕様差と運営回答](../discussions/topics/732450-crucial-information-for-starters-and-organizers-documentation-vs-engine-discrepa.md)
- [Town・Shopのバランス変更](../discussions/topics/733431-balance-changes.md)
- [Carrot・Tomato・Eggの価格変更](../discussions/topics/735311-small-balance-change.md)
- [提出とrating収束](../discussions/topics/736219-1st-place-previously-submission-strategy-for-beginners.md)
- [PPOによる80K cash](../discussions/topics/738619-learnings-from-ppo-to-80k-terminal-cash.md)
- [Replay測定pipeline](../discussions/topics/739273-i-came-here-to-build-a-farming-agent-i-ended-up-building-a-replay-measurement-pi.md)
- [注文と実約定の差](../discussions/topics/739972-from-replay-orders-to-actual-trades-a-cash-flow-breakdown.md)
- [3層型エージェント](../discussions/topics/740055-a-three-layer-brain-for-kaggriculture.md)
- [既知tapeとの一致率](../discussions/topics/740437-your-opponents-are-probably-replaying-the-same-tapes-you-are-i-measured-it.md)
- [RLの構成と評価上の注意](../discussions/topics/740792-how-are-people-making-rl-work-in-kaggriculture.md)
- [実際に改善した施策](../discussions/topics/740847-my-journey-so-far-mechanics-breakdowns-and-what-s-actually-working.md)

