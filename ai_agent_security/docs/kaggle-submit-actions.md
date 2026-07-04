# GitHub Actions Kaggle Kernel Push Flow

## 概要

`main`へpushするとCIが走ります。変更ファイルが
`ai_agent_security/kaggle-push/<exp>/`直下の提出用ファイルだった場合だけ、
CI成功後にKaggleへkernel versionをpushします。

> 注意: このcompetitionでは `kaggle competitions submit -k ... -v ...`
> を使うと、hosted evaluator rerunではなくkernel outputの
> `submission.csv` を静的に提出してしまい、`Submission Format Error`に
> なります。APIで行うのはkernel pushと完了確認までにし、最終提出は
> Kaggle Notebook画面右側の **Submit to Competition** から行います。

提出対象として見るファイル:

- `kernel-metadata.json`
- `*.ipynb`
- `*.py`
- `*.R`
- `*.Rmd`
- `*.sql`
- `*.jl`

`kaggle-push/<exp>/output/`などのネストした実行結果は提出トリガーにしません。

## 必要なGitHub Secret

Repository settingsのActions secretsに以下を登録します。

```text
KAGGLE_API_TOKEN
```

Kaggle SettingsのAPI画面で発行したtoken文字列をそのまま入れます。

## 自動push

1回のpushで変更できる提出bundleは1つだけです。

例:

```text
ai_agent_security/kaggle-push/exp-007/kernel-metadata.json
ai_agent_security/kaggle-push/exp-007/exp-007-phase-a-boost.ipynb
```

CIが成功すると、workflowは以下を実行します。

```bash
kaggle kernels push -p ai_agent_security/kaggle-push/<exp>
kaggle kernels status <kernel>/<version>
kaggle kernels files <kernel>/<version>
```

`submission.csv` がoutputにあることを確認したら、Kaggle Notebook画面で
該当versionを開き、右側パネルの **Submit to Competition** からnotebook自体を
提出します。output tabの`submission.csv`を提出しないでください。

## 手動push

Actionsの`CI and Kaggle Submit` workflowを手動実行し、`exp_id`に
`exp-007`のような`kaggle-push`配下のディレクトリ名を指定します。

## ローカル確認

```bash
python3 ai_agent_security/scripts/validate_submission_bundle.py \
  ai_agent_security/kaggle-push/exp-007

python3 ai_agent_security/scripts/submit_kaggle_kernel.py \
  ai_agent_security/kaggle-push/exp-007 \
  --message dry-run \
  --dry-run
```
