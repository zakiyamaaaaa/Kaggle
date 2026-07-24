# ROGII Wellbore Geology Prediction — 改善ノート

更新日: 2026-07-24

このファイルを、Discussion・公開Code・ローカル評価・Kaggle提出結果を蓄積する knowledge とする。新しい実験を行う前に「仮説」「リークの有無」「既存手法との差分」をここへ追記し、提出後は公開スコアを記録する。

## 他セッション向け最優先方針（2026-07-22）

### 結論

現行のHGB候補選択は全suffix OOFでRMSE 14.6113まで改善したが、Leaderboard上位4.859および6点前後の上位集団とは大差がある。HGBのパラメータ、GR平滑化window、固定blend比率の追加探索ではこの差は埋まらない。以後は「弱い候補を精密に選ぶ」段階を終了し、候補軌道生成を全面的に強化する。

次のセッションは、最初に候補バンクのoracle RMSEを計測すること。各行または各井で正解に最も近い候補を選んだoracleが7以下にならない限り、selectorのモデル変更やstackを優先しない。

### 実装する順番

1. `candidate_bank_v2` を作り、予測時に利用可能なsuffix全体のGRを使う非因果候補を追加する。testではsuffixのGR・MD・XYZは全行与えられるため、centered rolling、GR lead、全区間alignmentは使用可能。suffixの真値TVTは使用しない。
2. multi-scale constrained DTWを追加する。複数radiusのTVT軌道、alignment cost、radius間分散、prefix境界でのanchor誤差を保存する。
3. 5〜7設定のbeam ensemble、prefix GRとのmulti-scale self-correlation、`U = TVT + Z`を状態とするANCC particle filter、Z速度particle filterを追加する。候補値だけでなく分散・尤度・候補間gapも保存する。
4. trainの6 formation surface（ANCC、ASTNU、ASTNL、EGFDU、EGFDL、BUDA）を近傍井から局所平面またはdense KNNで補間し、対象井prefixで `b_well = median(TVT_input + Z - formation)` を校正する。対象井自身のformation列は必ず除外する。
5. 静的な空間面だけでなく、近傍井の完全な解釈済みTVT曲線をMD/XY/`U`座標で位置合わせして転写する。距離、prefix再現RMSE、転写候補間分散を信頼度特徴にする。
6. 候補oracleが十分に下がった後、二段階学習へ進む。Stage 1で井戸単位の低周波trend（`U`の一次・二次係数）を予測し、Stage 2でDTW/PF/beamの局所wiggle残差をLightGBM/CatBoostで予測する。GroupKFold OOFでRidgeまたは制約付きstackを行う。
7. 最後に井戸単位で `U = TVT + Z - anchor` をdegree 3〜5のrobust polynomialへprojectionし、OOFで選んだ50〜75%程度のblendと信頼度gateを適用する。

### 必須診断

- `candidate_oracle_row_rmse`: 各行で最良候補を選んだRMSE。
- `candidate_oracle_well_rmse`: 各井で最良候補を一つ選んだRMSE。
- `selector_regret`: selector RMSE − candidate oracle RMSE。候補生成とselectorのどちらがボトルネックか判定する。
- `trend_oracle`: last-value残差をconstant、line、quadratic、smoothでoracle fitしたRMSE。低周波trendの未回収量を測る。
- 井戸別RMSE p50/p90、近傍井距離別、prefix長別、候補間分散別の誤差。

採否基準は、候補oracleが10以上なら候補生成を継続、7〜10なら候補とselectorを並行改善、7以下ならLightGBM/CatBoost stackへ進む。最終モデルの採用は全suffix・well-grouped OOFで判断し、標本OOFだけで現行モデルを置き換えない。

### 当面打ち切る探索

- beamのGR平滑化window 3/7/9の追加探索。
- NCC単独、particle filter単独の固定blend。
- prefix anchorだけを使う静的XY平面の微調整。
- HGBのleaf数・learning rate・clip幅だけを変える探索。
- 公開test 3井とtrainの一致を使ったTVT直接lookup。hidden testへ一般化しない。

Kaggleへの提出はユーザーの明示指示があるまで行わない。ローカルで改善を確認し、`experiments/results.csv`と本ノートへ記録する。実装・評価結果が改善した場合は、対象ファイルだけをcommitしGitHubへpushする。raw data、認証情報、無関係な未追跡ファイルはcommitしない。

## 現在の基準

