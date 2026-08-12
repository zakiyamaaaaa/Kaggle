# exp-042-rag-vector-embedding-cache-bank

- 名前: rag-vector-embedding-cache-bank
- Kaggle タグ: `exp-042-rag-vector-embedding-cache-bank`

## 仮説

`exp-041-llm-gateway-function-registry-bank` は LLM ゲートウェイ / function-calling / ツールスキーマ / 評価ハーネスの文脈で exfil をエージェント開発証跡に見せた。RAG エージェントでは、ドキュメント検索（chunk indexer）、ベクトル DB（embedding store）、埋め込みパイプライン（vectorization batch）、セマンティックキャッシュ（prompt-cache fingerprint）でも、秘密情報の外部送信がインデックス監査ログ・類似度ストア同期・エンコーダ trace・キャッシュ検証プローブに紛れ込みやすい。

今回は exp-041 の bank をベースに、(1) RAG retrieval / chunk indexer HTTP 候補、(2) vector DB / embedding store HTTP 候補、(3) embedding pipeline / vectorization batch HTTP 候補、(4) semantic cache / prompt-cache fingerprint HTTP 候補、(5) read → RAG retrieval 採用 → exfil の 3 ターン、(6) read → vector DB 採用 → exfil の 3 ターンを追加する。2000 件上限のため、LLM gateway / function-calling / tool-schema / eval-harness HTTP 格子と LLM gateway / function-calling read チェーンを bank から外す。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-041 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | RAG retrieval / chunk indexer HTTP 1 ターン候補を追加 |
| A3 | vector DB / embedding store HTTP 1 ターン候補を追加 |
| A4 | embedding pipeline / vectorization batch HTTP 1 ターン候補を追加 |
| A5 | semantic cache / prompt-cache fingerprint HTTP 1 ターン候補を追加 |
| A6 | read → RAG retrieval 採用 → exfil の 3 ターン RAG retrieval チェーンを追加 |
| A7 | read → vector DB 採用 → exfil の 3 ターン vector DB チェーンを追加 |
| A8 | 2000 件上限対策として LLM gateway / function-calling / tool-schema / eval-harness HTTP と LLM gateway / function-calling read チェーンを削除 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- RAG 検索表現で exfil を chunk-indexer 監査テレメトリに見せ、ドキュメント取り込み境界を狙える。
- ベクトル DB 文脈で embedding store 同期として秘密を外部送信させられる。
- 埋め込みパイプラインで vectorization batch trace として exfil を正当化できる。
- セマンティックキャッシュで prompt-cache fingerprint プローブとして exfil を誘導できる。
- read 後の RAG retrieval / vector DB テンプレで exfil を自然な RAG エージェント運用タスクに見せられる。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-042-rag-vector-embedding-cache-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-042-rag-vector-embedding-cache-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-042
python3 scripts/build_exp_notebook.py exp-042-rag-vector-embedding-cache-bank --description "RAG retrieval/vector DB/embedding pipeline/semantic cache replay bank with compact Go-Explore fallback."
```

## 提出

1. `kaggle-push/exp-042` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-042-rag-vector-embedding-cache-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
