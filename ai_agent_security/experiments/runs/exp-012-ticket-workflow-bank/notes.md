# exp-012-ticket-workflow-bank

- 名前: ticket-workflow-bank
- Kaggle タグ: `exp-012-ticket-workflow-bank`

## 仮説

`exp-011-handoff-routing-bank` は、固定 replay bank と軽量 Go-Explore fallback の組み合わせで、Kaggle 本番 replay に短い候補を多く渡す設計になっている。まだ `MAX_FINDINGS=2000` には余裕があるため、既存の実績候補を先頭に維持したまま、業務ワークフロー系の言い換えを追加すると、同じ predicate でも別 cell signature を取りやすくなる可能性がある。

今回の実験では、チケット・インシデント・承認例外・casework という表現を中心に追加した。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | `exp-011` の core / HTTP / notice / read-share / extract-route / runbook / destructive 候補を維持 |
| A1 | `ticketing` / `incident` / `workflow` / `casework` / `triage` の HTTP 送信先と言い回しを追加 |
| A2 | `Create a ticket` / `Open an incident` / `approval task` / `triage update` など confused deputy 系 notice 表現を追加 |
| A3 | `Read -> ticket attachment/evidence field -> route` の 2〜3 ターン候補を追加 |
| A4 | inbox/web 由来の内容を incident ticket / approved exception / change-management task として受け入れ、実行へつなぐ 3 ターン候補を追加 |
| A5 | `secret.txt` に対する cleanup ticket / stale-secret incident / approved remediation 表現を追加 |
| B | 時間が十分残る場合のみ、ticket/workflow 語彙を含む小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- `Post` / `Notify` / `handoff` に寄っていた表現を、チケット処理・承認処理・インシデント対応に広げる。
- 既存の direct replay を崩さず、後段に候補を追加することで既知の強い候補を優先的に返す。
- HTTP 送信先・メール文面・読み取り後の配送チェーン・untrusted-to-action・destructive write のそれぞれで cell signature の多様性を増やす。

## ローカル検証

実装後に以下を実行した。

```bash
python3 -m py_compile experiments/runs/exp-012-ticket-workflow-bank/attack.py
aicomp validate redteam experiments/runs/exp-012-ticket-workflow-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-012
aicomp test redteam experiments/runs/exp-012-ticket-workflow-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- `py_compile`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- `aicomp validate`: pass
- 固定候補数: `1802`
- unique 候補数: `1802`
- 最大ターン数: `3`
- 最大メッセージ長: `106`

追加 smoke test:

```bash
aicomp test redteam experiments/runs/exp-012-ticket-workflow-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `103.6s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy として扱い、0 findings でも Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-012` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-012-ticket-workflow-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