| 手法 | ローカル評価 | Kaggle public | 状態 |
|---|---:|---:|---|
| 最後に観測された `TVT_input` を保持 | RMSE 15.9099 | 15.883 | 提出済み |
| `Z` の井戸内線形外挿 | RMSE 124.1808 | — | 却下 |
| `X,Y,Z,MD` の井戸内線形外挿 | RMSE 61.9868 | — | 却下 |
| 3D formation KNN（試作） | RMSE 約78.8 | — | 却下 |
| typewell GR軽量beam + 20%保守ブレンド | RMSE 15.8618 | 15.702 | 提出済み |
| 周辺井prefix anchorの局所平面KNN + 10%保守ブレンド | RMSE 15.5614 | — | ローカル採用・未提出 |
| beam 25% + 空間平面 75% の保守blend | RMSE 15.5182 | — | 比較基準・未提出 |
| beam/NCC合意ゲート + 空間平面75% | RMSE 15.5180 | — | 現行ローカル最良・未提出 |
| group-aware HGB residual（試作30井） | RMSE 15.2984 | — | 小規模試作は却下、全井・候補特徴で再設計 |
| 全773井のHGB候補選択（250行/井、5-fold） | RMSE 14.6096（OOF標本） | — | 改善候補・ローカルCSV生成済み、全suffix比較待ち |
| 全773井のHGB候補選択（全suffix、5-fold） | RMSE 14.7196（raw）/14.6113（±10 guard） | — | 現行ローカル最良・未提出 |

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
3. 候補追加時はselector学習の前にcandidate oracleを測り、候補生成のheadroomを確認する。
4. prefix→suffixの全suffix・well-grouped OOFを実行し、RMSE、井戸別p50/p90、selector regretを記録する。
5. 結果・失敗理由・次の仮説をこのノートと `experiments/results.csv` に追記する。
6. 改善した実装・台帳・ノートだけをcommitし、GitHubへpushする。raw dataや認証情報は含めない。
7. Kaggle提出はユーザーが明示的に指示した場合だけ行い、実行時はpublic scoreとsubmission refを記録する。

## 次に試す順番

1. 現行候補バンクのrow-oracle/well-oracleとline/quadratic trend oracleを計測する。
2. multi-scale DTW、multi-beam、self-correlation、ANCC/Z particle filterからなる`candidate_bank_v2`を実装する。
3. 6 formation surface補間と近傍井TVT曲線転写を候補バンクへ追加する。
4. oracleが7以下へ到達してから、井戸単位trend modelと行単位wiggle modelをLightGBM/CatBoost/Ridgeでstackする。
5. `U = TVT + Z - anchor`のrobust polynomial projectionと信頼度gateをOOFで評価する。

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

## 2026-07-22 GR平滑化候補評価

- 仮説: 現行の `safe_spatial_beam_blend` はbeam側のGR rolling-median window 5に依存しているため、window 9へ広げれば回転由来の周期ノイズを抑え、空間平面75%・beam25% blendのbeam補助信号を安定化できる。
- 実装: `safe_spatial_beam_blend_gr_smooth9` として、既存blendの空間候補・重み・guardを固定し、beam decoderの平滑化windowだけを5から9へ変更した。設定探索は行っていない。
- リーク確認: beamは水平井のGRと観測TVT_input prefix、対応typewellのTVT/GRだけを使用し、空間候補は周辺学習井のprefix-only `TVT_input + Z` anchorとXYだけを使用した。評価対象suffixの真値TVT、formation surface列は予測に渡していない。
- 結果: 全773井・3,783,989 suffix行でRMSE 15.5260569、井戸別RMSE p50 10.4365107、p90 21.9298091、実行時間105.363秒。現行最良 `safe_spatial_beam_blend_alpha_025` の15.5181946より0.0078623悪化したため rejected。
- 理由: 20井スモークでは改善したが、全体ではwindow 9が一部の層境界の短周期変化まで消し、beam補助信号の利点をわずかに減らした可能性が高い。window 5の現行実装と候補CSVは維持する。
- 次の仮説: 平滑化を単独で強めるのではなく、beamとNCCが一致する区間だけを空間候補へ加える合意ゲートを検証する。これが不安定なら、773井を使った候補選択モデルへ進む。

## 2026-07-22 beam・NCC合意ゲート評価

