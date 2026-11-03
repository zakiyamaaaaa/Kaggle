# OMW net-stock sell-now v2

One More Wheatの公開盤面由来の相手在庫推定を使うが、単純な在庫閾値だけでは前倒ししない。
次の予定売却までに町が消費する数量を相手在庫から差し引き、売却後も市場に残ると予測される
`net_batch`が12以上、かつ価格モデル上の損失回避額が1以上の場合だけ予定売却を現在へ移す。

既定値:

- 相手推定在庫閾値: 12
- 町需要控除後の最低残量: 12
- 最低価格影響: 1

環境変数`OMW_NET_SN_K`、`OMW_NET_SN_BUFFER`、`OMW_NET_SN_EXPOSURE`で探索できる。

## 2026-09-21 結果

単純な相手在庫閾値だけのv1は、鏡とTriadを改善した一方、Peakで勝率が落ちる設定があり、
独立seedでは平均cashも不安定だった。v2は次回予定売却までの町需要を控除する。
`net buffer`を4/8/12で比較し、12を採用した。

独立seed各32戦（16 seed × 両seat）の主指標は次の通り。scoreは勝1・引分0.5・敗0。

| 相手 | One More Wheat原版 | v2 | 判定 |
|---|---:|---:|---|
| One More Wheat | 0.5000 | 0.7500 | 改善 |
| 2950 Peak | 0.96875 | 0.96875 | 維持 |
| Triad Counter | 0.8750 | 0.9375 | 改善 |
| Salem early-milk | 1.0000 | 1.0000 | 維持 |
| local candidate | 1.0000 | 1.0000 | 維持 |

別seedのpublic Salem 16戦も16勝0敗。全評価で実行エラーは0だった。cash差は補助指標で、
Kaggle ratingと最終Bradley–Terryは勝敗だけを使うため、昇格判断は上表のscoreを優先する。

提出用アーカイブは`submissions/omw-net-stock-sellnow-v2.tar.gz`。単一`main.py`のみを含み、
開発版との8戦parityは全引分・平均差0。Validation/Holdout完了後のmanifest statusは
`validated_not_submitted`。Kaggleへの提出が確認できるまではこの状態を維持する。

## Validation / Holdout

Screen後はパラメータを固定し、自己完結版を原版と同じseed・両seat・6相手で評価した。

| 段階 | seed | 1方策あたり試合数 | 候補score | 原版score | paired差 | seed bootstrap 95% CI | error |
|---|---:|---:|---:|---:|---:|---:|---:|
| Validation | 128 | 1,536 | 0.931315 | 0.882161 | +0.049154 | [+0.025065, +0.073893] | 0 |
| Holdout | 256 | 3,072 | 0.932617 | 0.888997 | +0.043620 | [+0.027669, +0.059896] | 0 |

Holdoutの相手別scoreは、One More Wheatが0.500000→0.718750、Peakが
0.912109→0.933594、Triadが0.921875→0.943359。Salem、early-milk、baselineは
いずれも1.000000を維持した。全件は`results-summary.json`に保存した。
