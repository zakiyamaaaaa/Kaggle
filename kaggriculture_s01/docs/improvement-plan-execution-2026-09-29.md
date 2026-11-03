# Kaggriculture 9月29日改善計画の実行記録

## Kaggle CLIで確認した現在地

2026-09-29 05:46 UTC頃、Kaggle CLI 2.2.4で `kaggriculture` の提出履歴とepisode一覧を取得した。競技締切はCLI表示で **2026-09-30 23:59 UTC**、表示順位は1,359位だった。順位・Public ratingは変動するスナップショットである。

| 最新順 | 提出ID | 方策 | 状態 | Public rating | Public / Validation episode |
|---:|---:|---|---|---:|---:|
| 1 | `56654813` | hybrid2965 | COMPLETE | 1883.7 | 68 / 1 |
| 2 | `56654513` | cha22 | COMPLETE | 1661.7 | 64 / 1 |
| 3 | `56639982` | OMW観測価値版 | COMPLETE | 1490.0 | 77 / 1 |
| 4 | `56639976` | OMW原版 | COMPLETE | 1511.9 | 79 / 1 |

4件のepisode一覧はすべて `COMPLETED` で、errorは0。net-stock v2 `56417821` も307 Public + 1 Validationの全308件が `COMPLETED`。取得した一覧は [`outputs/plan-execution-2026-09-29/submissions.json`](../outputs/plan-execution-2026-09-29/submissions.json) と [`outputs/final-sprint-2026-09-28`](../outputs/final-sprint-2026-09-28) の `episodes-<id>-20260929.json` に保存した。

`cha22` と `hybrid2965` のローカルtarは、それぞれmanifest記載のアーカイブSHA-256、`main.py` SHA-256、メンバー一覧と一致した。これはローカルファイルの照合であり、CLIがサーバー側bytesのhashを返すわけではない。

## Replay追加取得

Kaggle CLIの `competitions replay` でnet-stockの `111507511`、`111835222`、観測価値版の `114710007`、`114764884` を取得した。全4件が720 stepで `DONE`。内訳はnet-stockが2勝（最終cash差 +74,321、+1,128）、観測価値版が2敗（-3、-604）。既存の直近3敗戦だけを根拠にしないための追加標本で、無作為標本ではない。ファイルは [`outputs/plan-execution-2026-09-29/replays`](../outputs/plan-execution-2026-09-29/replays) に保存した。

## 評価規則の確認上の制約

Kaggle CLIの `competitions pages` は、helpに示された両方の引数順で `kaggriculture` をcommandと誤解して失敗した。したがって、最終評価に最新2提出を使う規則は今回のCLIで再取得できていない。[以前の公式Evaluation確認記録](strategy-review-2026-09-20.md)を用いる。

## 採否

新規seed 997000–997007、両seat、OMW/Peak/Triadの8-seed smokeでは、OMW原版と観測価値版の48試合ずつが全て完走し、強敵別の勝敗、score、平均cashまで一致した。平均scoreは両者0.750、paired差0。結果は [`omw-observed-smoke-997000-8.json`](../outputs/final-sprint-2026-09-29/omw-observed-smoke-997000-8.json)。これは差がない一般的証明ではないが、観測価値版を現在の最終2枠へ再昇格させる根拠は増えなかった。

hybrid2965とcha22も新規2 seed × 両seat × 5相手で完走し、error 0。平均scoreはcha22が0.900、hybrid2965が0.700、paired差-0.200、seed-bootstrap 95%区間[-0.500,+0.100]。結果は [`hybrid-vs-cha22-smoke-997000.json`](../outputs/final-sprint-2026-09-29/hybrid-vs-cha22-smoke-997000.json)。この2 seedだけでは方向判定できないため、別の未使用seed 997100–997131で32-seed screenを追加した。

追加screenは全640試合完走、error 0。平均scoreはcha22 0.821875、hybrid2965 0.921875、paired差 **+0.1000**、seed-bootstrap 95%区間 **[+0.015625,+0.171875]**。相手別hybrid2965のscoreはcha22 0.84375、herd-risk 0.921875、OMW 0.9375、Peak 0.9375、Triad 0.96875。cha22 controlに対しcha22鏡とherd-riskでは改善し、OMW/Peak/Triadでは悪化した。結果は [`hybrid-vs-cha22-screen-997100-32.json`](../outputs/final-sprint-2026-09-29/hybrid-vs-cha22-screen-997100-32.json)。[既存64-seed validation](../outputs/final-sprint-2026-09-28/hybrid-validation-64.json)の+0.065625と改善方向は一致したが、hybrid2965は計画の厳密な128-seed Validation gateまでは達していない。