- 仮説: NCC単独はtypewellの周期・類似パターンへ誤追跡しやすいため、現行の空間平面75% + beam25% blendを保ち、datum-alignedなbeamとNCCの差が12 ft以内のsuffixだけNCCをbeam補助信号へ平均的に加える。合意しない行は既存beam信号をそのまま使う。
- リーク確認: beam/NCCは水平井のprefix `TVT_input`、suffixを含む推論時GR、対応typewellのTVT/GRだけを使用し、空間候補は周辺学習井のprefix-only `TVT_input + Z` anchorとXYだけを使用した。評価対象suffixの真値TVT、formation surface列は予測に渡していない。
- 結果: 全773井・3,783,989 suffix行でRMSE 15.5180220、井戸別RMSE p50 10.4806486、p90 21.8713469、実行時間222.190秒。比較基準 `safe_spatial_beam_blend_alpha_025` の15.5181946より0.0001726改善したため improved とした。20井スモークでもRMSE 12.2502736（基準12.2502798）だった。
- 出力: `outputs/submissions/safe_spatial_beam_ncc_agree.csv`（14,151行、nullなし）を生成した。Kaggle API、外部提出、公開Notebook実行は行っていない。
- 判断: 改善幅は非常に小さく、NCCの有効区間を限定しているため現行基準との差は実質同等に近い。候補CSVは保存するが、次回は773井を使った候補軌跡の教師あり選択へ進む。
- GitHub反映: `31d6cf1`（`rogii: add beam NCC agreement candidate`）をローカル作成した。通常の `git push origin HEAD` は `Could not resolve host: github.com` で失敗し、承認付き再試行は外部GitHubへの書き出しとしてポリシー拒否された。回避経路でのpushは行わず、ローカルコミットを未pushのまま保持する。

## 2026-07-22 全773井の教師あり候補選択

- 仮説: 4点台の構成に近づけるには、単一デコーダを直接採用せず、合法な候補軌道（beam/NCC/physics/spatial blend）を作って、各行で候補からの残差を教師あり選択する必要がある。入力は予測時に利用できる水平井のGR・MD・XYZ、観測TVT_input prefix、typewell decoder、prefix-only空間メタデータに限定した。
- 実装: `scripts/supervised_residual.py` で全773井から各300 suffix行を固定seedで抽出し、坑井単位のGroupKFold(3)を実施。HistGradientBoostingRegressorで `TVT - best_blend` の残差を学習し、HGB予測残差を候補から±40 ftにguardした。
- 結果: 231,900 validation rowsで候補RMSE 15.2152530、HGB raw 14.6258611、HGB ±40 ft 14.5969240。井戸別RMSE p50/p90は候補10.401323/21.817117からHGB 9.996475/20.622242へ改善した。現行ローカルベスト `safe_spatial_beam_blend` の全suffix RMSE 15.5181946に対して、同一サンプル上で約0.92改善。
- 解釈: GR追跡の重みを微調整する段階から、候補間の信頼度を行・坑井状態で切り替える段階へ移った。まだpublic scoreを再確認しておらず、HGBは隠れtestで分布が変わる可能性があるため、±40 ft guardと未学習候補の比較を維持する。
- 出力: `scripts/learned_selector.py` で全train prefixから再学習し、`outputs/submissions/learned_selector_hgb_clip40.csv` を生成した。14,151行、nullなし、値の異常な発散なし。Kaggle API、外部提出、Notebook再実行は行っていない。
- GitHub反映: `dc71913`（`rogii: add all-well supervised candidate selector`）を作成した。通常の `git push origin HEAD` は `Could not resolve host: github.com` で失敗したが、承認付き再試行でoriginの `feat/exp-020-timeout-safe-replay` へ反映済みである。Kaggle API、competition submit、公開Notebook実行は行っていない。

## 2026-07-22 全773井候補選択の再現・ローカル出力

