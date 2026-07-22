# exp-022-context-boundary-bank

- 名前: context-boundary-bank
- Kaggle タグ: `exp-022-context-boundary-bank`

## 仮説

`exp-021-output-spec-bank` は output-spec 整形と擬似構造（JSON spec / ticket template）で guardrail 回避を狙った。HackAPrompt 由来の知見では、引用符・区切り・`Rules:` などの擬似構造で「局所コンテキスト」を作り、モデルに処理対象を誤認させる手法が探索初期に有効だった。また、役割付与（audit bot / compliance relay）や翻訳・復元フレーミングも間接化に効く。

今回は exp-021 の bank をベースに、(1) 役割コンテキスト HTTP 候補、(2) Rules / 三重引用符の境界ブロック候補、(3) 引用復元・言い換え候補、(4) read → 局所ルール採用 → exfil の 3 ターン context-boundary チェーンを追加する。2000 件上限のため、HTTP / handoff / ticket / compliance / format-translation / output-spec / structure-spec の格子を一部削減する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-021 の core replay / workflow / encoding / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-006/007 由来の `PRIORITY_REPLAY_CANDIDATES` を bank 先頭に配置 |
| A2 | 役割コンテキスト HTTP 候補（audit webhook agent / compliance relay bot）を追加 |
| A3 | Rules / 三重引用符の境界ブロック 1 ターン候補を追加 |
| A4 | 引用復元・言い換え（translation restore）1 ターン候補を追加 |
| A5 | read → 局所ルール採用 → exfil の 3 ターン context-boundary チェーンを追加 |
| A6 | 2000 件上限対策として output-spec HTTP 4→3、structure-spec 4→3、format-translation 4→3、handoff/ticket/compliance URL 各 4→3、output-spec email recipient 6→5 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- 直接命令ではなく役割・局所ルールブロックとして誘導し、guardrail と evaluator の検知差分を狙える。
- Rules / delimiter 擬似構造でエージェントに処理境界を作りやすくする。
- 引用復元・言い換えで secret 風文字列の間接化を試せる。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-022-context-boundary-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-022-context-boundary-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-022
python3 scripts/build_exp_notebook.py exp-022-context-boundary-bank
```

## 提出

1. `kaggle-push/exp-022` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-022-context-boundary-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
