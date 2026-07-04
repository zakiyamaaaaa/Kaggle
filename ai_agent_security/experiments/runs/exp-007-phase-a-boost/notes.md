# exp-007-phase-a-boost

- Name: phase-a-boost
- Kaggle tag: `exp-007-phase-a-boost`

## Hypothesis

exp-006 (public **0.56**) left Phase A minimal (4 singles + 1 multi-turn + 3 config snapshots).
exp-004 showed deputy variants and extra snapshot branches work in isolation but never submitted.
Expand Phase A with exp-004's grid while **reserving ~280s for Phase B Go-Explore** (same as exp-006).

## Strategy

| Phase | Content |
|---|---|
| **A1** | Direct exfil singles (exp-006) |
| **A2** | 7 deputy singles (exp-004) |
| **A3** | 3 multi-turn read → deputy |
| **A4** | config.json snapshot × 5 follows |
| **A5** | weekly_report snapshot × 3 follows |
| **A6** | Gated encoding snapshot × 3 + 1 two-turn (only if budget allows) |
| **B** | Go-Explore identical to exp-006 (`branch_batch=8`, `max_turns=10`) |

Phase A uses `can_run_phase_a()` — each attempt needs `margin + 280s` reserve so Go-Explore still runs.

## vs exp-006

| | exp-006 | exp-007 |
|---|---|---|
| Deputy singles | 2 | 7 |
| Multi-turn | 1 | 3 |
| Config snapshot follows | 3 | 5 |
| Weekly snapshot | — | 3 |
| Encoding variants | — | gated (3 snapshot + 1 two-turn) |
| Phase B | Go-Explore | same |

## Baseline

| exp_id | public_score |
|---|---|
| exp-006-hybrid-baseline-goexplore | **0.56** |
| exp-001-baseline | 0.255 |

## Local test

```bash
uv run aicomp validate redteam experiments/runs/exp-007-phase-a-boost/attack.py
uv run aicomp test redteam experiments/runs/exp-007-phase-a-boost/attack.py \
  --budget-s 600 --agent deterministic --env gym --verbosity progress
```

## Kaggle submit

1. Upload `submit.ipynb` or copy cell 2
2. Save & Run All — **T4 x2**
3. Version description: `exp-007-phase-a-boost`
4. Submit on Kaggle UI
5. `uv run python scripts/exp.py sync`
