# Four-stage specialization

`kaggriculture_agent.specialization` is the planning and provenance layer for
specializing a candidate against a changing opponent population.  It does not
implement PPO (or any other learner).  The learner is a registered callable
today, and Champion Arena can replace that callable with a checkpoint later.

The loop is deliberately progressive:

| Stage | Pool | Purpose | Promotion evidence |
| --- | --- | --- | --- |
| 1 — broad opponent pool | all configured rule agents | screen general competence and catch regressions | paired validation against the broad pool |
| 2 — archetype champions | one representative per retained archetype | remove redundant behaviours while preserving coverage | hard-opponent win rate and zero failures |
| 3 — selected strategy families | representatives of the families that matter | spend training/evaluation budget on the selected families | family-level paired score |
| 4 — fixed specialist | one fixed final opponent definition | freeze a specialist and perform the final confirmation | holdout-ready promotion gate |

The checked-in registry currently has `baseline`, `candidate`, and the archived
public `public_salem` reference. The default config screens the candidate
against the broad baseline/Salem pool in Stage 1, then keeps the stronger Salem
reference as the hard opponent through Stages 2–4. The `archetype` and
`strategy_family` labels remain explicit, so adding crop-, animal-, and
market-specialist agents later is a config-only change.

## Configuration contract

The source config is [`configs/specialization.json`](../configs/specialization.json).
It contains:

- `candidate_agent`: the registered callable being trained/evaluated;
- `opponents`: named definitions with a registry `agent`, an `archetype`, a
  `strategy_family`, a base `weight`, and a `hard` flag;
- exactly four ordered stages (`stage_1` through `stage_4`), each with a pool,
  even training/evaluation game counts, a seed, a hard-opponent multiplier, and
  promotion prerequisites;
- paired development/validation/holdout seed ranges and evaluation policy.

Validation checks every registry reference, duplicate or unknown pool entry,
stage ordering, progressive subset relation, positive effective weight, Stage 4
specialist identity, and even game count.  Callers can inject an alternate
registry with `available_agents` when a remote Champion Arena is being planned.

## Deterministic sampling

Opponent allocation is exact rather than an unbounded stream of floating-point
`random.choices` calls:

1. base weights are multiplied by the stage's `hard_opponent_weight` for
   definitions marked `hard`;
2. `allocate_weighted_games` uses largest remainder, with ties resolved by the
   configured pool order;
3. paired mode allocates an even number of games to each opponent;
4. `sample_opponents` shuffles the allocated list with an explicit seed.

Therefore the same config, stage, count, and seed always produce the same
counts and assignment order.  Each paired sample has the same seed in seat 0
and seat 1, with the candidate/opponent order swapped in the second game.
Training and evaluation seed ranges are separated by a one-million offset when
they share a stage seed.

## Run the planner

From this directory:

```bash
uv run python scripts/run_specialization.py \
  --config configs/specialization.json \
  --output-dir outputs/specialization
```

The command only plans work.  It does not launch a learner or consume arena
compute.  `--games N` overrides both game counts for a small smoke plan, and
`--stage stage_2` can limit per-stage files while retaining the complete plan.
The command resumes an existing output directory when its config fingerprint
matches; use a new output directory (or `--no-resume`) for a fresh run.

Output files are:

- `specialization_plan.json`: all stage pools, effective weights, seat-paired
  assignments, promotion gates, and learner contract;
- `arena_plan.json`: compact Stage-by-Stage instructions for Champion Arena,
  including registered agent names, exact opponent allocations, seeds, and
  `swap_seats: true`;
- `manifest.json`: config/plan fingerprints, run id, per-stage status, and
  checkpoint metadata pointers;
- `checkpoints/stage_N.json`: metadata only (status, parent pointer, config and
  plan hashes, optional artifact hash).  No model/checkpoint artifact is made by
  this framework;
- `stages/stage_N.json` and `summary.json`: convenient per-stage and run-level
  JSON views.

The arena can consume each `champion_arena` object directly.  For the current
local arena, a simple external job is equivalent to:

```bash
uv run python scripts/run_arena.py \
  --agents candidate,baseline \
  --games-per-pair 12 \
  --swap-seats \
  --seed 10000 \
  --output outputs/specialization/stage_1-arena
```

If a stage contains a self-play definition, `arena_plan.json` marks it with
`self_play: true`; Champion Arena decides whether to include self-play in its
own backend.  The plan never silently maps an unknown alias to another rule.

## Promotion and checkpoints

`evaluate_promotion` accepts arena metrics and returns each check plus human-
readable failed prerequisites.  A typical metric payload is:

```json
{
  "evaluation_games": 40,
  "win_rate": 0.58,
  "mean_reward_delta": 120.0,
  "failure_rate": 0.0,
  "hard_opponent_win_rate": 0.55
}
```

Promotion requires all configured checks: sufficient completed evaluation
games, minimum paired win rate and reward delta, maximum failure rate, optional
hard-opponent threshold, and the previous stage's promotion.  Checkpoint
metadata is deliberately separate from an artifact so a rule agent can be
used now and a learned artifact can be attached later without changing the
run's identity.  The config SHA-256 and plan-stage SHA-256 prevent resuming a
checkpoint under a different plan.
