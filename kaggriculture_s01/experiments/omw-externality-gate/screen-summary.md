# OMW externality gate: verification summary

## Policy

The distant forecast branch is blocked when the estimated price loss imposed on
the public rival stream exceeds 50% of our current-price revenue. The estimate
uses the public rival's next four-turn sell stream and the same market-price
function used by the candidate. Immediate one- and two-turn sales remain
unchanged.

## Evaluation

- Candidate: One More Wheat with `forecast4` as the parent.
- Smoke: 8 seeds × 6 opponents × 2 seats × 4 policies = 384 games.
- Screen: 32 seeds × 6 opponents × 2 seats × 4 policies = 1,536 games.
- Policies: frozen OMW control, `forecast4`, externality gate, price guard.

## Results

| Policy | Smoke score | Screen score | Screen mean margin | Paired delta vs control |
|---|---:|---:|---:|---:|
| Frozen OMW control | 0.864583 | 0.882813 | 39,487.89 | — |
| forecast4 | 0.937500 | 0.929688 | 39,551.11 | +0.046875 |
| Externality gate | 0.937500 | 0.929688 | 39,536.09 | +0.046875 |

The externality gate produced exactly the same screen score and OMW mirror
record as `forecast4`: 42W / 8D / 14L against OMW. It changed 82 result rows
across the full panel, including 30 OMW rows, but did not remove any of the 14
OMW losses. Its mean margin was also 15.02 lower than `forecast4`.

## Decision

Do not adopt this gate in the candidate. The particular externality estimate
and 50% threshold did not improve the target outcome; the idea should only be
revisited with a better counterfactual that models both players' coupled sell
orders rather than the current approximate rival-stream loss.
