# 公開コード再調査（2026-09-21）

Kaggle CLIで最新のKaggriculture公開Notebookを取得し、自己完結したエージェントを
現在のローカル環境（`kaggle-environments 1.32.7`）へ抽出して、公開Salem 2900を
基準に同一seed・両seatで比較した。その後、One More WheatをKaggleへ提出した。

## 結論

Salemより明確に強い公開コードがある。最有力は Dmitrii Gluzdov の
[`Kaggriculture: One More Wheat`](https://www.kaggle.com/code/dmitriigluzdov/kaggriculture-one-more-wheat)。

| 比較 | 試合 | 勝敗 | 平均資金差 |
|---|---:|---:|---:|
| One More Wheat vs Salem（探索seed） | 16 | 16-0 | +34,559.8 |
| One More Wheat vs Salem（別holdout seed） | 32 | 32-0 | +33,072.2 |
| 2950 Peak vs Salem | 16 | 16-0 | +33,446.9 |
| Triad Counter vs Salem | 16 | 16-0 | +33,494.6 |
| One More Wheat vs 2950 Peak | 16 | 16-0 | +1,855.4 |
| One More Wheat vs Triad Counter | 16 | 16-0 | +1,513.4 |
| One More Wheat vs 現ローカルcandidate | 16 | 16-0 | +31,235.1 |

全112試合が正常完走した。結果JSONは [`evaluations/`](evaluations/) に保存した。
これはローカルhead-to-headであり、Kaggle ratingの保証ではない。Notebook名の
「2950」は作者の表示で、現在のleaderboard上の同一コードのratingとは照合できない。

## Kaggle提出結果（2026-09-21確認）

- Submission ID: `56409440`
- File: `one-more-wheat-v1.tar.gz`
- Submitted: `2026-09-21 00:38:26.483 UTC`
- Status: `COMPLETE`
- 初期表示Public score: **600.0**（validationのみ）
- 最新表示Public score: **706.1**（public 1件反映後）
- Episodes: validation 1件（`111423009`）、public 1件（`111424300`）

600.0はvalidation直後の初期表示だった。その後、最初のpublic episodeで
`Artem Zenkevich` に141,033対52,356（+88,677）で勝利し、706.1へ上昇した。
比較対象のSalem提出 `56186872`（表示974.2）には多数のpublic episodeがあるため、
まだ706.1対974.2を安定した実力差として扱ってはいけない。One More Wheatの
public episodeがさらに蓄積した時点で改めて評価する。

提出tar内の `main.py` は抽出ソースとbyte-for-byte一致した。tar SHA-256は
`4fd9470dbaff31a4fdc5f6c29fb2c9878f05772e6e4b7eb3029a7a0d033fcec0`、
`main.py` SHA-256は
`10f58185b916392ca39697c83f67f455df81a74dfb6eb1aacd60fd81d50c9970`。

## 最有力: One More Wheat

- Metav4 + Pipe16系の強いroute/RACE/day-11 sheepスタックを継承。
- 将来pastureになる `(2, 4)` に、暇なworkerで一時WHEATを栽培。
- 従来のDay 2収穫を1日遅らせ、2 wheatではなく3 wheatを収穫する。
- cow配置前にpastureを復元するため、後続routeを遅らせない。
- 追加の土地・workerを必要としない。

最も参考になるのは、巨大なroute全体のコピーではなく、既存route中のidle時間と
将来使用するtileを一時的な短期生産へ転換し、後続予定の直前に原状復帰する考え方。
現在のcandidateへ適用する場合は、opening wheatだけを独立layerとして移植し、
両seat・複数strategy familyでablationするのが安全。

抽出済みソース: [`extracted/one-more-wheat/main.py`](extracted/one-more-wheat/main.py)
（SHA-256 `10f58185b916392ca39697c83f67f455df81a74dfb6eb1aacd60fd81d50c9970`）。

## 次点

### The 2950 Peak Farm

[`The 2950 Peak Farm`](https://www.kaggle.com/code/haideptry/the-2950-peak-farm) は
zero-idle opening、day-11 sheep、40-turn RACE front-runningを統合している。
Salemには大差で勝つが、今回の直接比較ではOne More Wheatに全敗した。

### Triad Counter

[`Countering the Big 3 Meta`](https://www.kaggle.com/code/haideptry/countering-the-big-3-meta)
は、22-WHEAT opening、day-11 wool dump、公開cloneの同期売却を狙うcounter。
市場inventory差分から相手の売却を復元し、woolを先売りする発想は有用。ただし
One More Wheatとの直接比較では全敗し、meta依存性が高い。

### Route A/B Timing Lab

[`Route A/B Timing Lab`](https://www.kaggle.com/code/prvsiyan/kaggriculture-route-ab-timing-lab-20260921)
は提出コードではなく分析Notebook。temporary wheatを1日延長する差分について、
作者の64 seed・両seat比較では128試合中125勝、平均reward差 +27.56としている。
One More Wheatの小さな変更を独立検証する資料として有用。

## 取得・検証方法

- 一覧・取得は `kaggle kernels list` / `kaggle kernels pull` のみを使用。
- `%%writefile main.py` はそのまま抽出。
- 埋め込みtarはASTからbase64定数だけを読み、`main.py` をcompile確認して抽出。
- 評価は `scripts/evaluate_public_agent.py` で同一seedをseat swapして実行。
- 公開コードは第三者著作物であり、各ソースのライセンス・NOTICEを維持する必要がある。