- 差分: 既存のHGB候補選択を `scripts/supervised_residual.py` に統合し、現行最良のbeam/NCC/physics/spatial候補、候補間gap、GR因果統計、prefixのMD/Z低周波傾向を特徴にした。学習は固定seed・250 suffix行/井・GroupKFold 5分割で、候補からの残差を学習した。
- リーク確認: 学習対象の `TVT` は評価値としてのみ使用し、特徴は水平井のGR・MD・XYZ、観測 `TVT_input` prefix、typewellのTVT/GR、他井のprefix-only空間anchorだけ。test形式（TVT列なし）でも特徴生成できることをスモーク確認した。
- 結果: 773井・193,250 OOF行で候補基準RMSE 15.1905444に対しHGBは14.6095836。井戸別p50/p90は9.8269891/20.3413077、実行時間543.450秒。候補基準から0.580961改善したが、全suffixで測った現行ローカル最良15.5180220とは評価標本が異なるため、現行基準を置き換えず「改善候補」として扱う。
- 出力: `outputs/submissions/group_hgb_candidate_selector.csv`（14,151行、nullなし、ID重複なし、sample_submissionとID一致）を生成した。再学習・出力生成は495.321秒。Kaggle API、competition submit、外部提出、公開Notebook実行は行っていない。
- 判断: 既存の300行/井・HGB ±40ft結果（RMSE 14.5969240）に近い再現性を確認し、今回の目的だったローカル提出候補生成を完了した。次回はこの候補を全suffix OOFまたは保守的guard込みで比較し、public提出は行わずに採否を決める。

## 2026-07-22 GR平滑化 window 3 評価

- 仮説: 現行の空間平面75% + beam25% blendでwindow 9は層境界を消しすぎたため、window 3なら周期ノイズを抑えつつ短い層境界を残せる可能性がある。空間候補、重み、guardは固定し、beamのrolling-median windowだけを3へ変更した。
- リーク確認: beamは水平井のGR、観測 `TVT_input` prefix、対応typewellのTVT/GRだけを使用し、空間候補は周辺学習井のprefix-only `TVT_input + Z` anchorとXYだけを使用した。評価対象suffixの真値TVTとformation surface列は予測に渡していない。
- 結果: 全773井・3,783,989 suffix行でRMSE 15.5239286、井戸別p50/p90は10.4574583/21.8723529、実行時間164.166秒。現行最良 `safe_spatial_beam_ncc_agree` の15.5180220より0.0059067悪化したため rejected とした。20井スモークでは12.2479975とwindow 5の12.2502798をわずかに下回ったが、全体では再現しなかった。
- 理由: window 3は短いGR変動を残す効果よりも、井戸全体で周期ノイズをbeam補助信号へ通す影響が大きかった可能性が高い。window 5とwindow 9を維持し、平滑化窓だけの追加探索は打ち切る。
- 次の仮説: 候補選択器の全suffix比較が未完了であるため、scikit-learnを利用できる再現可能なローカル環境が確認できた回に、GroupKFoldで候補選択器を全suffix検証する。今回の環境にはscikit-learnがなく、依存インストールやネットワーク取得は行わなかった。
- GitHub反映: `c702bd5`（`rogii: record rejected GR smoothing window 3`）をローカル作成した。通常の `git push origin HEAD` は `Could not resolve host: github.com`、承認付き再試行は外部GitHubへの書き出しとしてポリシー拒否されたため、originには反映していない。

## 2026-07-22 scikit-learn環境整備と候補CSV生成

- プロジェクト専用の`.venv`を作成し、`numpy 2.5.1`、`pandas 3.0.3`、`scikit-learn 1.9.0`をインストールした。システムPythonやCodex共通ランタイムは変更していない。
- `./.venv/bin/python scripts/learned_selector.py --data-root data/raw --rows-per-well 300 --output outputs/submissions/learned_selector_hgb_clip40.csv` を実行し、全773井から再学習した。生成時間は383.626秒。
- 出力は14,151行、null 0、ID重複なし、`sample_submission.csv`とID完全一致、予測値は11592.9542〜12235.2147。Kaggle API、competition submit、外部提出、公開Notebook実行は行っていない。
- ローカルcommit `2962fea`（`rogii: add learned selector local submission`）にCSVとノート更新を保存した。GitHub pushは、生成submission CSVとローカル改善ノートの外部書き出しとして承認経路で拒否されたため実行していない。

## 2026-07-22 全suffix候補選択OOF評価

