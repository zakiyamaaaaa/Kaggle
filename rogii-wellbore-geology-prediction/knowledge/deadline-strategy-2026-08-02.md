# ROGII 締切前実験戦略 v2 — 2026-08-02

> この文書は同日作成した初版を置き換える。初版でP0とした`New Strategy 6.213`完全版は、公開testとtrainの同一well contactを全行へ適用するため、private耐性を優先する計画の主候補から除外した。

## 結論

残り期間の基準はpublic 7.474の`full generic core d2/b0.50`とする。この提出ではsame-well contact、visible-prefix overlay、bimodal detector、model-package correctionがすべて明示的に無効化されており、公開well ID固有shiftも使っていない。

今後は次の3本に限定する。

1. 公開6点台Codeから、contact・固定well・submission fingerprintを除いても成立するcoreを1本だけ完全再現する。
2. 7.474のSP45/learned二枝に対し、toe区間だけを対象にした低次元confidence gateを1本だけ作る。
3. 1と2の双方がKaggleで改善した場合だけ、異系統固定weight ensembleを1本作る。

6.213完全版は提出しない。ローカルで0.01〜0.10ft改善する既存artifact、field、matcherの再調整も行わない。

## 現状と目標

| 項目 | 状況 |
| --- | --- |
| 締切 | 2026-08-05 23:59 UTC、2026-08-06 08:59 JST |
| 提出上限 | 1日5回 |
| 採点待ち | 約5時間 |
| 現行best | 7.474、rank 2,457前後 |
| 第一目標 | 6.417以下、rank 600前後の目安 |
| 第二目標 | 6.371以下、rank 300前後の目安 |
| stretch | 5.308以下、rank 10前後の目安 |

score境界は2026-08-02 21:22 JSTのKaggle API snapshotであり変動する。残り約3日で5点台前半へ到達するには、7.474の小幅補正ではなく、公開済みの強い汎用coreを正確に移植する必要がある。

## 過学習リスクの区分

### 失格 — final候補にしない

- testと同じ`well_id`のtrain TVT・contact・formationをlookupする。
- `000d7d20`、`00bbac68`、`00e12e8b`など公開well IDへ分岐する。
- 14,151行、既知submission SHA、既知CSVを条件に予測を変える。
- 特定wellへの固定shiftをpublic scoreで選ぶ。
- public testのtrainコピーを真値としてweight、閾値、branchを選ぶ。

`New Strategy 6.213`完全版はcontact overrideで14,151/14,151行を置換し、その後1井へ固定branch shiftを加えるため、この区分に置く。公開スコアの再現性はあっても、汎用モデルの6.213とは解釈しない。

### 条件付き適格

- 公開artifactやpretrained modelを使うが、学習時OOFとtest inferenceのID契約を監査できる。
- 観測済み`TVT_input` prefix、水平井GR、typewell、坑跡だけを使う。
- target-freeなPF hedgeやuncertainty gateを使う。
- 公開Code由来の固定parameterを使うが、public scoreを見たwell別再調整をしない。

### 現行適格基準

7.474 Notebookは起動時に次を強制的に無効化している。

- `run_guarded_overlap_override=False`
- `run_visible_prefix_calibration=False`
- `run_bimodal_detector=False`
- `run_vp_bimodal_guard=False`
- `run_model_package_correction=False`

残る構成はSP45 Ridge30/Selector70、`U=TVT+Z` projection d2/b0.50、learned trajectory 40%、target-free PF branch hedgeである。これを変更しないcontrolとする。

## 実験P0 — 公開6点台Codeのclean-core監査

対象は公開表示6.568、6.710、6.858、6.928の4系統。Notebook title scoreではなくcode、dataset、最終出力を比較する。

### 監査項目

1. 全code cellを抽出し、失格条件のwell ID、contact、row count、SHA、固定shiftを検索する。
2. 失格層を無効化した時点の最終CSVを生成する。
3. 7.474とのRMS差、相関、well別差、各componentの寄与を保存する。
4. 7.474と同じhidden-dynamic runtimeで完走できるか確認する。
5. clean coreに公開された実スコアがあるか、推測値ではなくsubmission履歴で確認する。

### 昇格

- clean core単独の公開実績が7.20以下で、sourceを完全再現できる候補を最優先する。
- 複数候補が同じcontact/artifact pipelineなら、最もsource provenanceが明確な1本だけ残す。
- 4系統すべてが失格層を除くと7.474相当または悪化なら、公開Code forkは2026-08-03中に終了する。

公開スコア付きclean coreの完全再現は、ローカルOOFとの絶対値対応が取れなくても1回だけ提出できる。ただしsourceから複数箇所を変更した候補にはこの例外を使わない。

## 実験P1 — toe-aware continuous confidence gate

公開solution noteでは、遠いtoe区間が二乗誤差の大半を占め、離散的な候補選択よりcontinuous regressionと候補間disagreementが有効と報告されている。この汎用部分だけを7.474へ加える。

### 固定する設計

