# exp-022-hybrid-safe-goexplore

- 名前: hybrid-safe-goexplore
- Kaggle タグ: `exp-022-hybrid-safe-goexplore`

## 仮説

exp-006（0.56）の Phase A + Go-Explore ハイブリッドを、Format Error 回避設定（`MAX_FINDINGS=512`, `max_turns=6`, 120s buffer）で再現する。

## 手法

- Phase A: `eval_predicates` で gym 通過候補のみ記録
- Phase B: compact Go-Explore（候補数・時間で打ち切り）
- 2 ターン上限、短い順ソート

## 提出

Version description: `exp-022-hybrid-safe-goexplore`
