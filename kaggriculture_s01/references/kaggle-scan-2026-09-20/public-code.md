# 公開コード調査

## 調査範囲

Kaggricultureに紐づく公開コードを `kaggle kernels list --competition kaggriculture` で取得し、日本時間の対象期間に対応する49件を確認した。著者の説明が具体的で、現在のローカル実装との差分または評価方法が参考になる20件をKaggle CLIでpullした。取得元はこのディレクトリの [`public-code/`](public-code/)。

## 最優先候補

### V53 — Opening Signature and Current-Meta Sale Streams

- 出典: [ahmedberatozer/kaggriculture-v53-opening-signature](https://www.kaggle.com/code/ahmedberatozer/kaggriculture-v53-opening-signature)
- 取得: [`public-code/ahmedberatozer__kaggriculture-v53-opening-signature/`](public-code/ahmedberatozer__kaggriculture-v53-opening-signature/)
- 内容: V52を維持し、step 2の公開wheat inventory変化でV52型openingか新型openingかを判別し、sale-forecast libraryを切り替える。Pipe16とDmitrii系の公開sale streamを追加。
- 著者記載の評価: V52との60-world pooled confirmationで `302/180/118` 対 `273/209/118`、points `+0.048`、margin `+$160.6`、own cash `+$53.4`。4つのV52-like mirrorでは719 actionsが完全一致。runtime最大20.22ms（著者環境）。
- 判断: 最新の公開派生で、現在のcandidateにない「公開inventory差分→forecast分岐」の最小候補。まずはV53をそのまま移植せず、forecast分岐だけを独立実験にする。

### V52 — Lean Flock, Yarn Route

- 出典: [ahmedberatozer/kaggriculture-v52-lean-flock-yarn-route](https://www.kaggle.com/code/ahmedberatozer/kaggriculture-v52-lean-flock-yarn-route)
- 取得: [`public-code/ahmedberatozer__kaggriculture-v52-lean-flock-yarn-route/`](public-code/ahmedberatozer__kaggriculture-v52-lean-flock-yarn-route/)
- 差分:
  - 6頭羊の非収穫日に、1人でfeed/careできるなら2人目（hire #12/#13、$144/$233）を雇わない。
  - `CARROT2` feed guardを2日→1日、FERT開始をday 16→14、SHEDROOMをhours 21–23 / margin 8、ORDERPRI2 slot marginを50→20。
  - V219 tomato crewをday 19/21/23にskip。
  - yarn店を含むfirst-two-shop pairでは、6 cows + 11 sheepのYARN routeを選択。
  - 公開market inventory差分から相手のpremium saleを復元し、48 turns以内の先売りを行う。
- 著者記載の評価: V50比1,280 gamesでpoints `+0.1094`、paired margin `+$1,314`、zero errors。YARN worlds 800 gamesでpoints `+0.2400`、margin `+$5,058`。
- 判断: 4つの小さな差分へ分解しやすく、特にhire #12/#13、day 11/29 sheep、ORDERPRI2は、現在の独立方策・Salem主力とは別familyの強い候補。

### The Metav4 Farm: Submission v13

- 出典: [thomastschinkel/the-metav4-farm-submission-v13](https://www.kaggle.com/code/thomastschinkel/the-metav4-farm-submission-v13)
- 取得: [`public-code/thomastschinkel__the-metav4-farm-submission-v13/`](public-code/thomastschinkel__the-metav4-farm-submission-v13/)
- 内容: recorded routeを基礎に、RACE/RACEPX、PREDICT/PREDICT2、COURIER/OVERFLOW、SHEDROOM、CARROT2、FERT、ORDERPRI2、CAPHARV、羊のday 11/終盤制御、tomato crew skipなどを積む。
- 著者記載の評価: 1,200 top-30 replaysから222,000+ sale eventsを使ったPREDICT library。Metav4 holdoutで `143 vs 135`（`+$170` margin）。The 2945 Farmには40–0。
- 重要な限界: published public botsには強いが、上位private teamはday 12–18でroute replayをやめ、adaptive plannerへ切り替えるという分析。greedy LP schedulerは `-$4.4k〜-$16.8k`、full tomato projectは `-$945〜-$2.3k` と失敗。
- 判断: 現在の主力にない市場・worker微修正の基準実装として最重要。ただし全routeを取り込むのではなく、V52の各layerと重複を照合する。

### Pipe16 — Idle Workers on The Metav4 Farm

- 出典: [nathanjacob/kaggriculture-pipe16-idle-workers](https://www.kaggle.com/code/nathanjacob/kaggriculture-pipe16-idle-workers)
- 取得: [`public-code/nathanjacob__kaggriculture-pipe16-idle-workers/`](public-code/nathanjacob__kaggriculture-pipe16-idle-workers/)
- 内容: day 0–2にPASSしているidle handを、一時WHEATの `BUY_SEED → PLANT/WATER → HARVEST → SELL` に振り替える。元のopening round-tripは残し、day 3前に通常routeへ戻す。
- 著者記載の評価: v13に対して全体 `318–32`（7 opponents × 50 games）。一方、Dmitrii系には78%で、相手が同じworker trickを使う場合の優位性は落ちる。
- 判断: 現在の独立方策でworkerを既に使うため、そのままの移植ではなく、Salem主力に対するday 0–2のidle action差分として検証する。採用は必ず複数strategy familyで判定する。

## 市場注文・売却順序

### V48 — Clear the Queue

- 出典: [ahmedberatozer/kaggriculture-v48-clear-the-queue](https://www.kaggle.com/code/ahmedberatozer/kaggriculture-v48-clear-the-queue)
- 取得: [`public-code/ahmedberatozer__kaggriculture-v48-clear-the-queue/`](public-code/ahmedberatozer__kaggriculture-v48-clear-the-queue/)
- 内容: dead SELLを除去し、同一cash productのSELLをmerge、空いた早いslotへ実行可能なcash saleを詰める。positive wheat/fertilizer sale、purchase等の固定orderは保持。
- 著者記載の評価: 3 worlds × both seats × 6 opponentsの72 gamesでV48が36/0/0、V47が30/0/6。
- 判断: 現在の `independent_agent.py` のmarket ordersはquantity順の単純構成なので、最小のqueue experimentとして取り入れやすい。

### First in Line — Stock Into Income

- 出典: [alperen5252525/kaggriculture-first-in-line-stock-into-income](https://www.kaggle.com/code/alperen5252525/kaggriculture-first-in-line-stock-into-income)
- 取得: [`public-code/alperen5252525__kaggriculture-first-in-line-stock-into-income/`](public-code/alperen5252525__kaggriculture-first-in-line-stock-into-income/)
- 内容: V48 coreに、cash saleのqueue cleanup、pre-dawn storage pressure、sale lookaheadを追加。`_ADV_LOOK = 8`。
- 著者記載の評価: selected configurationは144 gamesで `136/8/0`、mean margin `+$7,608.3`。V48に対しては限定panelの結果であり、公開engine差分も4/16 replayで残ると明記。
- 判断: 実装よりも「同じ総販売量でもqueue positionで差が出る」という診断が有用。V48 queueとsale lookaheadを分離して検証する。

### Demand-Preserving Turn Sale Timing

- 出典: [tetsutani/demand-preserving-turn-sale-timing](https://www.kaggle.com/code/tetsutani/demand-preserving-turn-sale-timing)
- 取得: [`public-code/tetsutani__demand-preserving-turn-sale-timing/`](public-code/tetsutani__demand-preserving-turn-sale-timing/)
- 内容: 公開stateのみで、production/race/storage/herd/capital/repair/compaction/terminalを持つ。openingはcash guard下でstep 1に22 WHEAT buy、step 2に同量resale。
- 判断: 22-unit値そのものは相手のopeningに依存するため固定採用しない。market lockstep、public-stateのrace handling、単一layerを変更して全season QAする姿勢が参考になる。

### Beat V48 100-0: Your Herd Is Decided on Day 6

- 出典: [shiiin9/beat-v48-100-0-your-herd-is-decided-on-day-6](https://www.kaggle.com/code/shiiin9/beat-v48-100-0-your-herd-is-decided-on-day-6)
- 取得: [`public-code/shiiin9__beat-v48-100-0-your-herd-is-decided-on-day-6/`](public-code/shiiin9__beat-v48-100-0-your-herd-is-decided-on-day-6/)
- 内容: layer Dは全SELL orderのlockstep応答順を探索し、layer O-Bはday 9時点で残りshop drawを列挙して、期待値ではなく95%のtownで勝つ場合だけcow/sheepを交換。
- 著者記載の評価: V48 mirror 100 gamesで100–0、layer O-B追加効果は+204 coins/game。固定勝敗だけでなく、変更候補を除いたpaired比較を強調。
- 判断: animal choiceを「平均cash最大」ではなく「win probability制約付き」で選ぶ考え方が有用。ただしshop distributionと価格表の再検証が必要。

### V47 — Reactive Market Coordination

- 出典: [ahmedberatozer/kaggriculture-v47-reactive-market-coordination](https://www.kaggle.com/code/ahmedberatozer/kaggriculture-v47-reactive-market-coordination)
- 取得: [`public-code/ahmedberatozer__kaggriculture-v47-reactive-market-coordination/`](public-code/ahmedberatozer__kaggriculture-v47-reactive-market-coordination/)
- 内容: V46 route/safetyに、public observationからclone-like rival queueを仮定したorder coordination、sale cache、resource reuseを追加。
- 著者記載の評価: 32 worlds × both seats × 8 responding policiesで503/9/0、V46は341/113/58。
- 判断: current candidateの別family opponentとして使う価値が高い。全sourceの採用ではなく、queue/order layerの対戦相手として登録する方が安全。

### Pipe15 — Two Layers That Beat The 2945 Farm

- 出典: [nathanjacob/kaggriculture-pipe15-two-layers](https://www.kaggle.com/code/nathanjacob/kaggriculture-pipe15-two-layers)
- 取得: [`public-code/nathanjacob__kaggriculture-pipe15-two-layers/`](public-code/nathanjacob__kaggriculture-pipe15-two-layers/)
- 内容: idle-worker temporary wheat（Dmitrii）とEffective Queue（lynnsakurai）をthin layerとしてstack。
- 著者記載の評価: 10-agent gauntletで346 wins / 52 losses。ただしtetsutani/v49へのregressionも明記され、公開fieldに特化した可能性がある。
- 判断: layer抽出の対象にはするが、採用候補ではなくstress opponentとして使う。

## 小さな実験・評価方法として有用

### V53以外の追加取得

- [V50 Early Yarn Commit](https://www.kaggle.com/code/ahmedberatozer/kaggriculture-v50-early-yarn-commit): [`public-code/ahmedberatozer__kaggriculture-v50-early-yarn-commit/`](public-code/ahmedberatozer__kaggriculture-v50-early-yarn-commit/)。day 11の羊投入、day 28–29のfeed/care停止。yarn worldsで80/0/0、fresh yarn 40 worldsでmargin `+$2,526` と著者記載。
- [The 2945 Farm](https://www.kaggle.com/code/thomastschinkel/the-2945-farm-96-vs-the-top-10-public-bots): [`public-code/thomastschinkel__the-2945-farm-96-vs-the-top-10-public-bots/`](public-code/thomastschinkel__the-2945-farm-96-vs-the-top-10-public-bots/)。公開top-10に519–21、reactive botsに645/680と著者記載。ただしprivate top teamsにはday 12–18以降で負ける分析が重要。
- [Market Rhythm — Sale Policy](https://www.kaggle.com/code/alperen5252525/kaggriculture-market-rhythm-sale-policy): [`public-code/alperen5252525__kaggriculture-market-rhythm-sale-policy/`](public-code/alperen5252525__kaggriculture-market-rhythm-sale-policy/)。24-turn sale advanceとbounded adjacent-exchange search。paired bootstrap CIが `-19.0〜+62.7` で、改善を断定していない点が評価設計として有用。
- [Beyond 48-0](https://www.kaggle.com/code/jaxa623/2780-beyond-48-0-128-128-worlds-with-95-cis): [`public-code/jaxa623__2780-beyond-48-0-128-128-worlds-with-95-cis/`](public-code/jaxa623__2780-beyond-48-0-128-128-worlds-with-95-cis/)。market lockstep、front-loading、2-turn sale advance、reservation horizon 24。8 seedの16–0ではなく、64 independent worldsとbootstrap CI、worst worldを見る評価作法が有用。
- [The Melon Threshold and the Step-1 Squeeze](https://www.kaggle.com/code/goodpjw2008/kaggriculture-melon-threshold-squeeze-2749): [`public-code/goodpjw2008__kaggriculture-melon-threshold-squeeze-2749/`](public-code/goodpjw2008__kaggriculture-melon-threshold-squeeze-2749/)。step 0/1のcash pressureがstep 17のmelon seed購入を変えるという診断。相手opening依存かつraceが速く、固定値の移植は危険。
- [Visible-Price Switch Lab](https://www.kaggle.com/code/prvsiyan/kaggriculture-visible-price-switch-lab): [`public-code/prvsiyan__kaggriculture-visible-price-switch-lab/`](public-code/prvsiyan__kaggriculture-visible-price-switch-lab/)。visible price×documented yieldでWHEAT/CARROTを切り替える小さな例。future price/hidden stateを使わず、seed purchaseとplant actionを一貫させる監査方法が参考。
- [Game-Theoretic Master](https://www.kaggle.com/code/guruprasaathas111/game-theoretic-master-discrete-optimization): [`public-code/guruprasaathas111__game-theoretic-master-discrete-optimization/`](public-code/guruprasaathas111__game-theoretic-master-discrete-optimization/)。数理モデルの説明は広いが、現時点では「新しい独立familyの対戦相手」として扱い、主張されたscoreは採用根拠にしない。

## 取得したが、今回の優先度が低いもの

- `sunil123kumar/kaggriculture-v8`
- `haideptry/demystifying-2900-meta-reflex-engine-and-bot`
- `laveshjadon/kagriculture-winning-notebook`
- `prvsiyan/kaggriculture-visible-price-switch-lab` 以外の短い教材系ノート

これらは取得済みだが、今回のレポートで優先する具体的な差分・再現可能な評価値が少ないため、まず上記候補のablationに集中する。

一覧だけ確認してNotebookを取得していないものには、`sunil123kumar/kaggriculture-top-10-public-bots` と `anhadmahajan06/kaggriculture-autonomous-ai-farming-agent` などがある。

## ライセンスと再利用

多くの取得NotebookはApache-2.0とupstream attributionを明記しているが、移植時は各Notebookの`main.py`先頭のattribution/licenseを残す。公開Notebookに含まれる圧縮blobは、内容を確認せずそのまま本番へ組み込まない。
