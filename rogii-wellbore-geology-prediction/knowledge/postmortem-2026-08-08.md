# ROGII Wellbore Geology Prediction ポストモーテム

作成日: 2026-08-08 JST

## 1. 結果の要約

チーム `yamazaking`（Kaggle user `zacky21`）の確定結果は次の通り。

| 指標 | 結果 |
|---|---:|
| 参加チーム数 | 6,125 |
| public best | 7.474 |
| public順位 | 2,608位 / 6,125（上位42.6%） |
| final/private score | 9.216 |
| final順位 | 665位 / 6,125（上位10.9%） |
| final 1位 | Ruby、5.639 |
| 1位との差 | 3.577 |

public順位はKaggleから2026-08-08に取得したpublic leaderboard CSV、final順位は同日の公式APIをページ走査して確認した。final score 9.216はsubmission ref `54938260`のprivate scoreと一致する。APIは最終選択フラグを返さないため、最終採用submissionの特定はこの一致に基づく推定である。

初期のlast-value baselineはpublic/private 15.883/14.488だった。最終score 9.216まで大幅に改善できたこと、リークを含む公開6点台コードをそのまま最終候補にしなかったことは成果である。一方、最終順位はメダル圏のすぐ外側で、モデル開発よりも最終submission選択の失敗が明確に残った。

## 2. 提出履歴

| Ref | 候補 | Public | Private | 判断 |
|---:|---|---:|---:|---|
| 54875928 | Last known TVT | 15.883 | 14.488 | 初期baseline |
| 54876671 | Safe typewell beam | 15.702 | 14.281 | 小幅改善 |
| 54938260 | Generic core | 7.539 | **9.216** | final scoreと一致 |
| 54991701 | SP45 Ridge30 selector70 | 7.894 | 9.994 | 悪化 |
| 55001998 | Generic core d2/b0.50 | **7.474** | 9.286 | public best |
| 55053043 | All13 learned meta | scoreなし | scoreなし | Notebook例外 |
| 55072030 | Dynamic all12 | 9.599 | 9.791 | 大幅悪化 |
| 55101733 | Complete-well 0.08-class | 7.625 | **9.074** | 全提出中private best |
| 55138088 | Field K6 guarded | 7.577 | 9.236 | public改善、private悪化 |
| 55171520 | Artifact15 centered | 7.784 | 9.164 | privateは比較的良好 |

重要な事実は、public best 7.474がprivateでは9.286であり、publicで0.151悪かったComplete-well 7.625がprivateでは全提出中最良の9.074だったことである。private leaderboardのスコア分布に9.074を当てはめると約546位相当で、実際の665位より約119位高い。6,125チームの単純な上位10%線は約613位なので、最終候補を明示的に選んでいればメダル圏相当へ入った可能性があった。ただし、これは終了後のprivate scoreを使った事後分析であり、当時その順位を保証できたわけではない。

## 3. 良かった点

### 3.1 リークを識別して隔離できた

公開Notebook `New Strategy — Score 6.213`を完全再現し、公開test 3井と同じIDのtrain井を使うcontact overrideが14,151行すべてを置換していることを確認した。6.213を汎用モデル性能と誤解した初期判断は修正し、same-well contact、固定well shift、submission fingerprint分岐を最終戦略から除外した。

### 3.2 実験の再現性をかなり高めた

Notebook SHA256、submission SHA256、行数、ID順、NaN、Kaggle runtimeの出力一致を記録した。Kernel outputを使うCode Competition特有の提出経路も最終的には再現可能になった。

### 3.3 baselineから大きく改善した

last-valueのprivate 14.488からgeneric coreの9.216まで5.272改善した。PF/beam、`U = TVT + Z` projection、learned trajectory、branch hedgeを組み合わせる方向は有効だった。

### 3.4 終盤は小さなローカル改善を無条件に提出しなかった

7.625、7.577、7.784でローカル改善とpublic悪化の反転を観測した後、0.1 ft未満の改善に厳しいeffect gateを設けた。これは追加の無駄な提出を抑える判断として妥当だった。

## 4. 反省点

### 4.1 最終submissionを明示的に選ばなかった

最大の運用ミスである。public上位の7.474と7.539を最終候補として残した結果、final scoreは9.216になった。一方、Complete-wellはprivate 9.074、Artifact15は9.164だった。終了前に「public順位ではなく、ローカルの空間耐性とモデル多様性で2本を選ぶ」作業を完了していれば、Complete-wellを少なくとも片方に選ぶ合理的な余地があった。

再発防止:

