# exp-021-diverse-safe-replay

- 名前: diverse-safe-replay
- Kaggle タグ: `exp-021-diverse-safe-replay`

## 仮説

exp-020（0.485）は 62 件 bank で Format Error を回避できた。021 では exp-015 系の structured bank を **縮小グリッド + 480 cap + 2 ターン上限** で拡張し、unique cell 多様性と replay 時間のバランスを取る。

## 手法

- 固定 replay bank（Go-Explore なし）
- HTTP / notice / read-share / untrusted / destructive を限定グリッドで生成
- `MAX_FINDINGS=480`, 短い順ソート

## 提出

Version description: `exp-021-diverse-safe-replay`
