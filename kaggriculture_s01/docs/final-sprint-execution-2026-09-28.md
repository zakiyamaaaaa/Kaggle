# Kaggriculture 9月28日 実行記録

## 範囲

[最終改善計画](final-sprint-plan-2026-09-28.md) のP0を実行した。Kaggle側はCLIの読み取り操作のみ。新たな提出は行っていない。

## 公式CLI確認

- `kaggle competitions submissions kaggriculture --format json --page-size 50` の結果を [`outputs/final-sprint-2026-09-28/submissions.json`](../outputs/final-sprint-2026-09-28/submissions.json) に保存。
- `kaggle competitions episodes <submission_id> --format json` の出力を同じディレクトリに保存。CLIがJSONの後に案内文を付けるため、機械処理時は `JSONDecoder.raw_decode` で先頭JSONを読む。

| 方策 | ID | Public episodes | Validation episodes | 状態 | 9/28 live rating |
|---|---:|---:|---:|---|---:|
| OMW原版 | `56409440` | 81 | 1 | 全82件COMPLETED | 2763.4 |
| 観測価値版 | `56410705` | 99 | 1 | 全100件COMPLETED | 2716.5 |
| net-stock v2 | `56417821` | 307 | 1 | 全308件COMPLETED | 2449.8 |
| zero-sell guard | `56593371` | 58 | 1 | 全59件COMPLETED | 884.5 |

Public ratingは試合数も相手も違うlive値であり、上表の差を方策の因果効果とは解釈しない。現時点の最新2提出はzero-sell guardとERRORのstrong ensembleで、強候補を最終枠に戻す作業が必要。

## 提出物の保全

ローカルの3アーカイブをSHA-256照合し、tar内の `main.py` もmanifestと一致した。原版tarには`LICENSE.txt`、`NOTICE.txt`、`main.py`、他の2本には`main.py`のみが入る。対応するmanifestは以下。

| 方策 | ローカルarchive SHA-256 | main SHA-256 |
|---|---|---|
| OMW原版 | `4fd9470dbaff31a4fdc5f6c29fb2c9878f05772e6e4b7eb3029a7a0d033fcec0` | `10f58185b916392ca39697c83f67f455df81a74dfb6eb1aacd60fd81d50c9970` |
| 観測価値版 | `630e368cc5a9602f6666634f3e2c854bd3d69fa76984528cb9a301a6e9b1b874` | `a99f93407a39dc87c4a8785c8434a03975703800320b764d69af0366f7d290b5` |
| net-stock v2 | `f6930d60b396aac9c70cbc93abdf04f2d76f60c712ddb6ca7c10bd5515e59544` | `92434983336d9ebfd53c4e85613a9fd675ddb78c0b0f1b6bb828c76c30038057` |

これはローカルアーカイブの照合。CLIは提出済みサーバー側のアーカイブhashを返さないため、サーバー側bytesの同一性を直接証明したものではない。観測価値版とnet-stock版の古いmanifestに残っていた「未提出」statusは、CLIで確認したsubmission ID、提出時刻、live score snapshotへ更新した。

## 強敵との再比較

[`scripts/evaluate_final_sprint_20260928.py`](../scripts/evaluate_final_sprint_20260928.py) を作成し、OMW鏡、Peak2950、Triad Counterに同一seed・両seatで対戦させた。8-seed smokeの996000–996007は以前のmarket-order-auditで使用済みなので、独立の新規seedとは呼ばない。32-seed screenの996100–996131は既存の実験記録にない範囲を使用した。

| 範囲 | 方策 | OMW鏡 W-D-L | Peak W-D-L | Triad W-D-L | 3相手平均score | 原版との差 | error |
|---|---|---:|---:|---:|---:|---:|---:|
| 8-seed smoke | 原版 | 0-16-0 | 16-0-0 | 16-0-0 | 0.8333 | — | 0 |
| 8-seed smoke | 観測価値版 | 0-16-0 | 16-0-0 | 16-0-0 | 0.8333 | 0 | 0 |
| 8-seed smoke | net-stock v2 | 8-0-8 | 14-0-2 | 14-0-2 | 0.7500 | -0.0833 | 0 |
| 32-seed screen | 原版 | 1-62-1 | 60-0-4 | 60-0-4 | 0.7917 | — | 0 |
| 32-seed screen | net-stock v2 | 40-0-24 | 64-0-0 | 64-0-0 | 0.8750 | +0.0833 | 0 |

