# OMW forecast4 capped screen result

## Policy

The candidate keeps the `omw-forecast4` confidence gate and changes only the
distant 3–4 turn branch: inserted SELL quantity is capped by the selected
stream's predicted SELL quantity over the next four turns. The immediate 1–2
turn branch is unchanged.

## Verification

- smoke: seed 993000, 8 seeds, 6 opponents, 2 seats, 192 total games
- screen: seed 994000, 32 seeds, 6 opponents, 2 seats, 768 total games
- all games completed; errors: 0
- control source is byte-for-byte identical to the frozen OMW copy
- no Kaggle submission was made

## Result

Metric: win + 0.5 × draw.

| policy | aggregate score | paired delta vs control | 95% CI |
|---|---:|---:|---:|
| control | 0.8828125 | — | — |
| capped | 0.9296875 | +0.046875 | [+0.015625, +0.080729] |

The screen score is unchanged from the previous `omw-forecast4` candidate.
The opponent-balanced mean margin moved from 39551.11 to 39553.22.

Against the OMW mirror, capped scored 42 wins / 8 draws / 14 losses, exactly
the same win/draw/loss count as the previous candidate. The 14 loss rows are
on unique seeds 994003, 994007, 994011, 994013, 994022, 994026, 994028, and
994031.

Conclusion: this quantity cap is safe on the panel and changes several
reward margins, but it does not solve the 14-loss pattern or improve the
screen score. Keep it as a diagnostic result; do not promote or submit it.
