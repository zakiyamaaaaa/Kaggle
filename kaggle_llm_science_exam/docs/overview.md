# Overview 日本語メモ

公式ページ: [Kaggle - LLM Science Exam](https://www.kaggle.com/competitions/kaggle-llm-science-exam)

## コンペ概要

**Kaggle - LLM Science Exam** は、LLM を使って難しい科学系の多肢選択問題に答えるコンペです。OpenBookQA データセットに着想を得ており、LLM が生成した科学問題に対して、5つの選択肢 `A`〜`E` の中から正答らしいものを順位付きで予測します。

このコンペの狙いは、LLM が自分自身で作ったような難問にどの程度答えられるか、また限られた計算資源で動かせるモデルがどこまで性能を出せるかを調べることです。

## タスク

各問題には以下が与えられます。

- `prompt`: 科学に関する設問
- `A`, `B`, `C`, `D`, `E`: 5つの選択肢

参加者は、各 `id` に対して正答の可能性が高い選択肢を最大3つ、確信度の高い順に提出します。

提出例:

```csv
id,prediction
0,A B C
1,D A E
```

## データ

公開されている訓練データには、設問・5つの選択肢・正解ラベルが含まれます。テストデータでは正解ラベルが隠されており、提出ファイルで `prediction` を作成します。

問題は科学トピックに基づいており、Wikipedia 由来のテキスト断片をもとに GPT-3.5 などの LLM で生成されたと説明されています。訓練データ数は大きくないため、外部データ、検索、追加生成データ、事前学習モデルの活用が重要になります。

## 評価指標

評価指標は **Mean Average Precision @ 3（MAP@3）** です。

正解が予測リストの何番目に入っているかでスコアが変わります。

- 1位に正解がある: 高スコア
- 2位または3位に正解がある: 部分点
- 上位3件に正解がない: 0点

各問題の AP@3 を平均したものが最終スコアになります。単に正解を含めるだけでなく、正しい選択肢をできるだけ上位に置くことが重要です。

## 基本方針の候補

典型的なアプローチは以下です。

- DeBERTa や BERT 系モデルによる multiple choice 分類
- LLM による選択肢ランキング
- Wikipedia などから関連文脈を検索する RAG
- BM25、Embedding、再ランキングを組み合わせた検索強化
- 追加の科学 QA データや合成データによる学習
- 複数モデル・複数検索結果のアンサンブル

特に上位解法では、Wikipedia を open-book 的に利用し、設問に関連する文脈を検索してから回答モデルに渡す構成がよく使われています。

## コンペ情報

| 項目 | 内容 |
|---|---|
| 種別 | Featured Code Competition |
| ホスト | Kaggle |
| 開始 | 2023-07-11 |
| 終了 | 2023-10-10 |
| 賞金 | $50,000 |
| タグ | Physics, NLP, MAP@K |
| 参加規模 | 2,664 teams / 57,886 submissions |

## このフォルダで管理したいこと

- `data/`: Kaggle データ、外部データ、検索用コーパス
- `experiments/`: 実験ごとのコード・設定・結果
- `notebooks/`: EDA、学習、推論、提出用ノートブック
- `submissions/`: 提出 CSV とスコア履歴
- `docs/`: 公式情報、解法メモ、参考リンク

## 参考リンク

- [Competition Page](https://www.kaggle.com/competitions/kaggle-llm-science-exam)
- [OpenBookQA](https://allenai.org/data/open-book-qa)
