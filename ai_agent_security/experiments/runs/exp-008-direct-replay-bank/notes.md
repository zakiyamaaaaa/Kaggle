# exp-008-direct-replay-bank

- 名前: direct-replay-bank
- Kaggle tag: `exp-008-direct-replay-bank`

## 仮説

任意の Kaggle 向け Go-Explore を実行する前に、選定済みの replay 候補バンクを直接返す。これにより、生成時の確率的な失敗で短く実績のあるプロンプトが候補から落ちることを防ぐ。

## 背景

exp-006 は、replay 実績のある短い固定プロンプトを Kaggle 向け Go-Explore より先に実行することで public **0.56** に到達した。exp-007 は Phase A を拡張したが、固定プロンプトの採用は生成時の `eval_predicates(env.export_trace_dict())` に依存していた。最終スコアは新しい環境での replay trace によって決まるため、生成時に失敗しただけで有用な候補が失われる可能性がある。

この実験では、コンパクトな replay バンクを `AttackCandidate` として直接記録し、残り budget を既存と同系統の Kaggle 向け Go-Explore に使う。直接返却する方針は、検証済みのプロンプト列であれば生成時に `interact()` を呼ばずに提出できる、という Discussion 上の示唆にも沿っている。

## 戦略

| Phase | 内容 |
|---|---|
| **A** | 選定済み 29 候補を直接返す。内訳は exp-001/006 の有望候補、exp-007 の deputy/snapshot 分岐、エンコード exfil follow-up、untrusted-source action probe 2 件 |
| **B** | 生成 budget が十分残っている場合のみ、Kaggle 専用 prompt bank で Go-Explore を実行 |
| **C** | 挿入順を維持し、最大 512 findings に制限する。replay budget が厳しい場合でも短い選定候補が先に replay されるようにする |

## exp-007 からの主な変更点

- 固定候補に対する `eval_predicates` gating を廃止。
- direct replay bank は、最も replay しやすい短い chain から始める。
- 低コストな direct probe を追加:
  - scorer pattern coverage 用の `SECRET_MARKER` direct post。
  - heuristic word の `email` / `send` / `upload` を避ける `Ping` / `Loop in` / `Tell` deputy variant。
  - Web/email の untrusted-source follow-up action probe。
- Go-Explore は任意実行のまま維持しつつ、短く replay しやすい chain を優先するため `max_turns` を 10 から 8 に削減。

## ベースライン

| exp_id | public_score |
|---|---|
| exp-006-hybrid-baseline-goexplore | **0.56** |
| exp-001-baseline | 0.255 |
| exp-005-goexplore | 0.075 |

## ローカル検証

```bash
uv run aicomp validate redteam experiments/runs/exp-008-direct-replay-bank/attack.py
uv run aicomp test redteam experiments/runs/exp-008-direct-replay-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
python3 scripts/validate_submission_bundle.py kaggle-push/exp-008
```

2026-07-06 実行結果:

- `aicomp validate`: 成功。
- `aicomp test --budget-s 300 --agent deterministic --env gym --verbosity progress`:
  1.8 秒で完了し、scored finding は 0。これは形式と replay plumbing の smoke test として許容範囲。deterministic local agent は hosted model の挙動と一致する前提ではない。
- 300 秒の dummy config で直接 `AttackAlgorithm().run()` を確認し、29 candidates を返すことを確認。
- `python3 scripts/validate_submission_bundle.py kaggle-push/exp-008`: 成功。
- `submit.ipynb` と `kaggle-push/exp-008/exp-008-direct-replay-bank.ipynb` に埋め込まれたコードが `attack.py` と一致することを確認。

## Kaggle 提出

1. `kaggle-push/exp-008` を push する。
2. T4 x2 で Save & Run All を実行する。
3. Version description は `exp-008-direct-replay-bank` にする。
4. Kaggle UI から notebook を提出する。placeholder CSV を API submit しない。
