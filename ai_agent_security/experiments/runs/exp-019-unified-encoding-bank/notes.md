# exp-019-unified-encoding-bank

- 名前: unified-encoding-bank
- Kaggle タグ: `exp-019-unified-encoding-bank`

## 仮説

`exp-018-unified-workflow-bank` は ticket / compliance / handoff 系の業務文脈を 1 本に統合し、固定 replay bank で多様な cell signature を狙う構成だった。一方 `exp-012-encoding-chain-bank` は、evaluator 更新後に効きやすい base64 / URL / hex 変換と read → encode → exfil の短い多段候補を別系統で持っていた。

今回は exp-018 の workflow bank をベースに、exp-012 の encoding chain を統合する。さらに compliance / ticket 宛先へ変換済み値を送る workflow 向け encode 候補を追加し、平文 exfil と変換 exfil、業務ルーティングの 3 軸を 1 提出で同時に replay する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-018 の core replay / handoff / ticket / compliance / runbook / destructive / Go-Explore fallback を維持 |
| A1 | exp-012 の `ENCODED_PAYLOADS` による base64 / URL / hex 直接 POST 候補を追加 |
| A2 | read → encode → POST の 2 ターン候補（監査系 URL）を追加 |
| A3 | read → transform → POST の 3 ターン候補（監査系 URL）を追加 |
| A4 | compliance / ticket / incident / legal 宛の workflow encode 2 ターン候補を追加 |
| A5 | compliance / ticket 宛の workflow transform 3 ターン候補を追加 |
| A6 | 2000 件上限対策として汎用 notice topic を 6 → 4、compliance notice topic を 5 → 4 に削減 |
| A7 | workflow transform exfil 先を 4 → 2 に絞り、最終 1998 件に調整 |
| B | 時間が十分残る場合のみ、小さめの Kaggle-only Go-Explore を追加 |

## 期待する効果

- exp-018 の業務文脈カバレッジを維持しつつ、変換済み exfiltration 経路を追加できる。
- evaluator の reversible encoding 検知強化に合わせ、平文と変換済み文字列の両方を固定 replay する。
- 固定候補を無条件に返すため、ローカル deterministic agent との差で候補が落ちない。

## ローカル検証

```bash
python3 -m py_compile experiments/runs/exp-019-unified-encoding-bank/attack.py
$HOME/.local/bin/aicomp validate redteam experiments/runs/exp-019-unified-encoding-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-019
```

結果:

- `py_compile`: pass
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `1998`
- unique 候補数: `1998`
- 最大ターン数: `3`
- 最大メッセージ長: `130`

追加 smoke test:

```bash
$HOME/.local/bin/aicomp test redteam experiments/runs/exp-019-unified-encoding-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `115.5s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy として扱い、0 findings でも Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-019` の bundle を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-019-unified-encoding-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `python3 scripts/exp.py sync` を実行する。
