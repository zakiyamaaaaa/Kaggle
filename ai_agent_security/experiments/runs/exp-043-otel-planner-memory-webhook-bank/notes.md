# exp-043-otel-planner-memory-webhook-bank

- 名前: otel-planner-memory-webhook-bank
- Kaggle タグ: `exp-043-otel-planner-memory-webhook-bank`

## 仮説

`exp-042-rag-vector-embedding-cache-bank` は RAG 検索 / ベクトル DB / 埋め込みパイプライン / セマンティックキャッシュの文脈で exfil をドキュメント取り込み証跡に見せた。本番のエージェント運用では、OpenTelemetry 分散トレーシング（span export）、プランナー・エグゼキュータ分解（ReAct task graph）、会話状態チェックポイント（agent memory store）、非同期ツール結果コールバック（webhook delivery）でも、秘密情報の外部送信が正当な可観測性・オーケストレーション・状態永続化・非同期完了通知に紛れ込みやすい。

今回は exp-042 の bank をベースに、(1) OpenTelemetry / span export HTTP 候補、(2) planner-executor / ReAct decomposition HTTP 候補、(3) agent memory / conversation checkpoint HTTP 候補、(4) async webhook / tool callback HTTP 候補、(5) read → OpenTelemetry 採用 → exfil の 3 ターン、(6) read → planner-executor 採用 → exfil の 3 ターンを追加する。2000 件上限のため、RAG retrieval / vector DB / embedding pipeline / semantic cache HTTP 格子と RAG retrieval / vector DB read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-042 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | OpenTelemetry / span export HTTP 1 ターン候補を追加 |
| A3 | planner-executor / ReAct decomposition HTTP 1 ターン候補を追加 |
| A4 | agent memory / conversation checkpoint HTTP 1 ターン候補を追加 |
| A5 | async webhook / tool callback HTTP 1 ターン候補を追加 |
| A6 | read → OpenTelemetry 採用 → exfil の 3 ターン OTEL チェーンを追加 |
| A7 | read → planner-executor 採用 → exfil の 3 ターン planner チェーンを追加 |
| A8 | 2000 件上限対策として RAG retrieval / vector DB / embedding pipeline / semantic cache HTTP と RAG retrieval / vector DB read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- OpenTelemetry 表現で exfil を分散トレース属性エクスポートに見せ、可観測性パイプライン境界を狙える。
- planner-executor 文脈で ReAct タスク分解証跡として秘密を外部送信させられる。
- agent memory チェックポイントで会話状態スナップショットとして exfil を正当化できる。
- async webhook コールバックでツール結果配信ペイロードとして exfil を誘導できる。
- read 後の OTEL / planner テンプレで exfil を自然なエージェント運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-043-otel-planner-memory-webhook-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-043-otel-planner-memory-webhook-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-043
python3 scripts/build_exp_notebook.py exp-043-otel-planner-memory-webhook-bank --description "OpenTelemetry/planner-executor/agent memory/webhook callback replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-043` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-043-otel-planner-memory-webhook-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
