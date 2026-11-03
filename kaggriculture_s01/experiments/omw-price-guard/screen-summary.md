# OMW price-aware item guard: verification summary

## Policy

In the distant forecast branch, a sale is blocked when the current price is at
or below the item's base price. The base prices are MILK 160, WOOL 200, and
STRAWBERRY 120. Immediate one- and two-turn sales remain unchanged.

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
| Price guard | 0.885417 | 0.885417 | 39,483.30 | +0.002604 |

The price guard improved the OMW mirror matchup substantially: 10W / 50D / 4L
versus 42W / 8D / 14L for `forecast4`. However, it gave up too much against
Peak and Triad: Peak fell to 57W / 0D / 7L and Triad to 58W / 0D / 6L. The
overall screen score therefore fell from 0.929688 to 0.885417, and the paired
confidence interval against control was [-0.018229, +0.018229], so the total
gain is not robust.

## Decision

Do not use the guard globally. It is useful evidence that low-price distant
sales are a real source of OMW mirror losses, but the hard base-price cutoff is
too conservative for the broader opponent panel. A future version should make
the guard conditional or soften it rather than applying it to every opponent.
