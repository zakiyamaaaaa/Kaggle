# exp-020-timeout-safe-replay

- 名前: timeout-safe-replay
- Kaggle タグ: `exp-020-timeout-safe-replay`

## 仮説

`exp-014-prioritized-replay-bank` は固定 bank を 62 件・最大 2 ターンに絞っていたが、Kaggle 提出では Format Error になった。Discussion [#725073](https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/725073) および [#711457](https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/711457) から、Format Error の主因は CSV 形式ではなく **攻撃生成 / replay タイムアウト** である可能性が高い。

`exp-014` は bank 自体は小さいが、評価時に Go-Explore が走り候補が膨張する設計だった。今回は **014 と同じ bank を維持しつつ、タイムアウト要因だけを除去** し、Format Error 解消を最優先で確認する。

## 実装内容

| 項目 | exp-014 | exp-020（本実験） |
|---|---|---|
| 固定 bank | 62 件（014 と同一） | 同一 |
| 最大ターン | 2 | 2（明示フィルタ） |
| Go-Explore | あり | **なし** |
| `MAX_FINDINGS` | 2000 | **512** |
| 返却順 | bank 順 | **ターン数昇順**（exp-006 準拠） |
| 生成 deadline | あり | 不要（即時 return） |

## 期待する効果

- replay 候補数を Discussion の安全域（~600 未満）に確実に収める。
- 評価時の Go-Explore 実行を排除し、生成フェーズ timeout を避ける。
- Format Error が解消されれば、014 bank の本番 replay スコアを初めて測定できる。
- 成功後、`exp-021-diverse-safe-replay` で多様性拡張を試す前提実験とする。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-020-timeout-safe-replay/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-020
python3 scripts/sync_submit_notebook.py exp-020-timeout-safe-replay
```

結果:
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `62`（exp-014 と同一 bank）
- 最大ターン数: `2`
- `MAX_FINDINGS`: `512`
- Go-Explore: 無効

## 結果

| exp_id | public_score | 備考 |
|---|---|---|
| exp-020-timeout-safe-replay | **0.485** | Format Error 解消。014 bank の初スコア |

LB 比較:

| exp_id | public_score |
|---|---|
| exp-006-hybrid-baseline-goexplore | **0.56** |
| **exp-020-timeout-safe-replay** | **0.485** |
| exp-001-baseline | 0.255 |

014 と同一 bank（62 件）で 0.485 は、**Go-Explore 除去 + 短い順ソート** だけで exp-006（0.56）の約 87% に到達したことを示す。013〜017 の Format Error は bank 内容より **タイムアウト設計** が主因だった仮説を裏付ける。

次の `exp-021-diverse-safe-replay` では、013/015 由来の候補を 400〜500 件 cap で追加し、unique cell 多様性とスコアのトレードオフを探る。

## 提出

1. `kaggle-push/exp-020` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-020-timeout-safe-replay` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
