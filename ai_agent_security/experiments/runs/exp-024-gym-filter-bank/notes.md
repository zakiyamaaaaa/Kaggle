# exp-024-gym-filter-bank

- 名前: gym-filter-bank
- Kaggle タグ: `exp-024-gym-filter-bank`

## 仮説

exp-020 は全候補を無条件 replay する。024 では **core 候補は固定で返し、追加候補は生成時 `eval_predicates` 通過分だけ** 足す。006 に近い品質フィルタを、候補数 cap 付きで試す。

## 手法

- Phase A: exp-020 core を無条件記録
- Phase B: probe 候補を gym で試行、ヒットのみ追加
- `MAX_FINDINGS=512`, Go-Explore なし

## 提出

Version description: `exp-024-gym-filter-bank`