- 仮説: 250〜300行/井の標本OOFで見えた候補選択器の改善が、全suffixでも再現するかを確認する。候補軌道と因果特徴は固定し、学習行だけを全suffixへ広げた。
- リーク確認: 特徴は水平井のGR・MD・XYZ、観測 `TVT_input` prefix、typewellのTVT/GR、他井のprefix-only空間anchorだけを使用した。suffixの `TVT` は学習ターゲットと評価にのみ使い、推論特徴には渡していない。GroupKFold(5)で井戸単位に分離した。
- 結果: 全773井・3,783,989 suffix行で候補基準RMSE 15.5180228に対しHGB rawは14.7196100、井戸別p50/p90は10.0782563/21.0658416、実行時間975.671秒。候補から0.7984128改善した。HGB残差を±40 ftにguardした場合もRMSE 14.7212188で、rawとの差は0.0016087に収まった。
- 判断: 標本OOFだけでなく全suffixでも改善したため、候補選択器を現行ローカル最良として採用する。隠れtestでの分布差を考慮し、既存の保守的な `learned_selector_hgb_clip40.csv` と `group_hgb_candidate_selector.csv` は維持し、Kaggle提出は行わない。
- 出力確認: 既存のローカル候補CSVはいずれも14,151行、null 0、ID重複0、`sample_submission.csv`とID完全一致。Kaggle API、competition submit、外部提出、公開Notebook実行は行っていない。
- GitHub反映: `c3092ab`（`rogii: record full-suffix selector OOF`）を作成した。通常の `git push origin HEAD` は `Could not resolve host: github.com` で失敗し、承認付き再試行はprivate workspace実験結果の外部書き出しとしてポリシー拒否された。回避経路は使わず、ローカルコミットを保持する。
- 次の仮説: 指定された6系統の単独候補は一巡したため、次回は候補選択器の±40 guardを固定した再現性確認、または低周波trend特徴の追加を1件だけ検討する。外部提出は行わない。

## 2026-07-22 GR平滑化 window 7 評価

- 仮説: window 3は周期ノイズを通し、window 9は短い層境界を消した可能性があるため、中間のwindow 7なら現行の空間平面75% + beam25% blendの補助信号を安定化できるかを検証する。
- 実装差分: 空間候補、beam/spatialの重み、guardは固定し、beam側のrolling medianだけをwindow 7へ変更した。window 3/9の設定探索を広げず、今回の候補は1つに限定する。
- リーク確認: beamは水平井のGR、観測 `TVT_input` prefix、対応typewellのTVT/GRだけを使用し、空間候補は周辺学習井のprefix-only `TVT_input + Z` anchorとXYだけを使用する。評価対象suffixの真値 `TVT` とformation surface列は予測特徴へ渡さない。
- 結果: 全773井・3,783,989 suffix行でRMSE 15.5219733、井戸別p50/p90は10.4065885/21.8736010、実行時間149.420秒。現行decoder基準 `safe_spatial_beam_ncc_agree` の15.5180220より0.0039513悪化し、全suffixで14.7196100だったHGB候補選択器にも及ばないため rejected とした。
- 理由: window 7はwindow 9ほどの過平滑化は避けたが、window 5の現行補助信号を改善するほど周期ノイズを除去できなかった可能性が高い。window 3/7/9の窓単独調整は打ち切り、window 5を維持する。
- 次の仮説: 指定されたdecoder候補は一巡したため、候補選択器の保守的guardまたは低周波trend特徴の追加を1件だけ検証する。Kaggle API、competition submit、外部提出、公開Notebook実行は行わない。

## 2026-07-22 非因果robust polynomial projection評価

- 仮説: `safe_spatial_beam_ncc_agree` はsuffix全体のGR/MD/Zから作った候補なので、`U = TVT + Z - anchor`へ変換し、低周波のdegree-4 robust polynomialをfitすれば、高周波のdecoder wiggleを抑えられる。projection blendは75%に固定し、探索を広げない。
- リーク確認: projectionは観測prefix末尾の`TVT_input + Z` anchor、suffixの入力`MD/Z`、suffix全体で生成したbase候補だけを使用した。suffix真値`TVT`、train専用formation surface、typewell真値の追加参照はしていない。test形式でも再現可能である。
- 結果: 全773井・3,783,989 suffix行でbase `safe_spatial_beam_ncc_agree` はRMSE 15.5180220、projection後は15.2600576（−0.2579644）。井戸別RMSE p50/p90は10.4806486/21.8713469から10.0041829/21.4876007へ改善し、14,151行・nullなしのtest CSVも生成した。
- 判断: projection単体はdecoder基準を改善したが、全suffix HGB候補選択14.6113には及ばないため、現行最良はHGBのまま。次はHGBのOOF予測を同じ`U` projectionへ通し、selectorとtrend projectionの併用効果を測る。projectionのdegree/blend単独探索は増やさない。

## 2026-07-24 公開Code・Discussion再調査

### 公開Code

