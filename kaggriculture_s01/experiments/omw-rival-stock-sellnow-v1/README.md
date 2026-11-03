# OMW rival-stock sell-now v1

One More Wheat内のORDERPRI2は、相手の公開盤面から収穫量を追跡し、市場inventory差分で
相手の売却済み量を差し引いて、商品別の推定売却可能在庫を維持している。

既定コードでは売却順序の最適化だけが有効で、推定相手在庫が一定量を超えたときに
こちらの24 turn以内の予定売却を前倒しする分岐は`_OR2_SN_K=0`で無効。この候補は
その閾値だけを有効化する。

ローカル探索では環境変数`OMW_OR2_SN_K`で閾値を4/8/12/16/24 unitsから比較する。
既定は12。親のroute、opening、売却債務ledger、終盤plannerは変更しない。

