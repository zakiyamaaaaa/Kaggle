# OMW sell-now A/B/C screen — 2026-09-22

## Protocol

- Policies: current `omw-net-stock-sellnow-v2`, candidates A/B/C
- Opponents: One More Wheat, Peak 2950, Triad Counter, public Salem,
  Salem early-milk, baseline
- Seeds: 32 fresh seeds beginning at 994000
- Seats: both seats for every seed/opponent
- Games: 384 per policy; 1,536 total
- Primary metric: `win + 0.5 * draw`
- Engine: pinned `kaggle-environments==1.32.7`

## Aggregate result

| Policy | Score | Delta vs control | Paired bootstrap 95% CI | Balanced mean margin | Errors |
|---|---:|---:|---:|---:|---:|
| Current v2 | 0.929688 | — | — | 39,550.21 | 0 |
| A | 0.934896 | +0.005208 | [-0.010417, +0.026042] | 39,576.76 | 0 |
| B | 0.934896 | +0.005208 | [-0.010417, +0.026042] | 39,576.18 | 0 |
| C | 0.934896 | +0.005208 | [-0.010417, +0.026042] | 39,576.15 | 0 |

## Opponent score

| Policy | OMW | Peak | Triad | Salem | Early milk | Baseline |
|---|---:|---:|---:|---:|---:|---:|
| Current v2 | 0.656250 | 0.984375 | 0.968750 | 0.984375 | 0.984375 | 1.000000 |
| A | 0.718750 | 0.953125 | 0.968750 | 0.984375 | 0.984375 | 1.000000 |
| B | 0.718750 | 0.953125 | 0.968750 | 0.984375 | 0.984375 | 1.000000 |
| C | 0.718750 | 0.953125 | 0.968750 | 0.984375 | 0.984375 | 1.000000 |

## Decision

A/B/C have identical win/draw/loss outcomes in this screen. A gains four wins
against OMW relative to control but loses two wins against Peak. The aggregate
improvement is small and its confidence interval crosses zero. B and C change
cash margins on a small subset of games but add no win-rate benefit over A.

Do not promote any candidate from this screen alone. If continuing, carry only
A to a larger validation because it is the smallest change; treat B as a
safety/correctness hardening layer requiring targeted fault-injection tests,
and reject C unless a market-order opponent panel demonstrates a benefit.

## Candidate A validation

A was subsequently evaluated on 128 fresh seeds beginning at 995000, both
seats and the same six-opponent panel: 1,536 games per policy and 3,072 total.

| Policy | Aggregate score | Balanced mean margin | Errors |
|---|---:|---:|---:|
| Current v2 | 0.944010 | 38,749.72 | 0 |
| A | 0.931641 | 38,727.49 | 0 |

The paired score delta was `-0.012370`, with bootstrap 95% CI
`[-0.027344, +0.001953]`. Opponent deltas were OMW `-0.019531`, Peak
`-0.023438`, Triad `-0.031250`, and zero for Salem, early-milk and baseline.
Triad's opponent-specific 95% CI was `[-0.062500, -0.007812]`.

Candidate A therefore fails validation and must not proceed to holdout or
submission. Keep current v2 as the incumbent. Full validation rows are in
`outputs/omw-net-stock-sellnow-abc/validation-a-128seed.json`.

Full rows and summaries are in
`outputs/omw-net-stock-sellnow-abc/screen-32seed.json`.
