# exp-041-llm-gateway-function-registry-bank

- 名前: llm-gateway-function-registry-bank
- Kaggle タグ: `exp-041-llm-gateway-function-registry-bank`

## 仮説

`exp-040-gitops-sbom-ebpf-envelope-bank` は GitOps / SBOM / eBPF / KMS エンベロープの文脈で exfil を DevSecOps 証跡に見せた。本コンペの主戦場は **ツール利用エージェントの多段攻撃** であり、LLM API ゲートウェイのモデルルーティング監査、function-calling の OpenAPI ツールレジストリ同期、JSON スキーマによるツール引数検証プローブ、エージェント評価ハーネスの回帰リプレイでも、秘密情報の外部送信がトークン計量ログ・ツールマニフェスト・スキーマ適合テスト・ベンチマーク trace に紛れ込みやすい。

今回は exp-040 の bank をベースに、(1) LLM gateway / prompt router HTTP 候補、(2) function-calling / tool registry HTTP 候補、(3) tool JSON schema validation HTTP 候補、(4) agent eval / regression harness HTTP 候補、(5) read → LLM gateway 採用 → exfil の 3 ターン、(6) read → function-calling 採用 → exfil の 3 ターンを追加する。2000 件上限のため、GitOps / SBOM / eBPF / envelope HTTP 格子と GitOps / SBOM read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-040 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | LLM gateway / model router HTTP 1 ターン候補を追加 |
| A3 | function-calling / OpenAPI registry HTTP 1 ターン候補を追加 |
| A4 | tool JSON schema validation HTTP 1 ターン候補を追加 |
| A5 | agent eval / regression harness HTTP 1 ターン候補を追加 |
| A6 | read → LLM gateway 採用 → exfil の 3 ターン LLM gateway チェーンを追加 |
| A7 | read → function-calling 採用 → exfil の 3 ターン function-calling チェーンを追加 |
| A8 | 2000 件上限対策として GitOps / SBOM / eBPF / envelope HTTP と GitOps / SBOM read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- LLM ゲートウェイ表現で exfil をモデルルーティング監査テレメトリに見せ、API プロキシ境界を狙える。
- function-calling 文脈で OpenAPI ツールレジストリ同期として秘密を外部送信させられる。
- JSON スキーマ検証プローブでツール引数適合テストケースとして exfil を正当化できる。
- 評価ハーネスでベンチマーク回帰 trace として exfil を誘導できる。
- read 後の LLM gateway / function-calling テンプレで exfil を自然なエージェント開発運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-041-llm-gateway-function-registry-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-041-llm-gateway-function-registry-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-041
python3 scripts/build_exp_notebook.py exp-041-llm-gateway-function-registry-bank --description "LLM gateway/function-calling/tool-schema/eval harness replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-041` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-041-llm-gateway-function-registry-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
