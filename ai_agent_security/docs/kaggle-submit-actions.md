# GitHub Actions Kaggle Submit Flow

## 概要

`main`へpushするとCIが走ります。変更ファイルが
`ai_agent_security/kaggle-push/<exp>/`直下の提出用ファイルだった場合だけ、
CI成功後にKaggleへ提出します。

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

## 自動提出

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
kaggle competitions submit ai-agent-security-multi-step-tool-attacks \
  -f attack.py \
  -k <kernel> \
  -v <version> \
  -m "<exp> github:<sha>"
```

## 手動提出

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
