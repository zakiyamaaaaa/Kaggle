# `economy_mix50_waste_shield` experiment

This is an executor-only experiment. `economy_mix50` remains unchanged; the
experimental registry entry calls the same `Plan` and replaces only commands
that are provably ineffective from the current public observation. `PASS` is
never treated as waste. Potentially partial operations such as an oversized
`PICKUP` or a partially affordable market order are retained.

The shield covers observable invalid/silent-no-op cases such as boundary
moves, wrong/occupied/locked targets, missing resources, duplicate same-turn
plant requests that the engine atomically cancels, empty/full shed drops, and
market orders that cannot buy/sell even one unit. It does not attempt to
re-plan the economy, infer hidden opponent state, or decide whether a valid
`CARE` is strategically worthwhile.

## Reproduction

From `kaggriculture_s01`:

```sh
.venv/bin/pytest -q tests/test_waste_shield.py tests/test_planning_agent.py tests/test_local_arena.py
.venv/bin/ruff check src/kaggriculture_agent/waste_shield.py src/kaggriculture_agent/registry.py scripts/diagnose_policy.py
.venv/bin/python scripts/run_arena.py --agents candidate,economy_mix50 --games-per-pair 1 --swap-seats --workers 1 --seed 130001 --output experiments/economy_mix50-waste-shield/smoke/control
.venv/bin/python scripts/run_arena.py --agents candidate,economy_mix50_waste_shield --games-per-pair 1 --swap-seats --workers 1 --seed 130001 --output experiments/economy_mix50-waste-shield/smoke/shield
.venv/bin/python scripts/run_arena.py --agents candidate,economy_mix50 --games-per-pair 8 --swap-seats --workers 4 --seed 130001 --output experiments/economy_mix50-waste-shield/screen/control
.venv/bin/python scripts/run_arena.py --agents candidate,economy_mix50_waste_shield --games-per-pair 8 --swap-seats --workers 4 --seed 130001 --output experiments/economy_mix50-waste-shield/screen/shield
for seed in 130001 130002 130003 130004; do .venv/bin/python scripts/diagnose_policy.py --agents economy_mix50,economy_mix50_waste_shield --opponent candidate --seed "$seed" --output "experiments/economy_mix50-waste-shield/diagnostics/seed-$seed.json"; done
```

## Results

| paired run | games | variant wins | draws | mean variant reward | mean reward difference (variant − opponent) | failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| smoke, seed 130001 | 2 | 0 | 0 | 63,190.0 | −76,817.0 | 0 |
| screen, seeds 130001–130008 | 16 | 0 | 0 | 62,990.875 | −57,063.9375 | 0 |

The control and shield `games.csv` rows are exactly equal after normalizing
the agent name: 16/16 screen rows match rewards, status, and 719 steps. The
smoke rows also match exactly. Candidate wins every paired game, so this
experiment does not justify replacing the incumbent.

The four diagnostic files cover both seats for both variants (16 games in
total). Every game reconciled cashflow and completed normally. Engine waste
counters were zero for both policies: no `noops.*` entries, `overflow: 0`, no
water-deadline losses, and no escaped animals. The shield's own replacement
counter was also zero in all four seeds; the incumbent planner did not emit a
provably wasteful command in this panel. Other nonzero diagnostic counters
(for example `unfed_animal_days` and `unwatered_crop_days`) describe missed
work, not shieldable silent no-ops.

No Kaggle submission or push was performed.
