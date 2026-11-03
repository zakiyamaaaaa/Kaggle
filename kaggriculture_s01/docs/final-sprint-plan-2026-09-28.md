# Kaggriculture 最終改善計画

> 9月28日の実施結果は [実行記録](final-sprint-execution-2026-09-28.md) を参照。Public敗戦3件の終局在庫は0で、終盤清算より市場raceの検証を優先する。

- 策定日: 2026-09-28
- 目標: 銀メダル以上
- 締切: **2026-09-30 23:59 UTC（2026-10-01 08:59 JST）**。9月28日にKaggle CLIで確認。
- 原則: 強い提出物を保全し、勝敗で検証できた変更だけを最終提出へ進める。

## 1. 現在地と最重要リスク

9月28日の `kaggle competitions list --search kaggriculture --format json` は参加10,113チーム、表示順位2,378位を返した。これはその時点の表示であり、最終順位や銀メダル境界の推定値ではない。

同日の `kaggle competitions submissions kaggriculture --format json` による提出履歴は次のとおり。Public scoreは相手と試合数に応じて変動するlive ratingであり、候補間の固定テスト差ではない。

| 提出物 | ID | 状態 | Public rating |
|---|---:|---|---:|
| One More Wheat原版 | `56409440` | COMPLETE | 2763.4 |
| 観測価値版 | `56410705` | COMPLETE | 2716.5 |
| net-stock sell-now v2 | `56417821` | COMPLETE | 2449.8 |
| 最新のzero-sell guard | `56593371` | COMPLETE | 884.5 |
| 直前のstrong ensemble | `56505625` | ERROR | — |

net-stock v2はローカルholdoutで原版よりpaired score差 **+0.043620**、95%区間 **[+0.027669, +0.059896]** だった。それでもPublic ratingでは原版を下回る。最大の課題は、既存の対戦panelの改善が本番相手へ転移するかを見極めること。Public rating単独でもローカル勝率単独でも採用しない。

保存済みの公式Evaluation確認記録では最終評価に最新2提出を使う。締切前には、この規則をKaggle CLIで再確認し、最新2件を意図したCOMPLETEの強候補にする。現時点の最新2件は最終候補として不適切である。

## 2. 優先順位と日程

### P0 — 9月28日: 強い提出物を保全し、評価を校正する

1. 原版OMW、観測価値版、net-stock v2の提出済みアーカイブ、内容、SHA-256を照合して凍結する。各候補についてsubmission ID、Public episode数、ERRORの有無、rating取得時刻を記録する。
2. 原版と観測価値版を同一seed・両seatで比較する。OMW鏡、2950 Peak、Triad Counter、入手できる異系統の強敵を相手にし、相手別勝敗を出す。入手していない上位相手を「評価済み」とは扱わない。
3. Publicで原版を下回った変更の発火試合を特定し、売却時刻、実約定、最終在庫、相手の市場行動を確認する。評価panelに不足する相手の型を具体化する。

### P1 — 9月28～29日: 高価値の変更を一つずつ試す

第一候補は**終盤の現金化**。残りstepで回収・運搬・約定できる商品を区別し、売れ残りや回収不能な在庫が勝敗を変える試合だけを対象にする。変更が発火した試合の対照差と、発火しない試合の挙動一致を両方確認する。

第二候補は、相手の反復売却が十分観測された場合だけの小さな市場適応。forecast4は32-seed screenで原版よりpaired score **+0.046875** だったが、OMW鏡に14敗し、validationは未実施。order-safe、repeat-guard、capped、externality gate、price guardは追加の勝敗改善が確認できていない。これらを重ねて投入しない。net-stock v2のPublic逆転があるため、市場の先売り条件を増やす実験は後順位にする。

各仮説は一変更に限定し、次の順で判定する。

| Gate | 規模 | 通過条件 |
|---|---|---|
| Smoke | 8 seed、両seat | 完走、ERROR/INVALID/TIMEOUT 0、明白な退行なし |
| Screen | 新規32 seed、両seat | 強敵別の勝敗を確認し、paired scoreが改善 |
| Validation | 新規128 seed、両seat | seed単位bootstrapの95%区間下限が0超、主要相手の明確な悪化なし |
| Holdout | 選定後の未使用256 seed、両seat | Validationと方向が一致し、実行エラー0 |

主指標は `win + 0.5 × draw`。cash差、実売上、残在庫、価格、処理時間は診断値にする。簡単な相手を多数含む平均だけで昇格させない。時間が足りずvalidationを終えられない変更は最終提出へ進めない。

### P2 — 9月29～30日: 最終2枠を確定する

1. Gateを通過した新候補だけ単一`main.py`へbundleし、元の実験版との挙動一致、Kaggle相当環境での完走、処理時間、依存関係を確認する。
2. 新候補が通らなければ、原版OMWと観測価値版を基本案にする。両者が実質同じ挙動なら、強敵別評価で検証済みの異系統候補があるかを確認する。未知の変更で枠を埋めない。
3. 提出前にcompetition slug、アーカイブ内容、SHA-256を読み取り確認する。Kaggle側の操作はCLIを使う。送信後にsubmission ID、COMPLETE、episode error、Public ratingの取得時刻を記録する。
4. 9月30日は新機能の追加を止め、締切より十分前に最新2提出が意図したアーカイブであることをCLIで確認する。

## 3. 停止基準

- 強敵への明確な退行、実行エラー、またはvalidationの95%区間が0を跨ぐ変更は採用しない。
- Public scoreの一時的な上下だけで凍結した強候補を捨てない。
- 終盤までに新候補がgateを通らなければ、既存のCOMPLETEな強候補で最終2枠を確保する。
- 銀メダルの可否は現時点で保証できない。順位に加え、強敵別勝率、提出完走率、Public episode数を追う。

この計画の作成時点では、新たなKaggle提出は行っていない。
