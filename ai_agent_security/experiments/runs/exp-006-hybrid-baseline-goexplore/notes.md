# exp-006-hybrid-baseline-goexplore

- Name: hybrid-baseline-goexplore
- Kaggle tag: `exp-006-hybrid-baseline-goexplore`

## Hypothesis

exp-005 (0.075) ran Go-Explore alone with SDK fixture prompts — replay-unfriendly long chains, missed exp-001 wins.
Combine **replay-proven fixed prompts first**, then **Kaggle-only Go-Explore** on leftover budget.

## Strategy

| Phase | Content |
|---|---|
| **A** | exp-001 baseline verbatim (any predicate → record) |
| **B** | Go-Explore if ≥240s remain; `KAGGLE_GOEXPLORE_BANK` only (no install.txt / chain_attack_*) |
| **C** | Sort findings by chain length (short first), cap 2000 |

Go-Explore params (Phase B): `branch_batch=8`, `max_turns=10` (v2; shorter chains for replay).

## Results

| exp_id | public_score | notes |
|---|---|---|
| exp-006-hybrid-baseline-goexplore | **0.56** | Kaggle submit (v2); Format Error 解消後 |
| exp-001-baseline | 0.255 | |
| exp-005-goexplore | 0.075 | |
| exp-003-mixed-v1 | 0.060 | |

**0.56 は exp-001 (0.255) の約 2.2 倍。** Phase A（固定プロンプト先行）+ Phase B（Go-Explore 余り時間）の仮説が裏付けられた。

## Prior scores (historical)

## Local test

```bash
uv run aicomp validate redteam experiments/runs/exp-006-hybrid-baseline-goexplore/attack.py
uv run aicomp test redteam experiments/runs/exp-006-hybrid-baseline-goexplore/attack.py \
  --budget-s 300 --agent deterministic --verbosity progress
```

## Kaggle submit

1. Upload `submit.ipynb` or copy cell 2
2. Save & Run All (Commit) — T4 x2
3. Version description: `exp-006-hybrid-baseline-goexplore`
4. Submit on Kaggle UI
5. After score: `uv run python scripts/exp.py sync` (local only)

## Format error fix (v2)

Commit success != submission success. Evaluation runs `run()` for ~1800s separately.
v2 changes: global generation deadline with 120s buffer, try/except around exploration,
lazy Go-Explore import, smaller branch_batch/max_turns, always return `list[AttackCandidate]`.
