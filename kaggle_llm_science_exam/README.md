# kaggle_llm_science_exam

[Kaggle - LLM Science Exam](https://www.kaggle.com/competitions/kaggle-llm-science-exam) 向けのローカル作業フォルダです。

## 目的

科学分野の多肢選択問題に対して、LLM や検索・特徴量設計を使って正答候補を予測するコンペ用の実験管理を行います。

## ディレクトリ

| ディレクトリ | 用途 |
|---|---|
| `data/` | Kaggle から取得したデータやローカル前処理結果 |
| `data/external/` | Wikipedia STEM コーパスなど外部データ |
| `docs/` | コンペ概要、ルール、メモ、外部参照 |
| `experiments/` | 実験コード・設定・結果 |
| `kaggle-push/` | Kaggle Notebook 提出用パッケージ |
| `notebooks/` | 探索用・提出用ノートブック |
| `scripts/` | 再利用する補助スクリプト |
| `submissions/` | 提出ファイルや提出履歴 |

## スクリプト

```bash
source ../.venv/bin/activate

# 単純 baseline 比較
python scripts/evaluate_simple_methods.py

# BM25 RAG 評価（ローカルコーパス使用）
python scripts/evaluate_bm25_rag.py \
  --corpus-path data/external/ranchantan

# BM25 RAG 提出 CSV 生成
python scripts/generate_bm25_rag_submission.py \
  --corpus-path data/external/ranchantan
```

## Kaggle 提出

OAuth が切れている場合は `kaggle auth login` を先に実行します。

```bash
kaggle kernels push -p kaggle-push/bm25-rag
kaggle competitions submit -c kaggle-llm-science-exam \
  -k zacky21/llm-science-bm25-rag -v 1 -f submission.csv \
  -m "BM25 RAG with length and TF-IDF ensemble"
```

## 公式リンク

- [Competition Page](https://www.kaggle.com/competitions/kaggle-llm-science-exam)
