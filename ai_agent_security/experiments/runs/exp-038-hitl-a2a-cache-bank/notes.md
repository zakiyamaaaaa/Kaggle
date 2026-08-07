# exp-038-hitl-a2a-cache-bank

- 名前: hitl-a2a-cache-bank
- Kaggle タグ: `exp-038-hitl-a2a-cache-bank`

## 仮説

`exp-037-oauth-subagent-policy-bank` は OAuth / サブエージェント / メモリ同期 / ポリシー-as-code の文脈で exfil を委譲・監査運用に見せた。実運用のマルチエージェントでは、人間承認キュー（HITL）、エージェント間メッセージバス（A2A）、ツール結果キャッシュ同期、サンドボックス allowlist プローブでも秘密の外部送信が正当なオペレータ署名・タスクエンベロープ・キャッシュ無効化証跡・承認済みツール bypass テストに紛れ込みやすい。

今回は exp-037 の bank をベースに、(1) HITL approval HTTP 候補、(2) A2A bus HTTP 候補、(3) tool cache HTTP 候補、(4) allowlist probe HTTP 候補、(5) read → HITL 採用 → exfil の 3 ターン、(6) read → A2A 採用 → exfil の 3 ターンを追加する。2000 件上限のため、OAuth / sub-agent / memory / policy-as-code HTTP 格子と OAuth / sub-agent read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-037 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | HITL / operator approval HTTP 1 ターン候補を追加 |
| A3 | A2A / multi-agent bus HTTP 1 ターン候補を追加 |
| A4 | tool result cache sync HTTP 1 ターン候補を追加 |
| A5 | sandbox allowlist probe HTTP 1 ターン候補を追加 |
| A6 | read → HITL 採用 → exfil の 3 ターン HITL チェーンを追加 |
| A7 | read → A2A 採用 → exfil の 3 ターン A2A チェーンを追加 |
| A8 | 2000 件上限対策として OAuth / sub-agent / memory / policy-as-code HTTP と OAuth / sub-agent read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- HITL 表現で exfil をオペレータ承認証跡に見せ、危険操作の人手エスカレーションを狙える。
- A2A 文脈でクロスエージェントタスク中継として秘密を外部送信させられる。
- ツールキャッシュ同期で関数出力ミラーとして exfil を正当化できる。
- allowlist プローブでサンドボックス境界テストケースとして exfil を誘導できる。
- read 後の HITL / A2A テンプレで exfil を自然なマルチエージェント運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-038-hitl-a2a-cache-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-038-hitl-a2a-cache-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-038
python3 scripts/build_exp_notebook.py exp-038-hitl-a2a-cache-bank --description "HITL/A2A/tool-cache/allowlist replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-038` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-038-hitl-a2a-cache-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
