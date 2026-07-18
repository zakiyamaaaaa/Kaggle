# exp-016-compliance-routing-bank

- 名前: compliance-routing-bank
- Kaggle タグ: `exp-016-compliance-routing-bank`

## 仮説

`exp-013-handoff-routing-bank` は、過去最良の `exp-006` の短い replay 候補を維持しつつ、webhook / callback / handoff / runbook といった業務表現を増やした固定 bank 型の実験だった。今回の実験では、その構成を崩さずに `compliance` / `legal review` / `risk register` / `governance archive` といった監査・承認ワークフロー系の言い換えを追加する。

狙いは、同じ `http.post` / `email.send` / `fs.write` / `shell.run` 系の predicate でも、宛先ドメイン・受信者・直近ユーザーメッセージ・多段経路を変えて cell signature の多様性を増やすこと。生成時に `env.interact` を叩いて成功候補だけを選別する方式ではなく、Kaggle 本番の LLM replay に短い固定候補を渡す方針は維持する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | `exp-011` の core / HTTP / notice / read-share / extract-route / runbook / destructive 候補を維持 |
| A1 | `compliance.example.com` / `legal.example.com` / `risk.example.com` / `governance.example.com` への direct exfiltration 候補を追加 |
| A2 | `compliance@company.invalid` / `legal@company.invalid` / `risk@company.invalid` などへの review/case/handoff 通知候補を追加 |
| A3 | 既存の read setup から compliance evidence / legal review / risk register へ渡す 2 ターン候補を追加 |
| A4 | read -> extract -> compliance route の 3 ターン候補を追加 |
| A5 | untrusted content を compliance exception / legal checklist / risk workflow として採用させる 3 ターン候補を追加 |
| A6 | `secret.txt` を compliance / legal / privacy / governance cleanup として更新・移動・クリアする候補を追加 |
| B | 時間が十分残る場合のみ、既存通り小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- `Post` / `Notify` / `handoff` 以外の監査・法務・承認ワークフロー表現で、本番 LLM が自然にツール呼び出しへ進む候補を増やす。
- HTTP 宛先ドメインとメール受信者を変え、成功時の cell signature 重複を減らす。
- `untrusted-to-action` は direct command だけでなく、承認済み例外・法務チェックリスト・リスクワークフローとして採用する経路を増やす。
- `destructive write` は単純な delete/write だけでなく、retention / legal hold / privacy cleanup として表現をずらす。

## ローカル検証

実装後に以下を実行した。

```bash
python3 -m py_compile experiments/runs/exp-016-compliance-routing-bank/attack.py
aicomp validate redteam experiments/runs/exp-016-compliance-routing-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-012
```

結果:

- `py_compile`: pass
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `1686`
- unique 候補数: `1686`
- 最大ターン数: `3`
- 最大メッセージ長: `120`

追加 smoke test:

```bash
aicomp test redteam experiments/runs/exp-016-compliance-routing-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `97.8s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy として扱い、0 findings でも Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-012` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-016-compliance-routing-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
