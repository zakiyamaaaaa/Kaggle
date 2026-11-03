# Kaggriculture: 直近3日間のKaggle調査

調査日: 2026-09-20（Asia/Tokyo）

対象期間は、日本時間の 2026-09-17 00:00 から CLI 取得時点までとした。Kaggle CLI 2.2.4 を使い、Discussion 14件と、期間内に更新された公開コード49件を一覧化した。そのうち、内容が具体的で現在の実装に応用可能そうな公開コード20件を `public-code/` に取得した。

## 結論

最優先で小さく検証する価値があるのは次の4系統。

1. **市場注文のキュー制御**: 空注文を消し、実行可能な SELL を前方へ詰める。注文は同一slotで相手とロックされるため、同じ数量でもslot位置が売価を左右する。
2. **羊のday 11投入と非収穫日の人員削減**: yarn店が早期に見えている場合、day 12ではなくday 11に6頭羊を入れるとday 29の5回目の収穫が間に合う。非収穫日は2人目の羊担当を雇わない。
3. **公開観測だけの売却予測**: 相手の市場inventory差分から実行済み売却を復元し、最近の公開対戦のsale streamと照合して、相手のpremium商品の売却直前に先売りする。
4. **評価プロトコルの強化**: fixed development panel、未使用seed・異なる戦略のheld-out panel、両seatのpaired比較、opponent別の勝率を分ける。古いreplayや同系統の相手だけでの勝率は過大評価しやすい。

一方、RLのDiscussionは「BCでwarm-upしてからmacro PPO」という有用な方向性はあるが、実装詳細と再現可能なコードは不足している。Gurobi/HiGHSは遅いという報告があり、現段階では決定的initializer＋heuristicの方が本プロジェクトに適合する。

## ファイル

- [`discussions.md`](discussions.md): Discussionの全対象スレッドと有用性評価
- [`public-code.md`](public-code.md): 公開コードの調査結果、著者記載の検証値、適用判断
- [`experiment-backlog.md`](experiment-backlog.md): 現在のコードに対して次に試す候補と検証条件
- [`public-code/`](public-code/): Kaggle CLIで取得した公開Notebookと `kernel-metadata.json`

## 出典・取得方法

Kaggle CLIで次を実行した。提出、push、Notebook実行などの外部状態変更は行っていない。

```text
kaggle competitions topics list kaggriculture --format json
kaggle competitions topics show kaggriculture <topic-id> --format json
kaggle kernels list --competition kaggriculture --format json
kaggle kernels pull <owner>/<kernel> --path public-code/<owner>__<kernel> --metadata
```

Notebookのスコア・勝敗・評価値は、別途明記しない限り各著者の記載値であり、この調査で再実行した結果ではない。特に「公開コード同士の局所panelでの勝率」と「Kaggle live rating」は分けて扱う。
