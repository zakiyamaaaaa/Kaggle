# Kaggriculture 今後の改善戦略

- 策定日: 2026-09-21
- 締切: 2026-09-30 23:59 UTC（2026-10-01 08:59 JST）
- 現在の基準: One More Wheat（submission `56409440`）

## 結論

今後は、One More Wheatをそのまま保存する安定枠と、One More Wheatに小さな適応層を
追加する挑戦枠の二本立てで進める。公開ratingは変動が大きく、提出直後の値を開発の
目的関数にしない。ローカルの同一seed・両seat対戦で変更を選別し、最終的に最新2提出を
「基準版」と「多様性のある改善版」で構成する。

生actionを学ぶRLや独自executorの全面改修は、残り期間の主経路にしない。現在の強い
固定routeを保持し、opening、市場タイミング、終盤回収、相手適応を一要素ずつ改善する。

## 現在地

- One More WheatはSalemに48勝0敗。
- 2950 PeakとTriad Counterにも各16勝0敗。
- ただし平均cash差は、2950 Peakに+1,855、Triad Counterに+1,513と小さい。
- 公開評価はまだ1試合、1勝0敗、rating 706.1であり、実力推定には不足している。
- One More WheatはMetav4/Pipe16系の固定route、市場race、day-11 sheep、終盤清算を
  既に含む。全面的な書き換えは回帰リスクが大きい。

したがって、次の改善余地は「大幅な生産量増加」よりも、同系統との僅差を勝ち切る
市場順序、相手が異なる場合のroute選択、終盤の取りこぼし削減にある。

## 目標

1. 最終評価用に、検証済みの強い2提出を確保する。
2. One More Wheatと同系統の相手だけでなく、家畜偏重、作物偏重、市場counterに対して
   勝率を落とさない。
3. 変更の効果をcash差ではなく、まず勝敗で確認する。cash差は診断用とする。
4. 最新2枠を未検証実験で埋めない。

## 開発トラック

### Track A: 基準版を凍結する

提出済みOne More Wheatの`main.py`とtarをbyte-for-byte保存し、コードを変更しない。
全実験の比較対象、障害時の復帰候補、最終2枠の一方として使う。

### Track B: 小さな改善版を作る

優先順位は次の通り。

1. **終盤回収・清算**
   - step 712以降のworker在庫、Shed空き、帰還可能stepを観測して、回収できる商品だけを
     安全に追加回収する。
   - 最終SELLの順序、注文上限、同stepのunit action後の在庫を検証する。
   - 2950 Peakのterminal rescueから、独立した安全層だけをablationする。

2. **観測ベースの市場front-run**
   - 固定された相手tapeの完全一致を前提にせず、市場inventoryの差分と相手盤面の
     収穫状況から、次のMILK/WOOL/STRAWBERRY/MELON売却圧力を推定する。
   - 先売り量に上限を置き、自分の将来routeに必要な在庫は保護する。
   - Triad Counter由来の発想を使うが、特定cloneだけを狙う条件は採用しない。

3. **route選択の多様化**
   - opening自体はOne More Wheatを維持する。
   - step 2、day 6、day 27の既存router判定に、観測可能な市場在庫、価格、相手の
     作物・家畜構成を少数の離散条件として加える。
   - 最初は2 routeまでとし、条件を増やしすぎない。

4. **temporary wheatの堅牢化**
   - One More Wheatの主要差分である一時WHEATについて、雑草、購入失敗、worker位置ずれ
     が起きた場合に後続pastureを遅らせない撤退条件を加える。
   - 正常系のaction列は一切変えず、異常観測時だけ介入する。

### Track C: 多様性枠を用意する

One More Wheat派生が未知metaに同時に負けるリスクを避けるため、最終候補には異なる
市場挙動を持つ版も残す。候補はTriad型の観測counterか、2950 Peak型の終盤投資を
取り込んだ版とする。ただし、One More Wheatとの直接対戦だけに勝つcounterは採用しない。

## 評価panel

最低限、次を固定fingerprintで評価する。

1. One More Wheat原版
2. 2950 Peak
3. Triad Counter
4. public Salem 2900
5. candidate-early-milk
6. 市場介入が弱い単純agent

可能なら、公開Replayから挙動の異なる上位相手を2本追加する。各seedは必ずseatを交換し、
同一seed・同一相手で原版と変更版を比較する。

## Gate

| Gate | 規模 | 通過条件 |
|---|---:|---|
| Smoke | 8 seeds × 2 seats × 2相手 | ERROR/INVALID/TIMEOUT 0、正常系action回帰なし |
| Screen | 32 seeds × 2 seats × 6相手 | panel全体で原版以上、主要相手で勝率低下なし |
| Validation | 128 seeds × 2 seats × 6相手 | paired score改善、seed bootstrap 95% CI下限が概ね0以上 |
| Holdout | 256未閲覧seeds × 2 seats × 6相手 | 最終候補のみ1回、原版に明確な回帰なし |

主指標は`win + 0.5 * draw`。cash差、商品別売上、終端在庫、overflow、silent no-op、
action時間は原因診断に使う。Kaggle ratingは採用条件に含めない。

## 最初の実験