32-seed screenのseed単位bootstrap 95%区間は **[+0.0104, +0.1563]**。結果は [`strong-candidates-smoke.json`](../outputs/final-sprint-2026-09-28/strong-candidates-smoke.json) と [`strong-candidates-screen.json`](../outputs/final-sprint-2026-09-28/strong-candidates-screen.json) に保存した。観測価値版はsmoke全件で原版と結果・最終cashが一致し、この既存panelでは追加価値を測れない。

このscreenはnet-stock版のローカル効果を示すが、Publicでの優位を証明しない。smokeとの符号反転、および既存holdoutとPublicの不一致から、同系統3相手への過適合または本番相手分布のずれが未解決。

## 損失1例の診断と今日の判断

既知の不利seed 996003、seat 0、Peak戦をtrajectoryで再実行した。原版の最終rewardは76,394、net-stock版は74,636。最初のaction差はstep 385のMILK 5単位の先売り。以降62 stepでaction差があり、終盤step 718のShedは両者とも0、手持ちinventoryは両者とも8だった。step 718直前のmoneyは原版76,111、net-stock版74,353で、差は1,758。詳細は [`net-stock-loss-diagnostic.json`](../outputs/final-sprint-2026-09-28/net-stock-loss-diagnostic.json)。この1試合では終盤のShed売れ残りではなく、市場先売りと後続の価格・注文経路が損失源である。ただし単一試合の因果分解ではない。

**判断:** net-stock版を最終2枠の既定候補へ昇格させない。原版を安全枠として保持する。終盤清算の新パッチも、この事例からは根拠がなく、未実装。次はPublic敗戦replayと異系統の強敵を使い、変更が発火する相手条件を調べる。その後に限って単独パッチを試す。

## Public敗戦replayの初期診断

net-stock提出 `56417821` の直近3件を `kaggle competitions replay <episode_id>` で取得した。3件とも敗戦だった。これは全307 Public試合の無作為標本ではなく、直近3件に限る診断である。

| Episode | 相手 | 自分−相手の最終cash差 | 初回action差 | 同step・同商品のSELL重複 | 終了時Shed / worker在庫 |
|---|---|---:|---:|---:|---:|
| `112444887` | Juste Me (●'◡'●) | -1,839 | step 92 | 304 | 0 / 0 |
| `112453081` | emreaydin | -760 | step 92 | 270 | 0 / 0 |
| `112461339` | tyz123456 | -1,498 | step 1 | 326 | 0 / 0 |

3件の終局在庫はすべて0で、終盤清算の売れ残りは敗因として観測されなかった。相手は序盤から近いrouteを使う試合が多く、同step・同商品のSELLが頻発する。上表の重複は注文の同時存在数であり、約定損失や因果効果を示す値ではない。`112461339` では相手がstep 1にWHEATのBUY/SELL量を変えており、他2件はstep 92の売却有無が最初のaction差だった。次の仮説は終盤在庫より、同系統相手との市場raceと注文量の相互作用に置く。

## 残作業

- Public敗戦replayの対象を増やし、先売りが発火したstepの価格・実約定と最終cashの関係を調べる。直近3敗戦の初期診断だけで一般化しない。
- 入手できる異系統の強敵をpanelへ追加し、凍結原版と候補を再評価する。
- 最終評価の「最新2提出」規則をCLIで再確認する。今回使用中のCLIの `competitions pages` 引数解釈が不安定で、再取得できなかった。保存済み公式Evaluationの記録は [`strategy-review-2026-09-20.md`](strategy-review-2026-09-20.md) を参照。
- 最終2枠をCOMPLETEの強候補に戻す。これは提出を伴うため、今日の読み取り・検証作業には含めていない。