- baseは7.474のSP45 60%＋learned 40%＋PF hedge。
- 変更するのはSP45/learnedの混合率だけで、候補軌道を増やさない。
- 補正対象はsuffix後半40%のtoe区間。heel側は7.474をそのまま使う。
- 入力はnormalized MD、SP45/learned差、PF spread、prefix GR fit誤差、GR alignment sharpness、軌道curvatureだけ。
- 低次元Ridgeでcontinuousな混合率補正を予測し、基準weightからの変化を±0.10、最終移動を±1.5ftに制限する。
- outer well-group CVのvalidation井は、model fit、scale、clip、採否閾値の選択から完全に外す。
- parameter gridは正則化3値、shrink 3値まで。特徴追加やfield別modelへ広げない。

### ローカル昇格条件

直近3候補では、ローカル予測とpublic差分が0.18〜0.39ftずれた。従来の0.08ft gateは弱すぎるため、novel candidateは次をすべて満たす場合だけ提出する。

1. repeated well-group CVのpooled RMSEを0.25ft以上改善する。
2. 50,000 well bootstrapの改善p01が+0.05ft以上。
3. 事前固定したlegacy splitすべてで改善し、field別最大悪化が0.03ft以下。
4. toe後半40%で0.30ft以上改善し、heel側を0.02ft以上悪化させない。
5. artifact/HGB/Ridgeの3 proxyすべてで0.10ft以上改善する。
6. hidden入力で補正符号・scaleがOOF範囲外にならず、p95移動1.0ft以下、最大1.5ft以下。

0.10〜0.25ftの改善は研究結果として記録するが、締切前の提出候補にはしない。

## 実験P2 — continuous matcher公開解法の再現

P0監査でcontact-freeな7.2以下が見つからず、P1を2026-08-03中に完了できた場合だけ着手する。

- 公開solution noteのcontinuous matcher＋boosted combinerを、利用可能なsourceがある場合だけ再現する。
- 実装時間を6時間でtimeboxする。
- raw Viterbiは既にOOF 32.95で失敗しているため再実装しない。
- spatial cluster/geology補正は公開失敗報告と既存ローカル結果の両方が否定的なので使わない。
- source不足で新規architecture設計が必要になった時点で中止する。

P2も失格条件とP1のローカル昇格条件を満たす必要がある。

## 実験P3 — 異系統ensemble

次の条件をすべて満たす場合だけ1本作る。

- P0/P1/P2のうち2本がKaggleで7.474を0.05以上改善している。
- 2本の予測差RMSが0.5ft以上あり、単なる乱数違いではない。
- 両Notebookを同じhidden runtimeで動的に再現できる。
- weightは0.75/0.25と0.50/0.50だけ比較し、提出は1本だけ。

well別weight、公開scoreに合わせたglobal shift、3本以上のblendは行わない。

## 日程と提出枠

### 2026-08-02 JST

- 7.474の適格性監査を確定する。
- P0の4候補を静的監査し、clean core候補を1本へ絞る。
- Kaggle提出はしない。

### 2026-08-03 JST

- 午前: clean public coreが存在すればS1として1本提出する。
- 採点待ち: P1を実装・nested CV評価する。
- S1の結果が7.474より悪ければ、その公開familyの派生を停止する。
- P1が全gateを通った場合だけ、夕方までにS2として提出する。

### 2026-08-04 JST

- P0/P1の結果を確認する。
- 改善候補がある場合だけP2またはP3を最大1本提出する。
- 18:00 JSTまでに7.474を上回る適格候補がなければ、新規model実験を終了する。

### 2026-08-05 JST

- 新規architectureとparameter探索は禁止。
- 実行エラー修正、完全再現、または既に改善した2候補のP3だけを扱う。
- scoreが締切前に返るよう、最後の新規提出は22:00 JSTまでとする。

### 2026-08-06 JST

- 03:00以降は新規提出しない。
- 07:30までに全候補のscore、risk区分、Notebook version、出力SHAを確定する。
- 08:00までにfinal 2 submissionsを選択し、08:59直前の操作を避ける。

1日5枠を使い切らない。1 waveは原則1本、1日最大2本とし、常にエラー再実行用の枠を残す。

## public結果による判断

| 結果 | 判断 |
| --- | --- |
| 7.20以下かつ適格 | 新incumbent。別familyへ移り、同系統の微調整はしない |
| 7.20〜7.42 | 改善候補として保持。独立候補またはensembleを優先 |
| 7.42〜7.52 | 実質同等。乱数差を疑い、派生提出を止める |
| 7.52超 | familyを停止し、原因監査だけ記録 |
| 実行失敗 | 同一sourceの修正再実行は1回まで |

## 最終2枠

候補を次の順で選ぶ。

1. 失格条件を含まない候補のうち最高public。
2. 1と異なる予測familyで、失格条件を含まない最高候補。

6.213完全版はfinal候補から除外する。新規候補が7.474を更新しなければ、既存7.474とgeneric core 7.539をfallbackとする。2本目のpublic scoreが少し悪くても、同一familyの乱数違いより構造的に異なる候補を優先する。

## 次の改善ループ

最初にP0のstatic sanitizer tableを作る。4つの公開Notebookについて、contact、固定well、row/SHA分岐、固定shift、clean-core出力、7.474との相関を同一表へまとめる。その結果から1本だけ実装対象を選び、同時にP1の特徴とCV foldをコード上で事前固定する。
