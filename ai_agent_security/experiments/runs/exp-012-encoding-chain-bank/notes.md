# exp-012-encoding-chain-bank

- 名前: encoding-chain-bank
- Kaggle タグ: `exp-012-encoding-chain-bank`

## 仮説

`exp-015-structured-replay-bank` は固定 replay bank を広く返すことで、ローカルの
`eval_predicates` に依存しない提出形にしていた。一方で、Discussion では evaluator
側が URL encoding / base64 / hex などの漏洩検知を強化する流れがあり、既存 bank の
encoding 系は単発候補が少なく、read した値を変換して外部送信する多段候補も薄かった。

この実験では exp-010 のコア候補と Go-Explore fallback を維持しつつ、短い
encoding / transform / exfiltration チェーンを追加する。大量の実行時探索ではなく、
replay しやすい 1〜3 ターン候補を増やし、本番 LLM replay での exfiltration と
unique cell 多様性の上積みを狙う。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-010 の `CORE_REPLAY_CANDIDATES` と direct HTTP / deputy / destructive 候補を継承 |
| A1 | 既知 secret の base64 / URL encoded / hex 文字列を直接 POST する候補を追加 |
| A2 | `config.json` / `weekly_report.txt` / inbox / web から読んだ値を encode して POST する 2 ターン候補を追加 |
| A3 | read → transform → POST の 3 ターン候補を追加 |
| B | 時間が十分残る場合のみ、従来どおりコンパクトな Kaggle-only Go-Explore を追加 |

## 期待する効果

- 直接 secret を含む文面だけでなく、変換済み文字列を使うことで guardrail や evaluator 更新の差分に当てる。
- read → encode → exfil の経路を増やし、成功時の tool sequence / URL / 引数の多様性を増やす。
- exp-007 の反省を踏まえ、生成時に env を大量に回さず、固定 replay bank を即返す構造を維持する。
- 最大 3 ターンの短い候補に抑え、replay 成功率と提出制約の安全性を優先する。

## ローカル検証

実装後に以下を実行した。

```bash
python3 -m py_compile experiments/runs/exp-012-encoding-chain-bank/attack.py
aicomp validate redteam experiments/runs/exp-012-encoding-chain-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-011
```

結果:

- `py_compile`: pass
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `739`
- 最大ターン数: `3`
- 最大メッセージ長: `130`

追加 smoke test:

```bash
aicomp test redteam experiments/runs/exp-012-encoding-chain-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `43.0s`
- findings: `0`
- score: `0.00`

固定 replay bank 型のため、`aicomp test` の deterministic/gym で 0 findings になっても
本番提出の blocker とは扱わない。形式チェック、候補数、候補長、notebook 同期を重点的に見る。

## 提出

1. `kaggle-push/exp-011` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-012-encoding-chain-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
