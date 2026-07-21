# ROGII - Wellbore Geology Prediction

ROGII の水平坑井地質予測コンペ用の作業フォルダです。

## 調査メモ

- 目的変数は水平坑井の `TVT`（True Vertical Thickness）。
- 水平坑井ファイルには `MD`, `X`, `Y`, `Z`, `GR`, `TVT_input` などがあり、`TVT_input` は Prediction Start まで既知、それ以降は欠損です。
- 各水平坑井には `typewell` の `TVT`, `GR`, `Geology` が対応します。
- 予測対象は `TVT_input` が欠損している行です。
- 提出形式は `id,tvt`、評価指標は RMSE です。
- 公式データページでは `train/`, `test/`, `sample_submission.csv` が提供されています。データはコンペ規約への同意後に取得できます。

取得データの実測：`train/` は水平坑井773本・5,092,255行、`test/` の公開サンプルは3本・19,221行でした。学習側には水平坑井CSV、typewell CSV、PNGが各773本あり、typewell列は `TVT`, `GR`, `Geology`、水平坑井列は `MD`, `X`, `Y`, `Z`, `GR`, `TVT`, `TVT_input` と地質トップ列です。学習データの評価区間（`TVT_input` 欠損）は3,783,989行でした。

## ディレクトリ

```text
data/raw/       Kaggleから取得した train/, test/, sample_submission.csv
data/processed/ EDA・中間生成物
outputs/        検証結果と提出ファイル
scripts/        再現可能なスクリプト
knowledge/      Discussion・Code・実験結果を蓄積する学習ノート
experiments/    実験台帳
```

## ベースライン

`TVT_input` の既知区間の最後の値をPrediction Startより先へ固定して延長します。学習データの評価区間を使った比較では、線形外挿よりこの末尾値固定の方が安定しました。これは typewell や GR をまだ使わない、提出形式と評価の動作確認用ベースラインです。

末尾値固定の学習評価区間RMSEは `15.909853`（3,783,989行）でした。比較対象の単純な線形外挿はRMSE `117.285798` となり、長い予測区間で発散しました。

```bash
source ../.venv/bin/activate
python scripts/inspect_data.py --data-dir data/raw
python scripts/baseline.py --data-dir data/raw --submission-path outputs/submissions/last_value_baseline.csv --validate
python scripts/advanced_baseline.py --data-root data/raw --method safe_beam --evaluate
python scripts/advanced_baseline.py --data-root data/raw --method safe_beam --output outputs/submissions/safe_beam_baseline.csv
```

## 現在の提出結果

typewellのGR波形をbounded beam searchで追跡し、最後の `TVT_input` からの補正を20%だけ採用する `safe_beam` を実装しました。全773井・3,783,989 suffix行のローカルRMSEは `15.861771`、Kaggle public scoreは `15.702`（submission ref `54876671`）です。末尾値固定のpublic score `15.883`から改善しています。

改善の根拠と次の実験は [knowledge/learning-notes.md](knowledge/learning-notes.md)、全実験の数値は [experiments/results.csv](experiments/results.csv) に記録しています。

Kaggle提出用のコマンド例：

```bash
KAGGLE_CONFIG_DIR=/Users/shoichiyamazaki/Downloads python -m kaggle competitions submit \
  -c rogii-wellbore-geology-prediction \
  -f outputs/submissions/linear_extrapolation.csv \
  -m "Linear extrapolation baseline"
```

## 次の改善候補

1. GRの移動統計量・差分・自己相関を追加する。
2. typewell の GR-TVT 波形との相互相関でTVT位置を推定する。
3. `X,Y,Z` から方位・傾斜・曲率・3D tortuosityを作る。
4. 井戸単位の時系列holdoutで、単純なランダム分割を避けて比較する。
