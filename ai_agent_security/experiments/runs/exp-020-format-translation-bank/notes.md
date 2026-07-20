# exp-020-format-translation-bank

- 名前: format-translation-bank
- Kaggle タグ: `exp-020-format-translation-bank`

## 仮説

`exp-019-unified-encoding-bank` は workflow / encoding / handoff を 1 本に統合し、固定 replay bank で広い cell signature を狙う構成だった。一方で、HackAPrompt 由来の知見では「翻訳」「整形」「監査ログ化」などの間接表現が guardrail 回避や evaluator 差分に効きやすい。また `exp-014` の反省として、exp-006/007 で実績のある短い候補を先頭に置くことで replay 時間の浪費を抑えられる。

今回は exp-019 の bank をベースに、(1) exp-006/007 由来の優先候補を先頭に固定し、(2) JSON 診断レポート・監査テキスト・コンプライアンスログなどの format/translation フレーミング候補を追加する。平文 exfil・encoding chain・業務ルーティングの 3 軸に加え、間接表現の 4 軸目を replay する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-019 の core replay / handoff / ticket / compliance / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES`（deputy singles、config/weekly snapshot 2 ターン、encoding snapshot）を bank 先頭に配置 |
| A2 | secret を JSON 診断レポート・監査テキスト・コンプライアンスログ・引用復元として送る 1 ターン候補を追加 |
| A3 | read → format/translate → POST の 2 ターン候補を追加 |
| A4 | read → format transform → POST の 3 ターン候補を追加 |
| A5 | 2000 件上限対策として HTTP JSON テンプレート削除、notice recipient 8→6、compliance notice template 5→4、handoff/ticket/compliance URL を各 1 件削減 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- exp-006/007 で実績のある短い候補を先頭に置き、replay 時間を低確度格子候補で浪費しにくくする。
- 平文・encoding 以外に、format/translation フレーミングで evaluator の predicate 検知差分を狙える。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-020-format-translation-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-020-format-translation-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-020
```

結果:

- `py_compile`: pass
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `1884`
- unique 候補数: `1884`
- 最大ターン数: `3`
- 最大メッセージ長: `130`

追加 smoke test:

```bash
$HOME/.local/bin/aicomp test redteam experiments/runs/exp-020-format-translation-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `109.5s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy として扱い、0 findings でも Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-020` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-020-format-translation-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
