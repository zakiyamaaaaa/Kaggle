# exp-005-goexplore

- Name: goexplore
- Kaggle tag: `exp-005-goexplore`

## Hypothesis

Fixed prompt lists (exp-001–004) cannot reach leaderboard top tier (~58–100).
Use SDK **Go-Explore** baseline: archive + snapshot/restore + cell-signature novelty search
over the full 1800s attack budget.

## Implementation

- `aicomp_sdk.attacks.baselines.attacker_goexplore.AttackAlgorithm` (subclassed)
- Extended `prompt_bank` with Kaggle starter / deputy / exfil phrases
- Filter return: dedupe, max 2000 findings, max 32 messages, 2000 chars/message

## Go-Explore params

| Param | Value |
|---|---|
| `branch_batch` | 12 |
| `max_turns` | 20 |
| `use_intent` | true |
| `use_args` | true |
| `args_count` | 5 |
| `use_outputs` | true |

## Local smoke test

```bash
uv run aicomp validate redteam experiments/runs/exp-005-goexplore/attack.py
# Go-Explore needs a long budget locally (uses ~budget - 5% headroom internally)
uv run aicomp test redteam experiments/runs/exp-005-goexplore/attack.py \
  --budget-s 300 --agent deterministic --verbosity progress
```

`run()` subtracts ~5% (30–120s) from `time_budget_s` before Go-Explore so the last branch batch does not trip the evaluator timeout.

## Prior scores (reference)

| exp_id | score | approach |
|---|---|---|
| exp-001-baseline | 0.255 | fixed prompts |
| exp-002-exfil-encoding | 0.0 | exfil-only filter |
| exp-003-mixed-v1 | 0.060 | mixed + heavy grid |
| exp-004-deputy-focus | (pending) | deputy expansion |
| **exp-005-goexplore** | **0.075** | SDK Go-Explore + prompt extension |

## Result

- Public score: **0.075** (submitted 2026-06-27)
- Go-Explore did **not** beat exp-001 (0.255); slightly above exp-003 (0.060)

## Post-mortem (why 0.075 << leaderboard / exp-001)

1. **Replay gap** — Go-Explore records chains where predicates fired during *exploration*, but production **replay** in a fresh env often fails (stochastic LLM). Long random chains replay worse than short starter prompts.
2. **Prompt bank mismatch** — SDK `DEFAULT_PROMPT_BANK` targets local fixtures (`read file install.txt`, `open chain_attack_1`, …), not Kaggle sandbox paths (`config.json`, `weekly_report.txt`). Much search budget spent off-target.
3. **No guaranteed baseline** — exp-001 fixed prompts were not run first; Go-Explore alone did not rediscover those replayable wins reliably.
4. **Top LB (58–100)** likely uses tuned Go-Explore (custom bank, replay-aware filtering, longer iteration) — stock baseline + small Kaggle extension is not enough.
