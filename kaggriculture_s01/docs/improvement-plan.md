# Kaggriculture 改善計画

> 2026-09-20の現在地とCNN／最適化の比較は [方針レビュー](strategy-review-2026-09-20.md) を参照。この文書は9/18時点の計画を保持しており、以下の「現状」には実装前の記述が含まれる。

- 作成日: 2026-09-18
- 対象環境: `kaggle-environments==1.32.7`
- 目標: 公開強豪に対して再現性のある改善を積み上げ、未知戦略にも崩れにくい提出を作る

## 結論

開発順は次の通りとする。

1. 公開強豪をArenaの基準相手として動かす
2. paired評価と計測を完成させる
3. 決定論的executorで作業損失をなくす
4. 固定生産計画を探索する
5. Shop・市場・相手に適応する
6. 最後にマクロ戦略選択だけを探索・学習する

生の719-step actionを学ぶend-to-end RLは当面行わない。作業実行はルールベースで固定し、探索対象を少数の経済パラメータとマクロactionに限定する。

## 現状とボトルネック

- Arenaはseed固定、seat交換、並列実行、resume、CSV集計まで動作済み。
- `baseline` と `candidate` は現時点で同じPASS方策であり、戦略評価の基準にはならない。
- `submissions/public-salem-2900/main.py` に公開強豪の取得済みコードがあるが、Arena registryには未登録。
- Arenaは最終cashと勝敗を記録するが、期限切れ、no-op、商品別生産・実約定などの診断値が不足している。
- 単純Eloは試合順に依存するため、候補の昇格判定には使わない。
- resumeはagent名だけを識別しており、同名agentのコード変更後に古い結果を再利用する危険がある。

## 評価設計

### seed分割

| 用途 | seed | 扱い |
|---|---:|---|
| 開発 | 10,000–10,999 | 日常的なデバッグと探索に使用 |
| validation | 20,000–20,999 | 仮説ごとの採否判定に使用 |
| holdout | 90,000–90,999 | 提出候補が決まるまで結果を見ない |

各seedは必ずseat 0/1を交換して2試合実行し、2試合のcash差の平均を1つのpaired sampleとして扱う。

### opponent panel

最低限、次の4系統を含める。

1. 固定した単純ルールベース
2. `public-salem-2900`
3. 取得済み公開tapeのうち挙動が異なる2–3本
4. 過去に昇格した自分のcheckpoint

公開tapeだけに最適化しない。Shop系列が元Replayから維持された試合と変化した試合は別集計する。

### 段階的な試合数

| Gate | 規模 | 目的 |
|---|---:|---|
| Smoke | 10 seeds × 2 seats × 1 opponent | 例外、INVALID、明白な退行を検出 |
| Screen | 50 seeds × 2 seats × 2 opponents | 仮説の早期選別 |
| Validation | 200 seeds × 2 seats × panel全体 | candidate昇格判定 |
| Holdout | 300 seeds × 2 seats × panel全体 | 提出候補の最終確認 |

### 昇格条件

candidateは次をすべて満たしたときだけincumbentへ昇格する。

- `ERROR / INVALID / TIMEOUT == 0`
- panel全体のpaired scoreがincumbentを上回る
- paired cash差の95% bootstrap信頼区間の下限が0以上
- 主要な各opponentに対する勝率低下が3ポイント以内
- 終了時未売却在庫、動物逃亡、作業期限切れが悪化していない
- holdoutはvalidationで採用判断した後、一度だけ確認する

引き分けが多い場合は勝率だけでなくpaired cash差を一次スクリーニングに使う。ただし最終判断は対戦scoreを優先する。

## 実装ロードマップ

### Phase 0: 信頼できる基準相手を作る（9/18–9/19）

- 任意の単一ファイル提出をprocess-safeに読み込めるregistryを追加する。
- `public-salem-2900` をArenaへ登録する。
- agent sourceのSHA-256をmanifestへ保存し、コード変更時は古いresume結果を拒否する。
- 同一agentのself-playでもモジュールglobalが混ざらないよう、必要ならplayerごとにmoduleを分離ロードする。
- 公開Replayを抽出する場合は、自分のReplayでaction一致率100%の回帰テストを必須にする。

完了条件: `candidate vs public-salem-2900` を100 paired seedsで完走し、再実行で結果が一致する。

### Phase 1: 診断可能なArenaへ拡張（9/19–9/20）

