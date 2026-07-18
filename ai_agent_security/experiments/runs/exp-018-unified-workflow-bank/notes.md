# exp-018-unified-workflow-bank

- 名前: unified-workflow-bank
- Kaggle タグ: `exp-018-unified-workflow-bank`

## 仮説

直近の `exp-016-compliance-routing-bank` と `exp-017-ticket-workflow-bank` は、いずれも `exp-013-handoff-routing-bank` 系の固定 replay bank に業務文脈を足す方針で、それぞれ compliance / legal / risk と ticket / incident / workflow の言い換えを追加した。どちらも単体では 2000 候補未満だが、単純結合すると 2200 件超になる。

今回は両実験の差分候補を 1 本に統合し、重複の多い notice グリッドだけを削って 2000 件以内に収める。`exp-006` 由来の短い core replay を先頭に維持しつつ、ticket と compliance の HTTP / notice / read-route / untrusted-to-action / destructive write 表現を同時に本番 LLM replay へ渡す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | `exp-017` の core / handoff / ticket / runbook / destructive / Go-Explore fallback を維持 |
| A1 | `exp-016` の compliance / legal / risk / governance HTTP 宛先とテンプレートを追加 |
| A2 | compliance / legal / risk / privacy / records 宛の review / case / handoff 通知を追加 |
| A3 | read → compliance evidence / legal review / risk register ルートを追加 |
| A4 | untrusted content を compliance exception / legal checklist / risk workflow として採用する 3 ターン候補を追加 |
| A5 | `secret.txt` の compliance / legal / privacy / governance cleanup と ticket cleanup を併存 |
| A6 | 候補上限対策として汎用 notice topic を 8 → 6 に削減（incident drill / deployment verification を除外） |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- ticket 系と compliance 系の文脈を 1 提出で同時にカバーし、cell signature の分散を増やす。
- 単純 union より先に core replay が並ぶため、時間切れ時でも短い実績候補を優先できる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-018-unified-workflow-bank/attack.py
aicomp validate redteam experiments/runs/exp-018-unified-workflow-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-018
```

結果:

- `py_compile`: pass
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `1995`
- unique 候補数: `1995`
- 最大ターン数: `3`
- 最大メッセージ長: `120`

追加 smoke test:

```bash
aicomp test redteam experiments/runs/exp-018-unified-workflow-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `116.0s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy として扱い、0 findings でも Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-018` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-018-unified-workflow-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