別の未使用128 seed（997200–997327）の一括評価は結果JSONを出せずに停滞したため中断し、同じseed範囲を16 seedずつ8区間で再実行した。各区間が完走し、結合時に2,560行のseed・seat・相手・方策keyに欠落・重複がないことを確認した。全試合 `completed`、error 0。結合結果は [`hybrid-vs-cha22-validation-997200-128.json`](../outputs/final-sprint-2026-09-29/hybrid-vs-cha22-validation-997200-128.json)。

128-seed Validationの平均scoreはcha22 control **0.85703125**、hybrid2965 **0.91484375**。paired差は **+0.0578125**、seed-bootstrap 95%区間 **[+0.0234375,+0.09140625]**。相手別差はcha22鏡 +0.394531、herd-risk -0.007812、OMW -0.050781、Peak -0.023438、Triad -0.023438。各相手のseed単位95%区間では負方向の4相手すべてが0を跨いだ。aggregate gateは通過するが、相手別の退行方向は最終2枠にcha22を残す理由として扱う。

[`audit_market_replays.py`](../scripts/audit_market_replays.py) で保存済み16 Replayの市場注文・約定・cashを再構成した。結果は [`market-replay-audit.json`](../outputs/final-sprint-2026-09-28/market-replay-audit.json)。16件すべてでcash ledgerが記録済み最終rewardと一致し、11件は盤面・市場・private stateの全transitionも一致した。残る5件の不一致は終日のShed容量超過stepで、private stateの差として残るため、完全な状態再現を主張しない。

16件のSELL注文量は36,668、実約定量は26,261、未約定は10,407。実約定した単位を取引前quoteで評価すると2,166,102だったが、再構成された売上は2,039,374で差は126,728。価格下限での約定は1,658単位だった。これは複数方策・異なる相手を混ぜた記述統計で、先売りパッチの期待改善額ではない。元のPublic敗戦3件でも約定率は89.4～90.6%と高く、約定率だけでは敗戦を説明しない。`SELL FERTILIZER 997` が0約定となる例も勝敗双方にある。

未使用holdout 997400–997655も16 seedずつ16区間で実行した。結合時に5,120行のkeyに欠落・重複がないことを確認し、全試合 `completed`、error 0。結果は [`hybrid-vs-cha22-holdout-997400-256.json`](../outputs/final-sprint-2026-09-29/hybrid-vs-cha22-holdout-997400-256.json)。平均scoreはcha22 control **0.85703125**、hybrid2965 **0.871484375**。paired差 **+0.014453125**、seed-bootstrap 95%区間 **[-0.016015625,+0.0421875]** で、計画のholdout gateは通過しなかった。相手別差はcha22鏡 +0.294922、herd-risk -0.054688、OMW -0.066406、Peak -0.054688、Triad -0.046875。OMW、Peak、Triadの95%区間上限はいずれも0未満で、明確な退行がある。

**判断:** 先売りの損失条件を相手・商品・時期で再現できる段階には至っていない。計画P0の完了条件を満たさないため、市場パッチは作らず、追加提出もしない。hybrid2965の総合的な優位もholdoutでは確認できず、同方策をcha22の全面的な上位互換とは扱わない。一方、cha22鏡ではhybrid2965が一貫して勝ち、公開強豪コピーとの対戦に対する別の選択肢になる。既存のOMW候補は新規smokeで観測価値版と同じ挙動であり、公開強豪panelではcha22より弱かった。**すでにKaggleへ提出済みの最新2件 `cha22` と `hybrid2965` を、異なる相手への補完関係を持つ候補として維持する。** Public ratingとPrivate評価への転移は未確定。

2026-09-29 07:21 UTCのCLI再確認では、最新2件は `hybrid2965` `56654813`（COMPLETE、Public 91 + Validation 1、全件COMPLETED、live rating 1877.3）と `cha22` `56654513`（COMPLETE、Public 76 + Validation 1、全件COMPLETED、live rating 1692.2）。Private scoreは未表示。episode一覧は [`outputs/plan-execution-2026-09-29`](../outputs/plan-execution-2026-09-29) の `episodes-<id>-final.json` に保存した。今回新規の提出は行っていない。これら2件は本計画の実行開始前にKaggle CLIで提出済みだった。
