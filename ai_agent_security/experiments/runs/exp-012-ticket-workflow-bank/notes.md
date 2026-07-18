# exp-012-ticket-workflow-bank

- 名前: ticket-workflow-bank
- Kaggle タグ: `exp-012-ticket-workflow-bank`

## 仮説

<<<<<<< HEAD
直近の `exp-011-handoff-routing-bank` は、過去最良系統である短い固定 replay bank を維持しつつ handoff / routing 表現を追加して候補の多様性を増やした。候補数は上限 2000 に対してまだ余裕があるため、同じ predicate を別の業務文脈で誘発する候補を増やす余地がある。

今回の実験では、Kaggle 本番 LLM が自然にツールを使いそうな `ticket` / `incident` / `workflow` / `casework` / `triage` の表現を追加する。HTTP 外部送信、メール送信、読み取り後の証跡添付、untrusted content 由来の実行・書き込み、`secret.txt` の cleanup を ticket 処理として言い換え、cell signature の重複を減らすことを狙う。
=======
`exp-011-handoff-routing-bank` は、固定 replay bank と軽量 Go-Explore fallback の組み合わせで、Kaggle 本番 replay に短い候補を多く渡す設計になっている。まだ `MAX_FINDINGS=2000` には余裕があるため、既存の実績候補を先頭に維持したまま、業務ワークフロー系の言い換えを追加すると、同じ predicate でも別 cell signature を取りやすくなる可能性がある。

今回の実験では、チケット・インシデント・承認例外・casework という表現を中心に追加した。
>>>>>>> origin/main

## 実装内容

| フェーズ | 内容 |
|---|---|
<<<<<<< HEAD
| A0 | `exp-011` の core / HTTP / notice / read-share / extract-route / untrusted / destructive / Go-Explore fallback を維持 |
| A1 | `ticketing.example.com` / `incident.example.com` / `workflow.example.com` / `casework.example.com` への direct exfiltration 候補を追加 |
| A2 | `Create a ticket` / `Open an incident` / `Log a triage task` / `Start a casework item` の confused deputy 候補を追加 |
| A3 | `Read -> ticket evidence field -> route` と `Read -> extract -> case attachment` の 2〜3 ターン候補を追加 |
| A4 | untrusted content を incident ticket / workflow task / exception record / casework remediation として採用させる 3 ターン候補を追加 |
| A5 | `secret.txt` の削除・上書きを cleanup ticket / stale-secret incident / approved remediation として言い換える候補を追加 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- 既存の `webhook` / `handoff` 表現とは別の、チケット処理・インシデント対応系の自然な文脈で外部送信とメール送信を誘導する。
- `config.json` や `weekly_report.txt` の読み取り後に、証跡添付・ケース添付・triage workflow へ流す表現を増やし、replay 成功時の tool 引数と cell signature の分散を狙う。
- untrusted-to-action は「runbook」だけでなく「承認済み ticket/workflow」として実行・書き込みへつなげる。
- 固定候補を無条件に返すため、ローカル `eval_predicates` や deterministic agent の挙動差で候補が落ちない。

## ローカル検証

実装後に以下を実行する。
=======
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
>>>>>>> origin/main

```bash
python3 -m py_compile experiments/runs/exp-012-ticket-workflow-bank/attack.py
aicomp validate redteam experiments/runs/exp-012-ticket-workflow-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-012
<<<<<<< HEAD
=======
aicomp test redteam experiments/runs/exp-012-ticket-workflow-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
>>>>>>> origin/main
```

結果:

- `py_compile`: pass
<<<<<<< HEAD
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `1724`
- unique 候補数: `1724`
- 最大ターン数: `3`
- 最大メッセージ長: `114`
=======
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- `aicomp validate`: pass
- 固定候補数: `1802`
- unique 候補数: `1802`
- 最大ターン数: `3`
- 最大メッセージ長: `106`
>>>>>>> origin/main

追加 smoke test:

```bash
aicomp test redteam experiments/runs/exp-012-ticket-workflow-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

<<<<<<< HEAD
- 実行時間: `98.8s`
=======
- 実行時間: `103.6s`
>>>>>>> origin/main
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy として扱い、0 findings でも Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-012` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-012-ticket-workflow-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