| ID | 変更 | 狙い | 中止条件 |
|---|---|---|---|
| OMW-001 | 2950 Peakのterminal rescueを安全層として移植 | 終盤の未回収在庫削減 | 正常系action変更、処理時間超過 |
| OMW-002 | inventory差分によるWOOL/MILK先売り | 同系統市場raceの僅差改善 | 非clone相手で勝率低下 |
| OMW-003 | day 6 routeを相手の家畜構成で2分岐 | meta外への耐性 | panel平均だけ改善し主要相手が悪化 |
| OMW-004 | temporary wheat失敗時の撤退guard | live環境のずれ耐性 | 正常系に介入する |
| OMW-005 | OMW-001と採用済み市場層だけを統合 | 最終challenger | 単体効果の和を下回る |

一度に複数の変更を混ぜない。各実験は原版との差分を小さくし、採用されなかった変更は
統合版へ持ち込まない。

### OMW-002 初期実装状況（2026-09-21）

`experiments/omw-observed-front-run-v1/` に、公開市場inventory差分から相手の実売却を
復元し、安定した大量売却周期を検出した場合だけ予定売却を1〜2 turn前倒しする候補を
実装した。56試合の比較は全件正常完走。2950 Peakには平均差+12.25だった一方、
Triad Counterで-53.88、Salemで-59.38となり、勝敗の改善はなかった。

仕組みは発火し、先売り分を将来SELLから相殺できているが、現設定は未昇格とする。
次版では「予測できたら売る」だけでなく、予想価格下落額が早売りの機会損失を上回る
場合だけ発火する価値ゲートを追加する。

### OMW-002 需要控除版（2026-09-21）

`experiments/omw-net-stock-sellnow-v2/` に、相手の公開盤面から復元した推定売却可能在庫から、
こちらの次回予定売却までの町需要を差し引く版を実装した。控除後も12 units以上残り、
価格モデル上の損失が正の場合だけ、24 turn以内の予定売却を現在へ移す。前倒し数量は
既存の売却債務ledgerへ記録し、将来の二重売却を防ぐ。

独立seed各32戦では、原版に対するscoreがOne More Wheat鏡で0.5000→0.7500、
Triad Counterで0.8750→0.9375、2950 Peakは0.96875を維持した。Salem early-milkと
local candidateは双方1.0000を維持し、別seedのpublic Salem 16戦も全勝。実行エラーは0。
Screen候補として採用し、より大規模なValidation/Holdoutは提出セッションと分離して行う。

自己完結アーカイブは`submissions/omw-net-stock-sellnow-v2.tar.gz`。開発版とのparity 8戦は
全引分・平均差0で、manifestは`built_not_submitted`。この作業セッションでは提出していない。

### OMW-002 Validation / Holdout（2026-09-21）

Screen後に設定を固定し、自己完結版と原版を同一seed・両seat・6相手で比較した。
Validationは128 seed・1方策あたり1,536試合で、scoreは0.931315対0.882161、
paired差+0.049154、seed bootstrap 95%区間[+0.025065, +0.073893]。未使用Holdoutは
256 seed・1方策あたり3,072試合で、0.932617対0.888997、差+0.043620、
95%区間[+0.027669, +0.059896]。両段階とも実行エラー0だった。

HoldoutではOne More Wheat鏡が0.500000→0.718750、2950 Peakが0.912109→0.933594、
Triad Counterが0.921875→0.943359。Salem、early-milk、単純baselineは1.000000を維持。
ValidationとHoldoutの採用gateを通過したため、最終challengerとして提出可能と判定する。
詳細は`experiments/omw-net-stock-sellnow-v2/results-summary.json`に保存した。

## 公開評価の扱い

- One More Wheatの公開episodeは開発を止めずに観察する。
- 10、30、60 public episodesを目安にrating、勝敗、相手、seatをsnapshot保存する。
- 30試合未満のrating差で方針を変えない。
- 60試合も公式の収束点ではなく、単なる観察目安とする。
- 敗戦Replayは、相手family、売却衝突、終端在庫、route逸脱の4分類で診断する。

## 提出計画

1. 検証中はローカルだけで回し、Screen未通過版を提出しない。
2. Validationを通過したchallengerを1本だけ提出する。
3. 提出後も短期ratingで原版を捨てず、Replayをローカルpanelへ追加する。
4. 締切前日に最新2提出を確認する。
5. 最終2枠は原則として、再提出したOne More Wheat基準版と、Holdout通過challengerにする。
6. challengerが原版を超えなければ、One More Wheatと、最も多様で回帰の少ない既存強豪版を
   最新2枠に置く。弱い実験版を残さない。

## 日程

- 9/21–9/22: 評価panel固定、OMW-001終盤回収。
- 9/23–9/24: OMW-002市場front-run。
- 9/25–9/26: OMW-003 route分岐、公開敗戦Replayの反映。
- 9/27: 単体採用版の統合とValidation。
- 9/28: 未閲覧Holdout、処理時間・bundle検査。
- 9/29: challenger提出、実行確認。
- 9/30: 最新2枠、ハッシュ、status、episode errorを最終確認。新しい機能追加はしない。

## 判断基準

最も重要なのは、One More Wheatの高い既知性能を失わず、未知相手に対する敗北確率を
下げることである。局所cash差が増えても勝敗が改善しない変更、特定公開tapeだけを狙う
変更、正常系routeを広く変更する機能は採用しない。