- 締切24時間前に新規実験を凍結する。
- final 2本の選択表を作り、モデルfamily、CV、LSO、public、分布差、相関を並べる。
- Kaggle画面で選択状態を確認し、スクリーンショットまたはAPI監査ログを残す。
- public上位2本の自動選択に任せない。

### 4.2 public leaderboardを強く信頼しすぎた

public 7.474はprivate 9.286へ1.812悪化した。後期5候補のprivateは9.074〜9.791付近に集まる一方、publicは7.474〜9.599まで大きく動いた。public 3井は全体分布の代表ではなく、特定構造や後処理に敏感だった。

Complete-wellを「7.625なので失敗」と結論づけたのはpublic中心の判断だった。終了後に見ると、これは最もprivate耐性の高い提出だった。publicは実装確認と大事故検知には使えるが、汎化順位の主指標にすべきではなかった。

再発防止:

- public scoreは採否基準ではなく、弱い補助観測に限定する。
- public改善とCV改善が食い違った場合は、CV/LSOを優先する。
- public差0.1〜0.3をモデル優劣と断定しない。

### 4.3 CVがhiddenの空間分布を十分に再現していなかった

主に坑井単位のランダムGroupKFoldとsuffix OOFを使った。坑井リークは防げても、近接井・同一field・類似軌跡がtrainとvalidationへ分散し、空間的な一般化を過大評価する可能性が残った。field nested検証は終盤に追加したが、評価契約の中心にはならなかった。

公開writeupでは、重複・近接twinsを除いた762井の5-fold GroupKFoldに加えて、空間blockを丸ごと外すLSOが重要だったと報告されている。私たちもこれをコンペ序盤に固定すべきだった。

再発防止:

- 重複井・近接井・同一軌跡を先にcluster化する。
- `GroupKFold by well`、`leave-spatial-block-out`、`field holdout`の3指標を固定する。
- 候補昇格には3指標中2つ以上の改善と、最悪blockの非悪化を要求する。

### 4.4 ローカルproxyと実提出pipelineが一致していなかった

7.474のproxyと呼んだローカル評価は、Kaggle NotebookのPF seed、hedge、learned branch、runtime artifactを完全には再現していなかった。Dynamic all12ではKaggleで効いていたhedgeを後段で上書きし、ローカル8.8945に対してpublic 9.599となった。Complete-well、Field K6、Artifact15もローカル約0.08改善がpublicでは反転した。

「同じbase上の差分比較」だけでは、hidden環境で枝の統計が変わると符号が反転する。候補の最終比較は、同一Notebook・同一runtime・同一seed pathで、変更箇所だけを差し替える必要があった。

再発防止:

- incumbent Notebookを関数化し、ローカル/クラウドで同じコードを実行する。
- proxyではなく、全componentのOOFとtest統計を同じcontractで保存する。
- candidateとincumbentの差分だけでなく、各branchの分布移動を必須監査する。

### 4.5 小幅な補正モデルを作りすぎた

7.474以降、Savgol、well bias、field routing、matcher、artifact blend、toe gateなど、0.01〜0.11 ft級の補正を多数試した。これらは同じ誤差構造の周辺探索であり、1位private 5.639との差3.577を埋める規模ではなかった。

上位へ近づくには、PFの観測ノイズ、aliasing、uncertainty-aware offset、空間構造、系列モデルなど、誤差の主要因を変える実験へ早く移るべきだった。公開PF writeupでは`gs_floor=45`、PF uncertainty、offset correctionが大きな段差を作ったと報告されている。私たちは`gs_floor=45`を終了直前に40井だけ試し、投影RMSE 14.0561から13.6888へ改善したが、全773井検証を完了できなかった。このpilotは有望な仮説であって、確定結果ではない。

### 4.6 公開Codeの追跡に時間を使いすぎた

6.213の完全再現、複数Notebookのsanitizer、artifactの再現には価値があったが、公開スコアの内訳解明へ多くの時間を使った。公開Notebookにはcontact lookup、固定well、固定shift、壊れた依存関係が多く、汎用部分の抽出コストが高かった。

再発防止:

- 公開Codeは最初に静的リーク監査し、失格なら深追いしない。
- 再利用するのは新しい特徴・物理モデル・検証法に限定する。
- 1本の再現に使う時間上限を事前に決める。

### 4.7 計算と実験管理が重かった

773井PF OOFが12,000秒を超えた実行、Kaggle Kernelの待ち時間、ローカルの長時間runがあり、結果が出るまで次の判断が止まった。`/private/tmp`の大きなcacheに依存し、実験結果の一部がリポジトリ外に残った。`learning-notes.md`は詳しい一方、1ファイルが巨大化し、最終候補一覧を即座に判断しにくかった。