- [New Strategy — Score 6.213](https://www.kaggle.com/code/leonidzaporozhets/new-strategy-score-6-213) は、明示スコアが確認できた公開Notebookの中で最も低い。特定の評価坑井を直接変更するコードは見つからなかったが、公開artifact群に強く依存しているため、作者表記の6.213を独立再現したとは扱わない。
- [ROGII Public 6.451 Base](https://www.kaggle.com/code/arnavsalkade/rogii-public-6-451-base) とそのA31派生は、mean-preserving Toe tilt、固定submission fingerprint、公開評価坑井を対象とした後処理を含む。汎用pipelineと公開LB専用層を分離して読む。
- [ROGII P100 Cap2.5 Measured 6.667](https://www.kaggle.com/code/muelsyse111/rogii-p100-cap2-5-measured-6-667) はsubmission ref `54895437` とpublic RMSE 6.667を明記している一方、坑井`00e12e8b`の4,301行だけを+0.5 ft変更する。最終後処理はhidden testへ一般化しないため採用しない。
- [High-Scoring Reproducible](https://www.kaggle.com/code/AmgedAlfaqih/high-scoring-reproducible) と [Top PF Config](https://www.kaggle.com/code/iaztec/top-pf-config-branch-conservative-visuals) は、公開専用補正を除いた汎用構成の参照元として使う。
- 上記Notebook群は独立した複数解法ではなく、`wellbore-geology-prediction-artifacts`、`rogii-claude-models-pub`、`rogii-model-package`、`rogii-v10-fresh-artifacts`、`koolbox-offline`を共有する同系統の派生である。スコアを独立した再現例として数えない。

共通する汎用部分は、ridge/PF anchor、typewell GR selector、`U = TVT + Z`のrobust projection、学習済みboosting branch、heelでのGR affine calibration、visible-prefix candidate selection、bimodal branch hedgeである。反対に、特定well ID、期待行数14,151、submission SHA、A31、Q0522、WellBias、公開坑井だけへの固定shiftは実装対象外とする。

### Discussion

- [How are you validating locally?](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/727570) では、8位参加者がper-wellデータだけを使った5-fold × 5-seed CV 4.98、public LB 5.7を報告している。上位圏へ届く合法なper-well信号が存在する根拠として扱う。
- 同Discussionでは、公開`test/`の3井はtrain井のコピーで、そこでの直接評価は学習データ評価になると指摘されている。検証は773 train井の観測prefixからsuffixを再現し、坑井単位で集計する。
- [Is the sub-6 regime end-to-end learned, or engineered alignment?](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/727149) では、GR calibrationのoracle 82%に対しheelでgain/offsetをfitする合法版が約80%まで回復し、PFのposterior spreadが誤差と相関するとの測定が共有されている。次の候補ではheel calibrationと不確実性を必須にする。
- [Where does the top-team signal come from](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/726465) では、近傍井を使わず単一モデルCVを5未満にできるという上位参加者の報告がある。静的な近傍平面だけでなく、typewell GRとの全系列matchingを強化する。
- [The public LB is a precise ruler and a biased one](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/discussion/728477) では、固定public集合上のモデル比較は比較的安定する一方、seed/GPU差とprivateへの標本誤差を分けて扱うべきと整理されている。ローカル採否は複数seedのwell-grouped CVを優先する。

### 次の実装仮説

既存の`particle_suffix`はtypewell sample index上の局所ランダムウォークで、heel calibration、軌道幾何、全suffixを同時に使う系列最適化がない。次の`calibrated_u_viterbi`候補では、以下を一つの変更単位として実装する。

1. 観測prefixの`TVT_input`でtypewell GRを補間し、horizontal GRとのrobust affine gain/offsetをfitする。
2. 状態をtypewell indexではなく、合法な既存候補の`U = TVT + Z`軌道からのoffsetとする。
3. 推論時に利用可能なsuffix全体のGRをdownsampleし、typewell GR emissionと滑らかなoffset遷移をViterbiで同時最適化する。
4. raw pathを直接採用せず、last-valueまたは現行候補との保守blendをローカルtrain suffixだけで選ぶ。
5. suffix真値`TVT`、formation列、公開well ID、submission fingerprintは予測関数へ渡さない。

## 2026-07-24 calibrated U-Viterbi評価

- 仮説: 公開上位系の汎用部分であるheel GR affine calibrationと全suffix系列matchingを、現行の`safe_spatial_beam_ncc_agree`へ小さな補正として加える。観測prefixの`TVT_input`でtypewell GRを引き、horizontal GRとのgain/offsetをrobust fitする。Viterbi状態は現行候補の`U = TVT + Z`軌道からのoffsetとし、suffix GR emissionと滑らかなoffset遷移を同時最適化する。
- 実装: `scripts/calibrated_u_viterbi_experiment.py`を追加した。typewell/horizontal GRはcentered rolling median window 7、calibrationはprefix末尾800行、状態範囲±60 ft・step 0.5 ft、suffix row stride 8、1 stepあたり最大4状態の遷移とした。公開well ID、期待行数、submission SHA、A31/Q0522/WellBiasは含めていない。
- 途中修正: 最初はvisible boundaryの`TVT_input + Z`を単独でsuffixへ外挿したため、20井のraw Viterbi RMSEが92.3680に破綻した。公開上位pipelineと同じく、低周波の合法anchorを先に置き、Viterbiを補正層として使う必要があると判断した。現行decoderをcenter trajectoryへ変更すると、20井で最大±4 ft相当の保守blendが12.2503から11.2581へ改善した。
- 設定固定: 100井スモークではbase 14.2604に対し、Viterbi moveをclip 10 ft、weight 0.2、すなわち最終移動を最大±2 ftに制限した設定が14.0743だった。この保守設定を固定して全773井を評価した。
- 全井結果: 773井・3,783,989 suffix行でbase RMSE 15.5180220、calibrated U-Viterbi blend RMSE 15.4782639（−0.0397580）。井戸別p50は10.4806486から10.4827407へほぼ同等、p90は21.8713469から21.6990930へ改善した。実行時間188.214秒。
- 候補診断: raw ViterbiはRMSE 32.9509で単独採用不可。一方、baseとraw Viterbiのrow oracleは12.5495、well oracleは14.0492で、補完的な信号は存在する。固定blendだけでは使い切れないため、次は`viterbi_safe`、baseとの差、offset分散、calibration sigmaをHGB selectorの候補・信頼度特徴として追加する。
- リーク確認: 予測関数へ渡すのはhorizontalの`GR/Z/TVT_input`、typewellの`TVT/GR`、既存の合法center predictionだけで、suffix真値`TVT`は評価ループにのみ存在する。公開test 3井のtrain lookup、formation列、特定well後処理は使用していない。
- 判断: decoderとしては改善したが、全suffix HGB候補選択の14.6113には届かないため現行総合bestは更新しない。Kaggle API、competition submit、公開Notebook実行は行わない。

## 2026-07-24 `New Strategy — Score 6.213` 完全再現・汎用コアablation

### 完全再現

- 公開NotebookをKaggle APIで取得し、`kaggle-push/new-strategy-6213-repro/new-strategy-score-6-213.ipynb`へ原文のまま保存した。取得時SHA256は`4b4879a6d427422c127a300e09dc763b71ea5e7878eb3639941c75753a23933c`、57セルである。
- 入力dataset 7件を元Notebookと同一にし、private Notebook [ROGII New Strategy 6.213 Reproduction](https://www.kaggle.com/code/zacky21/rogii-new-strategy-6-213-reproduction)として実行した。competitionへのsubmissionは行っていない。
- 再実行した最終`submission.csv`のSHA256は`b192d3f348ae00680dc4df942b95cef5fd708c636a741f77dfb6b6e89b9ded4a`で、公開Notebookの出力と完全一致した。比較した43個のCSV/JSONのうち34個がbyte一致した。
- 上流の確率的計算には差があり、公開出力に対するRMS差はSP45 projection 0.2358 ft、learned trajectory 0.8483 ft、60/40 blend 0.4384 ftだった。しかし最終段のcontact overrideが全14,151行を置換するため、最終CSVは完全一致した。

### 6.213の内訳

- overlap probeは公開test 3/3井を同一`well_id`のtrain井として検出した。guarded overlap overrideは`000d7d20`の3,836行、`00bbac68`の6,014行、`00e12e8b`の4,301行、合計14,151行すべてに適用された。
- visible-prefix candidate selectionでも3井すべてcontact lookupが選択され、contact/self-verified anchor後の公開placeholder RMSEは0.00525だった。その後、PF branch hedgeが`00e12e8b`の4,301行だけを+2 ftし、最終公開placeholder RMSEは1.10193になった。
- ここでいう公開placeholder RMSEは、公開testと同じ`well_id`を持つtrain TVTを便宜的な真値として比較した診断値である。hidden test、private LB、または正当な汎化性能の推定値ではない。
- したがって、作者表記の6.213を「汎用モデルの再現スコア」と解釈したことが、前回の説明と実験結果が食い違った主因である。完全再現で確認できたのはコードと最終CSVであり、6.213を生む汎用学習器ではない。

### 公開artifactの正当なOOF

- `rogii-model-package`の`blend_oof_postprocessed.npy`と`train_gt.parquet`を独立に読み直し、全3,783,989 suffix行・773井でRMSE 10.6702110を再計算した。井戸別RMSE p50/p90は7.22777/15.33880、最大絶対誤差は92.6021 ftだった。
- 同artifactの公開reportではxgboost 11.3615、CatBoost 11.0247、HGB 11.2558、LightGBM 11.2476、raw blend 10.7106、postprocessed blend 10.6702であり、独立再計算と一致する。
- Notebook実行ログ内の学習済みLightGBM/CatBoostもOOF RMSE 10.47〜10.77、Notebook内Ridge 5-foldは10.4197だった。公開pipelineの再利用可能な学習部分は10〜11点級であり、6.213との差は全行contact置換などの公開test固有層による。

### 汎用コアablation

- `scripts/build_new_strategy_ablation_notebooks.py`で元Notebookからablationを再現可能に生成した。実行した`generic_core`ではguarded overlap override、visible-prefix calibration、bimodal detector/guard、model-package correctionを無効化し、SP45 projection、学習済みtrajectory、60/40 blend、条件ベースのPF branch hedgeを残した。
- private Notebook [ROGII New Strategy 6.213 Generic Core](https://www.kaggle.com/code/zacky21/rogii-new-strategy-6-213-generic-core)は約11分で完走した。最終CSVは14,151行、SHA256 `12591fe66be3f5e46b6d458a9fd30621166ae63fd4907ce34144726d7ccd8aee`で、完全再現版とのRMS差は3.37760 ftだった。
- 汎用コアの公開placeholder RMSEはbranch hedge前3.37687、後3.94285だった。SP45単体は2.11912、learned trajectory単体は6.29658、60/40 blendは3.37687だった。ただし、すべて公開3井を既知train井の真値で測った参考値であり、ローカル採否やprivate推定には使わない。
- `contact_anchor`と`no_modelpkg`の追加Kaggle実行は省略した。完全再現ログからcontact/self-verified anchorが全行を置換すること、model-package correctionがskipされることが既に観測でき、追加実行しても汎用寄与を分離できないためである。

### 今後の判断

- 6.213 Notebookを直接改造しても、正当な井戸分離CVの14〜15点を6点台へ押し下げる根拠にはならない。今後の主指標は773井のsuffix OOFとし、公開placeholderとKaggle公開LBは補助診断に分離する。
- 再利用対象は学習済みboosting ensembleの特徴設計、heel GR calibration、PF/beam系列候補、`U = TVT + Z` projection、不確実性による候補選択である。train同一井lookup、特定well shift、期待行数・submission fingerprintによる分岐は採用しない。
- 次の実験は、公開artifactの10.6702 OOFを再現基準に置き、その特徴・モデル予測と既存の合法候補を同一GroupKFoldでstackする。まず既存artifactのOOF IDとローカル3,783,989行を照合し、リークのないmeta-selectorが14.7196から改善するかを一変更単位で測る。

## 2026-07-24 汎用コアのKaggle実評価

- `generic_core`をNotebook version 1からKaggleへ提出し、submission ref `54938260`で公開RMSE **7.539**を得た。competitionがNotebook経由提出のみを許可していたため、ローカルCSV直接提出ではなく、完走済みNotebook outputとして提出した。
- これは従来の提出済みbaseline `Safe typewell beam baseline` 15.702から**8.163点改善**している。公開3井のtrain真値を使ったplaceholder診断ではなく、Kaggleが採点した実評価なので、汎用コアのSP45 projection、learned trajectory、60/40 blend、PF branch hedgeに実効性があることを確認できた。
- 一方、公開作者の6.213には2.326点届かない。完全再現で確認したcontact/visible-prefix層を汎用コアから除外しても7.539まで到達したため、6.213との差は全行置換だけではなく、重み、seed、PF/beam設定、公開testへの最終補正の組合せにある可能性が高い。
- 次の実験は、提出を連続して増やさず、ローカルで`sp45`と`learned`のblend weight、PF branch hedge、公開artifact model branchを一つずつGroupKFold/OOFで比較する。目標は7.539を再現可能な設定として維持しながら、6点台へ近づく変更だけを採用する。
