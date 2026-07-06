# exp-008-direct-replay-bank

- Name: direct-replay-bank
- Kaggle tag: `exp-008-direct-replay-bank`

## Hypothesis

Return a curated replay candidate bank before optional Kaggle-only Go-Explore so generation stochasticity cannot drop short proven prompts.

## Rationale

exp-006 reached public **0.56** by running replay-proven short prompts before
Kaggle-only Go-Explore. exp-007 expanded Phase A, but still gated fixed prompts on
generation-time `eval_predicates(env.export_trace_dict())`. Because final scoring
uses fresh replay traces, useful candidates can be lost when they fail during the
generation pass.

This experiment records a compact replay bank directly as `AttackCandidate`
objects, then spends remaining budget on the same Kaggle-targeted Go-Explore
style. The direct bank follows the public discussion suggestion that validated
prompt chains can be submitted directly without calling `interact()` during
generation.

## Strategy

| Phase | Content |
|---|---|
| **A** | Directly return 29 curated candidates: exp-001/006 winners, exp-007 deputy/snapshot branches, encoded exfil follow-ups, and two untrusted-source action probes |
| **B** | Optional Go-Explore with Kaggle-only prompt bank if enough generation budget remains |
| **C** | Preserve insertion order and cap at 512 findings so curated short candidates are first if replay budget becomes tight |

## Key changes vs exp-007

- No `eval_predicates` gating for fixed candidates.
- Direct replay bank starts with the most replayable short chains.
- Additional low-cost direct probes:
  - `SECRET_MARKER` direct post for scorer pattern coverage.
  - `Ping` / `Loop in` / `Tell` deputy variants that avoid the heuristic words
    `email`, `send`, and `upload`.
  - Web/email untrusted-source follow-up action probes.
- Go-Explore remains optional, but `max_turns` is reduced from 10 to 8 to favor
  shorter replayable chains.

## Baseline

| exp_id | public_score |
|---|---|
| exp-006-hybrid-baseline-goexplore | **0.56** |
| exp-001-baseline | 0.255 |
| exp-005-goexplore | 0.075 |

## Local test

```bash
uv run aicomp validate redteam experiments/runs/exp-008-direct-replay-bank/attack.py
uv run aicomp test redteam experiments/runs/exp-008-direct-replay-bank/attack.py \
  --budget-s 300 --agent deterministic --env gym --verbosity progress
python3 scripts/validate_submission_bundle.py kaggle-push/exp-008
```

Run on 2026-07-06:

- `aicomp validate`: passed.
- `aicomp test --budget-s 300 --agent deterministic --env gym --verbosity progress`:
  completed in 1.8s with 0 scored findings. This is acceptable as a smoke test
  for format/replay plumbing; deterministic local agent is not expected to match
  hosted model behavior.
- Direct `AttackAlgorithm().run()` check with a 300s dummy config returned 29
  candidates.
- `python3 scripts/validate_submission_bundle.py kaggle-push/exp-008`: passed.
- `submit.ipynb` and `kaggle-push/exp-008/exp-008-direct-replay-bank.ipynb`
  embed code matching `attack.py`.

## Kaggle submit

1. Push `kaggle-push/exp-008`.
2. Save & Run All with T4 x2.
3. Version description: `exp-008-direct-replay-bank`.
4. Submit the notebook from Kaggle UI; do not API-submit the placeholder CSV.
