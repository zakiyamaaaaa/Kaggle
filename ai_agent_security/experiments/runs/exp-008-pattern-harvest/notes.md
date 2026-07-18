# exp-008-pattern-harvest

- 名前: pattern-harvest
- Kaggle タグ: `exp-008-pattern-harvest`

## 仮説

`exp-007` は Phase A を広げすぎた結果、`exp-006` を下回った。
さらにプロンプトを追加する前に、生成中に固定攻撃パターンを 1 つずつ計測し、
その実行で predicate を発火させたパターンだけを残し、短く再現しやすい勝ち筋を優先して並べる。

この実験は診断用の橋渡しである:

- まず `exp-006` のコアを維持する。
- 選別した `exp-004`/`exp-007` 候補を、個別に計測するパターンとして追加する。
- コンパクトな Go-Explore 予算を消費しそうな場合は、優先度の低いパターンをスキップする。
- 有用な固定パターンと無用な固定パターンを分離できるように、`pattern_metrics.csv` を書き出す。

## 戦略

| フェーズ | 内容 |
|---|---|
| A1 | `exp-006` のコアパターン。各パターンはクリーンな `env.reset()` から実行 |
| A2 | 選別した deputy 系の単発ターン派生 |
| A3 | 選別した read -> deputy 系の 2 ターン派生 |
| A4 | 選別した weekly/config snapshot 風の 2 ターン派生 |
| A5 | 軽量な encoding/exfil 派生 |
| B | 時間が残ればコンパクトな Go-Explore (`branch_batch=6`, `max_turns=8`) |

各パターンは以下を持つ:

- `pattern_id`
- `group`
- `priority`
- `margin_s`
- `messages`

成功したパターンは Go-Explore 候補より先に返す。順位付けは以下の順:

1. 優先度が低い数値
2. ターン数が少ない
3. predicate 数が多い
4. 経過時間が短い

## メトリクス

Kaggle 上では、攻撃は以下を書き出す:

```text
/kaggle/working/pattern_metrics.csv
```

ローカルテストでは以下を設定する:

```bash
AICOMP_PATTERN_METRICS_PATH=experiments/runs/exp-008-pattern-harvest/pattern_metrics.csv \
uv run aicomp test redteam experiments/runs/exp-008-pattern-harvest/attack.py \
  --budget-s 600 --agent deterministic --env gym --verbosity progress
```

列:

| 列 | 意味 |
|---|---|
| `pattern_id` | 安定したパターン名 |
| `group` | 攻撃ファミリー |
| `status` | `hit`, `miss`, `skipped_time`, `error` のいずれか |
| `predicate_count` | 発火した predicate 数 |
| `predicates` | パイプ区切りの predicate 名 |
| `elapsed_s` | 生成時のコスト |
| `turns` | user メッセージ数 |

## 期待する結果

主目的:

- 固定候補を単独で計測したときに、どれが実際に predicate を発火させるかを特定する。

リーダーボード上の目標:

- `exp-007` の手動提出スコア `0.310` を上回る
- できれば `exp-006` のスコア `0.560` まで戻す、または改善する

これが `exp-006` を上回らない場合は、メトリクスを使って `hit` パターンだけに絞り、
調整した Go-Explore 予算を加えて `exp-009` を作る。

## ローカル検証

完了済み:

```bash
python3 -m py_compile experiments/runs/exp-008-pattern-harvest/attack.py
uv run aicomp validate redteam experiments/runs/exp-008-pattern-harvest/attack.py
AICOMP_PATTERN_METRICS_PATH=experiments/runs/exp-008-pattern-harvest/pattern_metrics.csv \
uv run aicomp test redteam experiments/runs/exp-008-pattern-harvest/attack.py \
  --budget-s 600 --agent deterministic --env gym --verbosity progress
```

ローカル `deterministic/gym` 結果:

- findings: `0`
- メトリクス行数: `18`
- ステータス: `18 miss`

ローカルの deterministic agent はフォーマット確認とスモークテスト用の proxy にすぎず、
本番の replay evaluator とは大きく異なる可能性があるため、これは Kaggle スコア上の blocker とは扱わない。

## 提出

1. この `attack.py` から `submit.ipynb` を作成または更新する。
2. description `exp-008-pattern-harvest` で実行または提出する。
3. `exp-007` でスコア付き結果が得られたため、まずは手動提出 CSV ルートを優先する。
4. スコアが反映されたら `python3 scripts/exp.py sync` を実行する。