- paired sample単位の集計とbootstrap CIを追加する。
- 商品別に生産、収穫、注文、実約定量、売上、平均価格を記録する。
- 歩行、PASS、PICKUP、作業、推定silent no-opを記録する。
- 水切れ、給餌切れ、動物逃亡、Shed overflow、終了時在庫を記録する。
- Shop系列と、Replay由来相手では元系列維持/変化を記録する。
- 実験ごとに仮説、agent fingerprint、seed範囲、相手panel、結果をmanifestへ残す。

完了条件: 敗因を最終cashだけでなく作業損失・在庫・市場のどこで発生したか説明できる。

### Phase 2: executorを完成させる（9/20–9/23）

エージェントを3層へ分ける。

```text
Strategy: 日・phaseごとの生産量、土地、hands、売却方針
Scheduler: 期限、損失、距離からtaskを割り当てる
Executor: 実観測を正として複数step taskを完遂する
```

優先実験:

1. PLANT直後の同日WATERを保証
2. `PICKUP WHEAT → 移動 → FEED` を中断しない
3. 給餌済み動物だけCARE
4. 生産日まで2日以内のtileだけFERTILIZE
5. HARVEST後のDROPまでを永続task化
6. Shed overflow前の売却・回収制御
7. 必要作業量からhands数を日ごとに決定

完了条件: 100 validation seedsで逃亡、期限切れ、意図しないno-opをほぼ0にし、各変更のcash寄与を分離計測できる。

### Phase 3: 固定経済計画を探索（9/22–9/25）

executorを固定し、次だけを探索する。

- 作物・動物の構成と配置数
- 植付・配置日
- 土地購入日
- 日別hands数
- 商品別売却reserve
- 清算開始日

初期探索はgrid/random searchで十分。1ゲームの最終cashではなく、opponent panelに対するpaired scoreを目的関数にする。探索seedと採否seedを分け、上位設定をvalidationへ送る。

優先仮説:

- day 28以降はreserveを解除して全在庫を現金化
- Wheat過剰生産を抑え、飼料必要量＋安全余裕に合わせる
- worker追加は期限付きtaskが未処理になる日だけ行う
- Strawberry、Milk、Woolの比率を公開強豪との差分から探索する

完了条件: 公開強豪に対して勝てる固定incumbentを1つ確立する。

### Phase 4: 状態適応を追加（9/24–9/27）

固定計画から一度に1要素だけ適応化する。

1. Shop構成と市場在庫からCARROT/TOMATO/EGG不足を検出
2. 残り日数と予測価格を含む生産切替
3. 相手盤面から商品別将来生産量を推定
4. 相手の収穫量から売却圧力を推定し、大量売却の衝突を避ける
5. 自分と相手の推定最終資産差からHOLD/LIQUIDATEを切り替える

複雑な相手family分類は後回しにする。まず商品別供給予測で価値が出るか確認する。

完了条件: 固定incumbentよりpanel全体で改善し、特定tapeだけに依存していない。

### Phase 5: 提出安定化（9/27–9/30）

- 単一`main.py`へbundleし、外部ファイル参照がないことを検査する。
- Kaggle相当のクリーン環境でimportと1試合を確認する。
- action時間のp95/max、ファイルサイズ、依存関係を検査する。
- holdout Gateを1回だけ実行する。
- incumbentと多様性のあるchallengerを残し、LBの短期変動だけで差し替えない。
- 提出後は最低30試合程度まで観察し、Replayを診断データとして保存する。

## RL・探索の位置づけ

時間が残った場合だけ、次のマクロaction selectorを試す。

```text
KEEP_PLAN, INCREASE_CARROT, INCREASE_TOMATO,
ADD_GOOSE, ADD_COW, ADD_SHEEP,
BUY_LAND, HOLD_INVENTORY, LIQUIDATE
```

各日またはphaseごとに1つを選び、低レベル操作は同じexecutorへ渡す。学習より先に、simulatorで各候補を分岐実行してvalue targetを作る。flat PPO、全workerの生action学習、単一相手へのself-playは行わない。

## 最初の5実験

| ID | 変更 | 比較 | 主指標 |
|---|---|---|---|
| EXP-001 | `public-salem-2900` をArena登録 | PASS baseline | 完走・再現性 |
| EXP-002 | day 28 liquidation | 公開強豪の元方策 | paired cash差、終了在庫 |
| EXP-003 | CAREを給餌済みに限定 | EXP-002 | Milk/Wool量、paired score |
| EXP-004 | FEED taskのroute commitment | EXP-003 | 逃亡数、PICKUP数、score |
| EXP-005 | 生産2日前以内だけ施肥 | EXP-004 | 肥料効率、商品別生産、score |

この5本で「評価できる」「公開強豪を動かせる」「既知の高確度改善を再現できる」ところまで進め、その後に独自の生産計画探索へ移る。
