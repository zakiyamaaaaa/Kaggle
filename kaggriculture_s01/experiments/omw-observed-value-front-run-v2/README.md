# OMW observed value front-run v2

v1の周期予測に価格価値ゲートを追加した候補。

- ゲームと同じ市場価格曲線で現在売却収益を計算する。
- 相手の予測売却量を市場inventoryへ加算する。
- 次回の自分の予定売却までに発生する町・Shop需要を差し引く。
- 同一試合・同一商品で過去の予測が2回以上解決し、的中率75%以上の場合だけ介入する。
- `今売る収益 − 待つ収益 >= 4` かつ1 unitあたり0.5以上の場合だけ先売りする。
- 前倒し対象は24 turn以内の全予定量ではなく、次回予定ロットだけ。
- v1とOne More Wheat原版は変更しない。

これはローカル実験用。採用時には依存コードを単一`main.py`へinlineする。

## 最終候補（2026-09-21）

単純周期v1の誤予測を抑えるため、同一試合・同一商品で解決済み予測が2件以上、
的中率75%以上の場合だけ価値ゲートへ進む。32 seeds×両seatのScreenでは以下。

| 相手 | v2 | One More Wheat原版 | 差 |
|---|---:|---:|---:|
| One More Wheat | 3勝3敗58分、平均差0 | 同左 | 0 |
| Triad Counter | 57勝7敗、平均差+1,458.67 | 同左 | 0 |

このScreenでは信頼度ゲートにより先売りは発火せず、原版と完全一致した。Smokeを含む
Peak、Salemでも原版と一致。未知相手が高精度の反復売却を示した場合だけ適応する安全候補。

`scripts/build_omw_observed_value_v2.py`で単一`main.py`へbundle済み。bundle版とlocal
wrapper版の16試合は全て同値、平均差0。tarは`submissions/omw-observed-value-front-run-v2.tar.gz`。

Kaggleへの送信は外部変更の承認ゲートで拒否されたため未実施。明示承認後に提出する。
