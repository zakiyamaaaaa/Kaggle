# exp-023-encoding-safe-bank

- 名前: encoding-safe-bank
- Kaggle タグ: `exp-023-encoding-safe-bank`

## 仮説

exp-012 の encoding / transform 系候補は replay コストが高く Format Error になりやすかった。023 では **1〜2 ターンの encoding 候補だけ** を 480 件 cap で返し、reversible encoding のカバレッジを安全に試す。

## 手法

- base64 / url / hex 直接 POST
- read → encode → POST の 2 ターン候補
- Go-Explore なし、短い順ソート

## 提出

Version description: `exp-023-encoding-safe-bank`
