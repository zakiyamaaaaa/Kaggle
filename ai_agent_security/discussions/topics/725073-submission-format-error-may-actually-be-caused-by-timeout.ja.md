# Submission Format Error は CSV 形式ではなくタイムアウトが原因の可能性（日本語訳）

- Topic ID: 725073
- URL: https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/725073
- Author: KALYPHEUS
- Posted: 2026-07-14 頃（2026-07-18 時点で "4 days ago"）
- Votes: 4
- Comments: 0（取得時点では未ログインのため返信不可視）
- 原文: `discussions/topics/725073-submission-format-error-may-actually-be-caused-by-timeout.md`
- 翻訳日: 2026-07-18

## 投稿

公式 gateway コードを確認したところ、`Submission Format Error` は必ずしも `submission.csv` の列や形式が間違っていることを意味しない可能性がある、という理解です。

別の原因として考えられるのは次のとおりです。

攻撃生成フェーズまたは replay フェーズでタイムアウトが起きると、gateway が `INVALID_SUBMISSION` を raise し、最終的な有効な `submission.csv` が書き込まれない。

根拠は次のとおりです。

### 1. base gateway では、submission ファイルは全 prediction 成功後にのみ書かれる

Path: `ai-agent-security-multi-step-tool-attacks/kaggle_evaluation/core/base_gateway.py`

```
predictions, row_ids = self.get_all_predictions()
self.write_submission(predictions, row_ids)
```

`get_all_predictions()` のどこかで失敗すると `write_submission()` には到達しない。

### 2. コンペ固有 gateway でも CSV は最後に一度だけ書かれる

Path: `ai-agent-security-multi-step-tool-attacks/kaggle_evaluation/jed_attack_134815/jed_attack_gateway.py`

```
with open("submission.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Id", "Score"])
    for row_id, score in predictions["row_scores"].items():
        writer.writerow([row_id, score])
```

評価中に逐次書き込むのではなく、評価が正常完走した後にのみ書く。

### 3. タイムアウト例外は明示的に INVALID_SUBMISSION に変換される

Path: `ai-agent-security-multi-step-tool-attacks/kaggle_evaluation/jed_attack_134815/jed_attack_gateway.py`

```
except (ModelAttackTimedOut, ModelEvaluationTimedOut) as err:
    raise GatewayRuntimeError(
        GatewayRuntimeErrorType.INVALID_SUBMISSION,
        str(err),
    ) from err
```

`INVALID_SUBMISSION` は gateway の公式エラー型（`base_gateway.py` で `INVALID_SUBMISSION = 6`）。

### まとめ

あるモデルで攻撃生成または replay がタイムアウトすると、gateway は `INVALID_SUBMISSION` を raise し、通常の最終 `submission.csv` は書かれない。この場合、Kaggle UI では `Submission Format Error` と表示されても、実際の原因は CSV スキーマではない可能性がある。

つまり `Submission Format Error` は、場合によっては次を意味する:

- 評価が完走しなかった
- モデルがタイムアウトした
- gateway が run を invalid と判定した

次の意味ではない場合がある:

- ヘッダー列の誤り
- 列数の誤り
- CSV ファイル自体の破損

CSV 形式が正しいと確認済みなのにこのエラーが出る人向けに、タイムアウト / 中断評価パスも原因になりうるのではないか、という問いかけ。

## コメント

（取得時点では未ログインのため返信不可視。）
