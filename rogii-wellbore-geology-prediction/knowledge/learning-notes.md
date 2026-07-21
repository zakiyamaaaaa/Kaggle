# ROGII Wellbore Geology Prediction — 改善ノート

更新日: 2026-07-21

このファイルを、Discussion・公開Code・ローカル評価・Kaggle提出結果を蓄積する knowledge とする。新しい実験を行う前に「仮説」「リークの有無」「既存手法との差分」をここへ追記し、提出後は公開スコアを記録する。

## 現在の基準

| 手法 | ローカル評価 | Kaggle public | 状態 |
|---|---:|---:|---|
| 最後に観測された `TVT_input` を保持 | RMSE 15.9099 | 15.883 | 提出済み |
| `Z` の井戸内線形外挿 | RMSE 124.1808 | — | 却下 |
| `X,Y,Z,MD` の井戸内線形外挿 | RMSE 61.9868 | — | 却下 |
| 3D formation KNN（試作） | RMSE 約78.8 | — | 却下 |
| typewell GR軽量beam + 20%保守ブレンド | RMSE 15.8618 | 15.702 | 提出済み |

ローカル評価は、学習horizontal wellの `TVT_input` が観測されているprefixだけを入力にし、`TVT_input` が欠損しているsuffixの真値 `TVT` を評価する。したがって、提出時の「観測prefixから未観測suffixを予測する」構造を保っている。最終的な判断は、同じ公開テストに対するKaggleスコアで行う。

## データ理解

- 学習horizontal wellは773井、約509万行。評価対象suffixは約378万行。
- 推論時に使える主な列は `GR, MD, TVT_input, X, Y, Z`。学習時だけ存在する `TVT` と formation surface列を直接テスト入力へ持ち込まない。
- typewellは `TVT, GR` の基準ログ。Discussionでは、typewellはGRとTVTの対応表であり、水平井の地質位置をGRパターン照合で追跡する中心情報と説明されている。
- `TVT` は単純な深度や層厚ではなく、地質層境界に対する垂直距離。水平掘削では「同じ層準を保つ」ことが目的なので、`Z` の直接外挿は危険。
- 学習用formation surface列はtypewellから派生した情報で、テストhorizontalには存在しない。使う場合は、学習井の空間情報から推定する二段構成にする。

## Discussionから得た仮説

### H1: GRのpointwise一致ではなく、typewellとの時系列照合

単一GR値の最近傍探索は同じ値が頻出するため不安定。公開Codeでは、以下の組み合わせが使われている。

- GRのrolling平滑化
- typewellのTVT軸上への補間
- beam search / particle filter / NCCによる複数候補追跡
- `TVT + Z` を層準の状態として扱う物理的なanchor

まずは軽量beam searchを実装し、最後の観測TVTからtypewell GRを追跡する。候補の移動量にペナルティを課し、単発のGRノイズで大きく飛ばないようにする。

### H2: 周辺井の空間構造

Discussionでは、残差の主因は単独井のdecoderではなく、近隣井から得られる空間構造だと報告されている。公開Codeの `FormationPlaneKNN` は、周辺井のformation surfaceをXY平面上の局所平面で補間し、`TVT = -Z + formation + offset` の候補を作る。

ただし、formation surfaceはテストに直接ないため、学習井の空間補間とprefix anchorの組み合わせとして検証する。単純なformation中央値KNNはローカルRMSE約78.8で失敗したため、単純平均ではなく局所平面・井戸除外・formationごとの信頼度が必要。

### H3: GRセンサーの周期ノイズ

Discussionでは、GRに回転由来の周期アーティファクトがあり、rolling median / low-passでdatum localizationが改善する可能性が報告されている。平滑化を強くしすぎると層境界を消すため、windowを複数用意し、候補間の合意を信頼度として使う。

### H4: 曖昧な地質パターンは無理に決めない

複数のtypewell位置が同じGRパターンを説明する井戸があり、Discussionではbimodal datum / irreducible minorityが指摘されている。複数decoderが大きく乖離するsuffixは、移動を小さくしてlast-value側へ戻す保守的なゲートを入れる。

### H5: 検証はfield / well単位で行う

行単位のrandom splitは同一井戸の隣接行をtrainとvalidationに分けるため、過大評価になる。基本評価は「各井戸のprefix→suffix」。モデル学習を行う場合はwell-grouped splitを併記する。

## 公開情報の参照先

- [Problem Breakdown](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/708367) — TVT/typewellの意味、データ欠損、GRノイズ、pseudo-typewell。
- [Dynamic Programming for TVT Tracking](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/702919) — Viterbi/DPはCVを改善するが、decoder単独ではLB改善が小さいという注意点。
- [A geophysicist's take](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/702131) — domain priorと空間構造の方向性。
- [Where does the top-team signal come from](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/726465) — per-well oracle後に残る構造誤差。
- [Formation Columns Are Derived from Typewell](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/708167) — formation列の扱いに関する注意。
- [Look Ahead and Data Leakage](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/709764) — hidden suffixを使う実装を避けるための確認。
- [ROGII Public TVT Solution](https://www.kaggle.com/code/kaiwalyaatulraut/rogii-public-tvt-solution) — beam、particle filter、NCC、FormationPlaneKNNを組み合わせた公開実装。
- [ROGII GeoAnchor](https://www.kaggle.com/code/lucifer19/rogii-geoanchor) — prefix校正、物理anchor、suffixの保守的な補正。
- [Pure 3D Spatial KNN TVT](https://www.kaggle.com/code/hongweiluan/rogii-arch002-pure-3d-knn-tvt) — 空間KNNを単独で検証した公開実装。

## 改善ループ

1. このノートに仮説と出典を追加する。
2. `scripts/` に再現可能な実装を追加する。
3. prefix→suffixのローカル評価を実行し、RMSEだけでなく井戸別RMSEのp50/p90も記録する。
4. 既存の15.9099相当を超えた候補だけNotebook化する。
5. Kaggle Notebookをpushし、Notebook経由で提出する。
6. `competitions submissions` でpublic scoreとsubmission refを確認する。
7. 結果・失敗理由・次の仮説をこのノートと `experiments/results.csv` に追記する。

## 次に試す順番

1. 軽量beam search（GR + typewell + 移動ペナルティ）。
2. 複数windowのNCCとbeamの合意ゲート。
3. `TVT + Z` を状態にした局所particle filter。
4. 周辺井のformation surface局所平面KNN。
5. decoder候補と空間候補のwellごとの重み付きblend。

## 2026-07-21 提出ログ

- `safe_beam_alpha_020_clip60`: 全773井・約378万suffix行でRMSE 15.8618。last-valueとの差は小さいが、全体で再現した改善。
- Kaggle Notebook: [ROGII Safe Typewell Beam Baseline](https://www.kaggle.com/code/zacky21/rogii-safe-typewell-beam-baseline)
- Submission ref: `54876671`。public scoreは15.702で、last-valueの15.883から0.181改善。
