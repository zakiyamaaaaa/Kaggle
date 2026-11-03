# 調査結果からの実験バックログ

ここでは、直近3日間の調査結果を現在のローカル実装へ接続する順序を記録する。まだ実装・提出はしていない。

## P0: 既存主力を壊さない単一layer比較

### A. Market queue cleanup

対象: V48 / First in Line / Pipe15のEffective Queue

最小実装:

- `SELL` quantityが0または現在のshedで実行不能なorderを除去。
- 同一productのcash saleをmerge。
- purchase、positive wheat/fertilizer order、fixed route orderは並べ替え対象から除外。
- 空いた早いslotに、現stepで全量実行できるcash saleだけを移す。

検証:

- candidate vs candidate+queueの同一seed、両seat、同じshop draw。
- `public_salem`だけでなくV47/V52/independent_workersを含める。
- `points_delta`を採用指標、margin・failed orders・shed overflowを診断値にする。

### B. Sheep day-11 / late-season service

対象: V50/V52

最小実装:

- first-two-shopにyarnが含まれ、cashとday 12までの予定購入が成立する場合のみday 11へ羊投入。
- day 28以降、season内に売却可能なproductionがない羊のfeed/care/hireを止める。
- 非収穫日は6頭のfeed/careが1人で間に合う場合、2人目の羊handを雇わない。

検証:

- yarn有り／無しを別world familyとして評価。
- V50/V52の主張値を再現するのではなく、現candidateとの差分でpaired比較。
- sheepのfood shortage、missed care、last-day unsold woolを必ずログ化。

### C. Public sale-stream forecast

対象: V52/V53

最小実装:

- observationのmarket inventory差分、town draw、自己の実行SELLから相手の実行済みpremium saleを推定。
- まず統計的な簡易特徴（直近の同一product sale、shop pair、turn distance）だけで分岐する。
- 圧縮された大規模blobは最初の実験では使わない。

検証:

- 予測が外れた場合にsaleを前倒ししないfallbackを持つ。
- opponentの実行scoreがrecorded scoreの95%未満になるreplayは、counterfactual勝利の根拠から除外。
- V53のように、まず4〜8 worldのmirror fixtureでaction parityを確認し、その後held-outへ進む。

## P1: 独立方策の改善仮説

### D. Tile-day / worker-action crop score

作物候補のスコアを次のように分解し、現在のpriorityに導入する。

```text
expected_sale_value
- seed_cost
- fertilizer_cost
- expected_worker_actions * marginal_worker_cost
- cash_reserve_penalty
- late_harvest_penalty
--------------------------------
occupied_tile_days と worker_action で正規化
```

visible-priceの判断は現在の価格だけに限定し、seed購入とplant actionを同じdecision objectから生成する。将来価格を覗くoracleは使わない。

### E. Macro plan selector

RL Discussionの知見を、まずはRLなしで再現する。

- phaseごとに `KEEP_PLAN / INCREASE_CARROT / ADD_SHEEP / SELL_EARLY` などのmacro planを列挙。
- local simulatorで1 phase先を分岐実行し、value modelまたはpaired win estimateで選ぶ。
- その後、必要ならBC replayからmacro policyを学習する。

## 採用ゲート

新しい候補は次を満たさない限り主力へ昇格しない。

- clean runが全試合完走する。
- 旧版と同一seed・同一seatでpaired比較できる。
- 新規未使用seedで結果を確認する。
- 少なくとも3つのstrategy familyを含む。
- 勝率の改善がmargin改善だけでなくpointsにも出る。
- 失敗した相手・world family・engine差分を記録する。

公開ノートは勝ち数が大きくても、mirror・同系統相手・固定replayだけなら採用根拠としては弱い。特にopening size、sale lookahead、shop依存の羊比率は、相手のmetaが変わると反転し得るため、値を固定コピーせずablationで扱う。
