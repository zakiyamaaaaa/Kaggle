# exp-011-balanced-replay-bank

- 名前: balanced-replay-bank
- Kaggle タグ: `exp-011-balanced-replay-bank`

## 仮説

`exp-010` は 581 件の structured replay bank を無条件に返すことで、ローカル deterministic/gym では拾えない本番 LLM replay への候補供給を重視した。今回の実験では同じ方針を維持しつつ、候補数を約 800 件まで増やし、以下の経路を追加して unique cell の多様性を狙う。

- 過去最良 `exp-006` の短い固定候補を最優先に保持する。
- direct HTTP exfiltration に `collector.example.com` 系の別 URL と raw/form 風の短文を追加する。
- confused deputy では `Tell` / `Ping` / `Message` 系の文面を優先候補に置き、最後の user message に `send` / `email` / `upload` を含めない。
- `secret.txt` / `config.json` / inbox / web page から HTTP・通知・write・shell へつなぐ 2 ターン候補を拡張する。
- 少数の 3 ターン候補を追加し、untrusted source -> bridge -> action の replay 経路を試す。
- Go-Explore fallback は exp-010 と同じく短時間・Kaggle-only prompt bank に限定する。

## 実装内容

| フェーズ | 内容 |
|---|---|
| A0 | exp-006/010 由来の core replay 候補 |
| A1 | 手作業で選んだ優先 replay 候補（direct HTTP、confused deputy、read->exfil、untrusted->action） |
| A2 | secret payload x URL x 文面の direct HTTP grid |
| A3 | notify/inform/alert/remind/let/tell の confused deputy grid |
| A4 | read/open/list setup から HTTP・通知・credential relay へつなぐ 2 ターン候補 |
| A5 | inbox/web 由来の shell/write action 候補 |
| A6 | secret.txt destructive write 候補 |
| A7 | 少数の 3 ターン untrusted chain |
| B | 時間が十分残る場合のみ compact Go-Explore |

## 期待する効果

`exp-007` のように生成時探索へ時間を使いすぎるのではなく、固定候補生成は即時終了する。`exp-010` より少し広い bank にしつつ、候補は 1〜3 ターン・短文に抑え、本番 replay 時のツール列・URL・宛先・ファイル操作の分散を増やす。

## ローカル検証

実装後に以下を実行した。

```bash
python3 -m py_compile experiments/runs/exp-011-balanced-replay-bank/attack.py
aicomp validate redteam experiments/runs/exp-011-balanced-replay-bank/attack.py
python3 scripts/validate_submission_bundle.py kaggle-push/exp-011
```

結果:

- `py_compile`: pass
- `aicomp validate`: pass
- `validate_submission_bundle.py`: pass
- notebook 内 `attack_code` と実験版 `attack.py` の一致: pass
- 固定候補数: `764`
- 最大ターン数: `3`
- 最大メッセージ長: `88`

追加 smoke test:

```bash
aicomp test redteam experiments/runs/exp-011-balanced-replay-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
```

結果:

- 実行時間: `43.3s`
- findings: `0`
- score: `0.00`

固定 replay bank 型は、本番 LLM replay に候補を渡すことが主目的である。ローカル deterministic/gym はツール実行の形式確認・破綻検知の proxy であり、0 findings は Kaggle 提出の blocker とは扱わない。

## 提出

1. `kaggle-push/exp-011` を Kaggle kernels push する。
2. Kaggle UI で version description に `exp-011-balanced-replay-bank` を含めて notebook 自体を提出する。
3. スコア反映後に `uv run python scripts/exp.py sync` を実行する。
