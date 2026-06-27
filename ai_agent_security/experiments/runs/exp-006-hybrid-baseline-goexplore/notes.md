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

Go-Explore params (Phase B): `branch_batch=10`, `max_turns=12` (shorter chains for replay).

## vs exp-005-goexplore

- Phase A locks in exp-001-style wins before exploration
- Prompt bank replaced (not DEFAULT + extension)
- Shorter max_turns / smaller branch_batch
- Return order favors short chains

## Prior scores

| exp_id | score |
|---|---|
| exp-001-baseline | 0.255 |
| exp-005-goexplore | 0.075 |
| exp-003-mixed-v1 | 0.060 |

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
5. After score: `uv run python scripts/exp.py sync` (local only, not submit)
