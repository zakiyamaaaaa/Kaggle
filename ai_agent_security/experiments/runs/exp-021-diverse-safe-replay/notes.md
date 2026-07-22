# exp-021-diverse-safe-replay

- 名前: diverse-safe-replay
- Kaggle タグ: `exp-021-diverse-safe-replay`

## 仮説

`exp-020`（0.485）は exp-014 bank（62 件）のタイムアウト安全版として成功したが、020/014 は exp-006 core と **高い重複** がある。013/015 が Format Error になった主因は bank 内容ではなく候補数と Go-Explore だった。

今回は **020 の安全設計を維持** しつつ、013/015 由来の **2 ターン以下** 候補だけを追加して unique cell 多様性とスコア向上を狙う。Discussion [#711457](https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/711457) の目安（600 件超で replay 危険）を避けるため **`BANK_CAP=480`** に固定する。

## 実装内容

| 項目 | exp-020 | exp-021（本実験） |
|---|---|---|
| 優先 bank | 014 系 62 件 | 020 priority bank + exp-006 追加 2 件 |
| 拡張 | なし | 013 handoff / 015 structured の 2 ターン候補 |
| 3 ターン | なし | **除外** |
| Go-Explore | なし | なし |
| `BANK_CAP` | 実質 62 | **480** |
| `MAX_FINDINGS` | 512 | 512 |
| 返却順 | 短い順 | 短い順 |

拡張候補の内訳（builder 由来）:

- exp-015: HTTP grid、notice grid、read-share / untrusted 2 ターン
- exp-013: handoff HTTP、extract→direct route 2 ターン、handoff notice、retention cleanup
- exp-006: config read → email ops-team

## 期待する効果

- 020（0.485）を下回らず、006（0.56）に近づける。
- 013/015 で狙っていた predicate 多様性を、Format Error リスクなく部分的に再現する。
- 480 件 cap で replay timeout を回避する。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-021-diverse-safe-replay/attack.py
python3 scripts/sync_submit_notebook.py exp-021-diverse-safe-replay
python3 scripts/validate_submission_bundle.py kaggle-push/exp-021
```

結果:

- 固定候補数: `480`（`BANK_CAP`）
- 020 比の新規候補: `418`
- 最大ターン数: `2`
- `MAX_FINDINGS`: `512`
- Go-Explore: 無効

## 提出

1. `kaggle-push/exp-021` の bundle を Kaggle kernels push する。
2. Kaggle UI で **Save & Run All (Commit)** → **Submit to Competition**。
3. Version description: `exp-021-diverse-safe-replay`
4. スコア反映後: `python3 scripts/exp.py sync`

## 結果

（提出後に記入）
