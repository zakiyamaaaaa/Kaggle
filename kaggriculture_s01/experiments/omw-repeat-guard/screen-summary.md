# OMW forecast4 repeat-guard screen result

## Policy

The candidate is based on `omw-forecast4`. The only added rule is a per-item
4-turn cooldown on the distant (3–4 turn) forecast branch after a distant
forecast SELL fires. The immediate 1–2 turn branch is unchanged.

## Verification

- smoke: seed 993000, 8 seeds, 6 opponents, 2 seats, 288 total games
- screen: seed 994000, 32 seeds, 6 opponents, 2 seats, 1,152 total games
- all games completed; errors: 0
- 26 candidate result rows changed versus forecast4; 10 OMW-mirror rows
  changed, across seeds 994006, 994008, 994014, 994017, and 994031
- the control source and frozen OMW copy are byte-for-byte identical
- no Kaggle submission was made

## Result

| policy | aggregate score | paired delta vs control | 95% CI |
|---|---:|---:|---:|
| control | 0.8828125 | — | — |
| forecast4 | 0.9296875 | +0.046875 | [+0.015625, +0.080729] |
| repeat-guard | 0.9296875 | +0.046875 | [+0.015625, +0.080729] |

Against the OMW mirror, repeat-guard scored 42 wins / 8 draws / 14 losses,
the same as forecast4. Its opponent-balanced mean margin decreased from
39551.11 to 39548.78.

Conclusion: the 4-turn per-item cooldown changes some games but does not
reduce the 14-loss pattern and slightly worsens margin. Do not promote this
variant. The next useful test is an explicit externality-aware gate or a
price-aware per-item guard, rather than a blind cooldown.

