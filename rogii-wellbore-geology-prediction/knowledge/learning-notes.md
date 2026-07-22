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
| 周辺井prefix anchorの局所平面KNN + 10%保守ブレンド | RMSE 15.5614 | — | ローカル採用・未提出 |
| beam 25% + 空間平面 75% の保守blend | RMSE 15.5182 | — | 現行ローカル最良・未提出 |
| group-aware HGB residual（試作30井） | RMSE 15.2984 | — | 小規模試作は却下、全井・候補特徴で再設計 |

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

### H6: 4点台にはdecoder単独ではなく、候補軌跡の教師あり選択が必要

上位公開Codeでは、last-valueを基準にして、beam/PF/物理anchor/NCCなど複数候補を生成し、LightGBM・XGBoost・CatBoost等で残差または候補の重みをwell-grouped CVで学習する構成が繰り返し現れる。公開Codeの一例では、last-valueをresidual baselineにするだけで最近傍の傾きbaselineより大幅に安定し、別のstackではPF候補をGBDTとRidgeで統合している。

現在の15.5182は、候補を手作業で固定blendしている段階であり、候補のどれを採用するかを井戸・suffix位置ごとに学習していない。次は、候補値そのものだけでなく、候補間の差、GRの因果統計、prefixの長さ、軌跡の低周波トレンドを特徴にして、`TVT - last_known_tvt` をwell-grouped CVで学習する。

