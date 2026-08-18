# exp-047-multiagent-delegate-capability-egress-bank

- 名前: multiagent-delegate-capability-egress-bank
- Kaggle タグ: `exp-047-multiagent-delegate-capability-egress-bank`

## 仮説

`exp-046-agent-auth-promptdef-toolschema-session-bank` はエージェント OAuth / プロンプト防御 / ツールスキーマ検証 / セッションリプレイの文脈で exfil を AI エージェント基盤の監査証跡に見せた。マルチエージェント構成では、プランナーからワーカーへの委任（multi-agent delegation）、子エージェント生成（subagent spawn）、スコープ付き権限付与（capability token）、外向き通信プロキシ検証（egress proxy）でも、秘密情報の外部送信が正当なハンドオフ証跡・ブートストラップペイロード・権限付与証拠・境界検査プローブに紛れ込みやすい。

今回は exp-046 の bank をベースに、(1) multi-agent delegation HTTP 候補、(2) subagent spawn HTTP 候補、(3) capability token HTTP 候補、(4) egress proxy HTTP 候補、(5) read → multi-agent delegation 採用 → exfil の 3 ターン、(6) read → capability token 採用 → exfil の 3 ターンを追加する。2000 件上限のため、agent OAuth / prompt defense / tool schema / session replay HTTP 格子と agent OAuth / prompt defense read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-046 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | multi-agent delegation / planner-to-worker handoff HTTP 1 ターン候補を追加 |
| A3 | subagent spawn / child-agent bootstrap HTTP 1 ターン候補を追加 |
| A4 | capability token / scoped permission grant HTTP 1 ターン候補を追加 |
| A5 | egress proxy / outbound filter bypass HTTP 1 ターン候補を追加 |
| A6 | read → multi-agent delegation 採用 → exfil の 3 ターン delegation チェーンを追加 |
| A7 | read → capability token 採用 → exfil の 3 ターン capability token チェーンを追加 |
| A8 | 2000 件上限対策として agent OAuth / prompt defense / tool schema / session replay HTTP と agent OAuth / prompt defense read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- マルチエージェント委任表現で exfil を planner-to-worker ハンドオフ証跡に見せ、エージェント間境界を狙える。
- サブエージェント生成文脈で child-agent ブートストラップとして秘密を外部送信させられる。
- ケイパビリティトークンで scoped 権限付与証拠として exfil を正当化できる。
- エグレスプロキシで境界検査プローブとして exfil を誘導できる。
- read 後の delegation / capability token テンプレで exfil を自然なマルチエージェント運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-047-multiagent-delegate-capability-egress-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-047-multiagent-delegate-capability-egress-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-047
python3 scripts/build_exp_notebook.py exp-047-multiagent-delegate-capability-egress-bank --description "Multi-agent delegation/subagent spawn/capability token/egress proxy replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-047` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-047-multiagent-delegate-capability-egress-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
