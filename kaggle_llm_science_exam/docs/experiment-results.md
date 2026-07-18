# 実験結果メモ

作成日: 2026-07-08

## 提出結果

| ref | 手法 | Public | Private | メモ |
|---:|---|---:|---:|---|
| 54443338 | 長さ順 baseline | 0.542655 | 0.523705 | 各問題で選択肢を語数の長い順に並べる |
| 54454091 | 長さ + TF-IDF 類似度 ensemble | 0.552226 | 0.529853 | 長さスコアに prompt/option の TF-IDF cosine を少量加える |
| 54454212 | 特徴量分類器 + 長さ/TF-IDF blend | 0.523096 | 0.522038 | ExtraTrees で option 単位に正解確率を学習し、手作りスコアと混ぜる |
| 54460835 | BM25 RAG + 長さ/TF-IDF | 0.587598 | 0.564395 | Wikipedia STEM を BM25 で検索し、context/option 類似度を加える |

現時点の最良は **BM25 RAG + 長さ/TF-IDF** です。

## ローカル比較

`train.csv` 200件で MAP@3 を計算しました。

| 手法 | train MAP@3 |
|---|---:|
| 長さ + TF-IDF 類似度 ensemble | 0.5700 |
| BM25 RAG + 長さ/TF-IDF (top_k=10, rag=0.1) | 0.5783 |
| 長さ順 | 0.5375 |
| ラベル頻度順 | 0.4133 |
| sample submission 相当 `A B C` | 0.3783 |
| TF-IDF 類似度のみ | 0.3042 |
| prompt/option overlap のみ | 0.2742 |

質問単位 5-fold CV で軽量分類器も試しました。

| モデル | CV MAP@3 |
|---|---:|
| ExtraTrees | 0.5367 |
| RandomForest | 0.5258 |
| LogisticRegression | 0.5133 |
| GradientBoosting | 0.5100 |

ExtraTrees と手作りスコアの blend は CV 上で 0.5467 程度でしたが、実提出では悪化しました。

## 考察

### 1. 長さバイアスは評価データにも残っている

長さ順 baseline が Public 0.542655 / Private 0.523705 を出しており、`train.csv` で見えた「正解選択肢が長め」という癖は隠し評価側にも残っていました。

このコンペでは、内容理解をしない単純なルールでも 0.52 以上が出るため、以後のモデルはこの baseline を確実に超える必要があります。

### 2. TF-IDF は単独では弱いが、補助信号として効く

TF-IDF 類似度単独は train MAP@3 0.3042 と弱いです。しかし長さスコアに少量混ぜると、実提出で Public/Private ともに改善しました。

これは、prompt と選択肢の単純な語彙一致だけでは正解を選べないものの、長さ順で迷うケースの tie-breaker としては有効だったと考えられます。

### 3. 小さな train だけで分類器を作ると過学習しやすい

ExtraTrees blend は CV では手作りスコアと同等以上に見えましたが、実提出では Public 0.523096 / Private 0.522038 まで下がりました。

train は 200 問しかなく、option 単位に展開しても実質的な問題数は少ないです。選択肢ラベル、長さ、局所的な語彙特徴に過学習しやすく、隠しデータへの一般化が弱かったと見ています。

### 4. BM25 RAG は少量の外部知識で train を改善

Wikipedia STEM コーパス（ローカル: `ranchantan` 40,489 chunks）を BM25 で検索し、取得した context と各選択肢の TF-IDF 類似度を加えました。

最良設定:

- `top_k=10`
- `rag_weight=0.1`
- `tfidf_weight=0.25`

train MAP@3 は 0.5700 → 0.5783 に改善しました。RAG 重みを大きくしすぎると悪化するため、外部文脈は tie-breaker 的に少量混ぜるのがよさそうです。

Kaggle Notebook では `mbanaei/all-paraphs-parsed-expanded`（270K Wikipedia STEM articles）を attach して提出します。

### 5. 次は外部知識を入れないと伸びにくい

ここまでの手法は、すべて `prompt` と選択肢だけを見ています。上位解法との差を考えると、次の改善には Wikipedia などの外部文脈を検索する RAG が必要です。

次に試す候補:

- Wikipedia/STEM コーパスを用意する
- prompt と選択肢から検索クエリを作る
- BM25 または embedding で関連文脈を取得する
- `context + prompt + option` を分類または LLM で採点する
- 最後に長さ特徴を tie-breaker として混ぜる

## 現時点の採用方針

短期 baseline としては **BM25 RAG + 長さ/TF-IDF** を採用します（Public 0.587598 / Private 0.564395）。

分類器 blend は、現時点では採用しません。CV より実提出のほうが悪く、train 200件の特徴量学習では安定しないためです。

## BM25 RAG 提出手順

Kaggle OAuth が切れている場合は再ログインしてから実行します。

```bash
source .venv/bin/activate
kaggle auth login

kaggle kernels push -p kaggle_llm_science_exam/kaggle-push/bm25-rag
# 実行完了後
kaggle competitions submit -c kaggle-llm-science-exam \
  -k zacky21/llm-science-bm25-rag -v 1 -f submission.csv \
  -m "BM25 RAG with length and TF-IDF ensemble"
```