小規模30井・200行/井のHGB residual試作はRMSE 15.2984で、同じサンプルのbaseline 12.7084より悪化した。これはモデルが無効という結論ではなく、学習行が少なく候補特徴・well-grouped全体学習になっていないため、次回は773井を使い、井戸ごとに均等サンプリングし、5-fold OOFで候補重みを評価する。

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
- [XGB Starter](https://www.kaggle.com/code/cdeotte/xgb-starter-cv-15) — last-value residual baseline、候補特徴、well-grouped CVの基本形。
- [Target-Free TVT Geosteering](https://www.kaggle.com/code/pilkwang/rogii-target-free-tvt-geosteering) — PF/beam候補とpretrained LGBM、Ridge、projectionを重ねる構成。
- [Wellbore Geology Prediction | Ridge](https://www.kaggle.com/code/ravaghi/wellbore-geology-prediction-ridge) — PF候補をLightGBM/CatBoost/Ridgeでstackする公開実装。

## 改善ループ

1. このノートに仮説と出典を追加する。
2. `scripts/` に再現可能な実装を追加する。
3. prefix→suffixのローカル評価を実行し、RMSEだけでなく井戸別RMSEのp50/p90も記録する。
4. 既存の15.9099相当を超えた候補だけNotebook化する。
5. Kaggle Notebookをpushし、Notebook経由で提出する。
6. `competitions submissions` でpublic scoreとsubmission refを確認する。
7. 結果・失敗理由・次の仮説をこのノートと `experiments/results.csv` に追記する。

## 次に試す順番

1. GR平滑化 / 周期ノイズ対策を `safe_spatial_beam_blend` に保守的に重ねる。
2. 複数windowのNCCとbeamの合意ゲートを、空間平面blendの前段フィルタとして検証する。
3. 773井から候補軌跡を生成し、well-grouped OOFでLightGBM/XGBoost相当のresidual meta-modelを学習する。
4. 低周波トレンド（line/quadratic/smooth oracle）の誤差を、prefix由来の特徴で予測する。

## 2026-07-21 提出ログ

- `safe_beam_alpha_020_clip60`: 全773井・約378万suffix行でRMSE 15.8618。last-valueとの差は小さいが、全体で再現した改善。
- Kaggle Notebook: [ROGII Safe Typewell Beam Baseline](https://www.kaggle.com/code/zacky21/rogii-safe-typewell-beam-baseline)
- Submission ref: `54876671`。public scoreは15.702で、last-valueの15.883から0.181改善。

## 2026-07-21 NCC評価

- 仮説: typewell GRとの局所的な時系列相関（lookback 21、smooth window 7、search radius 12）を因果NCCで追跡し、suffixの移動を15%・±40で保守的に戻せば、beamとは異なるGRパターン情報を安全に追加できる。
- リーク確認: 学習horizontalの観測 `TVT_input` prefix、prefixとsuffixの `GR`、対応typewellの `TVT/GR` だけを使用し、suffixの真値 `TVT` は予測に渡していない。
- 結果: `safe_ncc_alpha_015_clip40` は全773井・3,783,989 suffix行でRMSE 16.382931、井戸別RMSE p50 10.935614、p90 23.690376。2026-07-21 の再実行でNCC計算をベクトル化し、実行時間は680.271秒から165.331秒へ短縮できたが、精度は基準 `safe_beam` の15.861771より0.521160悪いままで rejected。
- 理由: NCC単体は20井のスモークでRMSE 178.04となり、局所相関がtypewell上の誤った周期・類似パターンへ追跡する曖昧性が大きい。保守ブレンドで外れ値は抑えられたが、全体RMSEではbeam基準を超えなかった。
- 次の仮説: NCCを独立decoderとして使わず、beamとNCCが一致する区間だけを採用する合意ゲート、または現行最良の空間平面blendに対してGR平滑化/周期ノイズ対策を重ねる。

## 2026-07-21 TVT+Z物理anchor評価

- 仮説: 水平井では `TVT + Z` が局所的に安定するため、観測prefixの直近20行から中央値anchorを推定し、suffixの `Z` から `anchor - Z` を計算する。曖昧性を抑えるため、最後の `TVT_input` からの補正は4%・±40に制限した。
- リーク確認: 予測に使ったのは `TVT_input` prefix、suffixの推論可能な `Z`、および水平井ファイルの行順だけ。suffixの真値 `TVT`、train専用のformation surface列、typewellは予測に渡していない。test horizontalにも存在する列だけで再現可能である。
- 結果: `safe_physics_anchor_alpha_004_clip40` は全773井・3,783,989 suffix行でRMSE 15.8375943、井戸別RMSE p50 10.658889、p90 22.328145、実行時間11.113秒。基準 `safe_beam_alpha_020_clip60` の15.8617707より0.0241764改善したため improved とした。
- 出力: `outputs/submissions/safe_physics_anchor.csv` を生成した。Kaggle API、外部提出、公開Notebook実行は行っていないため、public scoreとsubmission refは未記録である。
- GitHub反映: `5723e15` (`rogii: add causal TVT Z physics anchor candidate`) とpush失敗記録 `02e6f9a` を作成した。初回 `git push origin HEAD` は `Could not resolve host: github.com` で失敗したが、承認付き再試行でoriginの `feat/exp-020-timeout-safe-replay` へ `02e6f9a` まで反映済みである。
- 次の仮説: この改善はZの局所的な層準変化を少量取り込んだ効果と考えられる。次回は候補リストから未実施の粒子filter、局所平面formation KNN、またはdecoder-空間候補の保守的blendを1件だけ選び、今回のanchorを固定fallbackとして比較する。

## 2026-07-21 粒子filter評価

- 仮説: typewellのTVTサンプルindexを状態とし、GR尤度と局所ランダムウォーク遷移を組み合わせた小規模bootstrap particle filterなら、beamの単一路線よりGRの曖昧な候補を平均化できる。粒子数48、遷移sigma 2.0、GR rolling median window 5、固定seed 1729、suffix移動の保守ブレンド20%・±60で検証した。
- リーク確認: 使用したのは観測 `TVT_input` prefix、水平井のGR（suffixを含む推論時入力）、対応typewellのTVT/GRだけで、suffixの真値 `TVT` と学習専用formation列は予測に渡していない。固定seedにより再現可能である。
- 結果: `safe_particle_alpha_020_clip60` は全773井・3,783,989 suffix行でRMSE 16.5610724、井戸別RMSE p50 11.063851、p90 24.476824、実行時間85.36秒。基準 `safe_beam_alpha_020_clip60` の15.8617707より0.6993017悪化したため rejected。
- 失敗理由: 粒子の重み付き平均は局所GR尤度だけではtypewell上の周期・類似パターンの複数モードを解消できず、誤ったモードへ粒子が移った後の保守ブレンドでも損失を回復できなかった。次に同じ候補を再訪するなら、particle単独ではなくbeamとの一致ゲート、または今回改善した `TVT + Z` anchorによる事前分布制約が必要。

## 2026-07-21 局所平面formation KNN評価

- 仮説: test horizontalにはformation surface列がないため、各周辺学習井の観測prefixだけから `TVT_input + Z` anchorを作り、井戸のXY位置で局所加重平面をfitする。対象井のsuffix XY上で補間したanchorから `TVT = anchor - Z` を得て、最後の観測値からの移動は10%・±60に制限する。単純なformation中央値KNN（RMSE約78.8）より、局所平面とprefix校正を使う。
- リーク確認: 周辺井メタデータは各井の `TVT_input` prefix末尾20行と `X,Y,Z` のみで作成し、対象井をKNNから除外した。対象suffixでは `X,Y,Z` と最後の観測 `TVT_input` のみを使用し、suffix真値 `TVT`、formation surface列、typewellは予測に渡していない。test horizontalの列構成でも再現可能である。
- 結果: `safe_spatial_plane_alpha_010_clip60` は全773井・3,783,989 suffix行でRMSE 15.5613541、井戸別RMSE p50 10.5807391、p90 22.3021217、実行時間17.788秒。基準 `safe_beam_alpha_020_clip60` の15.8617707より0.3004166改善し、今回のローカル基準として採用した。
- 出力: `outputs/submissions/safe_spatial_plane.csv`（14,151行、nullなし）を生成した。Kaggle API、外部提出、公開Notebook実行は行っていないため、public scoreとsubmission refは未記録である。
- GitHub反映: `43243bc`（`rogii: add local spatial plane anchor candidate`）を作成した。初回 `git push origin HEAD` は `Could not resolve host: github.com` で失敗したが、承認付き再試行でoriginの `feat/exp-020-timeout-safe-replay` へ反映済みである。

## 2026-07-21 decoder・空間候補blend評価

- 仮説: 局所平面anchorは空間的な層準を捉え、typewell beamはGR波形の局所的な追跡情報を持つため、両者を保守的に組み合わせると単独候補の誤差を相殺できる。局所平面の実績を優先し、beam 25%・空間平面75%の固定blendを検証した。
- 実装: `safe_spatial_beam_blend` は、beamを最後の `TVT_input` から20%・±60で、空間平面を10%・±60で各々guardした後、deltaを25%/75%で加重する。設定探索は行わず、1候補だけを評価した。
- リーク確認: beamは水平井のGRとprefixの `TVT_input`、対応typewellのTVT/GRだけを使い、空間平面は各学習井のprefix末尾20行から作った `TVT_input + Z` anchorとXYだけを使う。対象suffixの入力はGR・X・Y・Zのみで、真値TVT・formation surface列は予測に渡していない。
- 結果: `safe_spatial_beam_blend_alpha_025` は全773井・3,783,989 suffix行でRMSE 15.5181946、井戸別RMSE p50 10.4805207、p90 21.8713221、実行時間109.411秒。現行の `safe_spatial_plane_alpha_010_clip60`（15.5613541）より0.0431595改善し、ローカル基準として採用した。
- 出力: `outputs/submissions/safe_spatial_beam_blend.csv`（14,151行、nullなし）を生成した。Kaggle API、外部提出、公開Notebook実行は行っていない。
- 次の仮説: 空間＋decoder blendで改善したため、残る候補のGR平滑化/周期ノイズ対策は、beamと空間平面の両方に同時適用し、decoder単独の誤追跡を増やさない保守的な形で検証する。

## 2026-07-22 4点台との差分調査

- 現在のKaggle leaderboard上位は4.859前後。15点台の手作りdecoderとの差は、GR追跡の微調整では埋まらない。
- DiscussionのWorking Note Awardでは、上位の本質を「高周波のwiggleより低周波のtrendが誤差を決める」と整理している。別の分析では、best constant約9.04、line約6.70、quadratic約5.34、smooth約2.90というoracle ladderが示されている。
- 近傍井の静的krigingは、leave-one-outで約16.9 ftと報告され、現行の単純な空間planeだけで4点台を狙う方向は弱い。空間情報は曲線転写やmeta-featureとして使う必要がある。
- `test/` の公開3井はtrainと入力列が完全一致するが、Discussionの公式説明では公開testは提出作成用サンプルであり、Notebook rerun時にはhidden testへ置換される。したがってtrainのTVT直接lookupは本番手法として採用しない。
- 公開Codeの上位構成は、候補軌跡生成 → residual/candidate selectionの教師あり学習 → prefixでの自己検証 → 保守的blend、という順であり、次の実装はこの順序に合わせる。