再発防止:

- 50井pilot、200井confirm、全井finalの三段階gateを固定する。
- 各段階にeffect thresholdと時間上限を設ける。
- 予測componentを再利用可能なparquetへ一度だけ保存する。
- `experiments/results.csv`を唯一の索引とし、ノートは実験IDから参照する。
- 一時cacheではなく、必要なsummaryとmanifestをGit管理する。

### 4.8 提出経路の理解と説明が不十分だった

private Kernelへのpushとcompetition submissionを混同し、ユーザー画面に提出が見えない状態を一度作った。Notebook例外、認証状態、約5時間の採点待ちもあり、提出済み・実行中・採点待ちの状態説明が曖昧になった。

再発防止:

- 状態を `local candidate`、`kernel pushed`、`kernel complete`、`competition submitted`、`scored` の5段階で表示する。
- submission refが発行されるまで「提出済み」と言わない。
- 最終CSVのSHA、Kernel version、submission refを1レコードにまとめる。

### 4.9 私の判断基準と説明にも問題があった

私は何度か、0.08 ft前後のローカル改善を「提出できるレベル」と表現した。しかし過去のlocal/public反転を踏まえると、根拠は弱かった。また、`New Strategy 6.213`を当初は汎用モデルの到達点のように説明し、後からcontact全行置換を確認して訂正した。長時間runについても、早めの停止条件と進捗見積りを示すべきだった。

今後は、候補について必ず次の3点を分けて伝える。

1. ローカルで改善した事実。
2. hiddenへ一般化すると考える根拠。
3. Kaggleへ提出する価値があるかという意思決定。

## 5. 上位解法との差

終了時点で確認できた公開writeupから、上位へ近い解法には次の共通点がある。

- TVTを単純な表形式回帰ではなく、坑井に沿った系列・状態推定として扱う。
- `U = TVT + Z`の物理的な平滑性を利用する。
- GR/typewell対応のaliasingと多峰性を明示的に扱う。
- PF seed/particle spreadを不確実性として利用し、補正量を減衰する。
- ランダムwell CVだけでなく、空間block holdoutを重視する。
- per-well routingのような空間自己リークを棄却する。

私たちのgeneric coreにもPF、U projection、learned branchは入っていたが、PF不確実性を学習補正へ一貫して接続できず、空間CVも主契約にできなかった。終盤は主要構造を変えるより、既存trajectoryへの微修正が中心になった。この差がprivate 5点台との大きな隔たりとして残った。

参考:

- [ROGII final leaderboard](https://www.kaggle.com/competitions/rogii-wellbore-geology-prediction/leaderboard)
- [Working Note: Our Solution, the Failures Behind It, and What the Data Taught Us](https://www.kaggle.com/writeups/daulettoibazar/working-note-our-solution-the-failures-behind-it)
- [Bayesian Geosteering for ROGII: Particle Filters and Alias-Aware TVT](https://www.kaggle.com/writeups/rameshln/bayesian-geosteering-for-rogii-particle-filters-a)

## 6. 次回コンペの実行原則

1. 初日にリーク監査、重複cluster、GroupKFold、空間LSOを固定する。
2. baseline Notebookとローカル評価を同一コードパスにする。
3. 実験は「仮説1つ、変更1つ、時間上限1つ」で行う。
4. 50井pilotで0.1未満の効果なら原則停止する。
5. 全井昇格には複数seed、bootstrap、空間block非悪化を要求する。
6. public LBは実装確認に使い、モデル選択はCV/LSOで行う。
7. 最終候補は異なるfamilyから2本選び、締切24時間前に手動確定する。
8. `kernel pushed`と`competition submitted`を明確に分ける。
9. 実験索引、コードSHA、出力SHA、提出refを1つの台帳に残す。
10. 上位との差が大きいときは微調整を止め、誤差構造を変える仮説へ移る。

## 7. 結論

このコンペでは、baseline 14点台からfinal 9.216まで進み、リークを含む公開手法を識別する力と再現性のある提出基盤を得た。一方、privateで最良だった9.074の候補をfinalに選ばず、実順位は665位となった。最大の反省は「publicで最も良いモデルを残すこと」と「hiddenで最も頑健なモデルを選ぶこと」を分離できなかった点である。

次回はモデル改善と同じ重さで、空間CV、候補多様性、最終選択を設計する。今回の技術的な学び以上に、この選択プロセスを再現可能にすることが最も重要な改善である。
