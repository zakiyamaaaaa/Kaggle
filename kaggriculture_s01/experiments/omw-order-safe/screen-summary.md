# OMW order-safe screen result

## Policy

The candidate is based on `omw-forecast4`. Only the distant (3–4 turn)
forecast SELL placement was changed: new orders are appended when a slot is
available, and a full market skips the new order. Existing orders are not
reordered or displaced. Quantities and the immediate 1–2 turn branch are
unchanged.

## Verification

- smoke: seed 993000, 8 seeds, 6 opponents, 2 seats, 288 total games
- screen: seed 994000, 32 seeds, 6 opponents, 2 seats, 1,152 total games
- all games completed; errors: 0
- the control source and frozen OMW copy are byte-for-byte identical
- no Kaggle submission was made

## Result

| policy | aggregate score | paired delta vs control | 95% CI |
|---|---:|---:|---:|
| control | 0.8828125 | — | — |
| forecast4 | 0.9296875 | +0.046875 | [+0.015625, +0.080729] |
| order-safe | 0.9296875 | +0.046875 | [+0.015625, +0.080729] |

The order-safe and forecast4 policies have identical per-opponent win/draw/loss
counts, mean rewards, mean margins, and paired screen rows. The same holds in
the smoke result. In particular, the OMW mirror remains 42 wins / 8 draws /
14 losses for both candidates.

Conclusion: preserving the order of newly added distant SELL orders does not
change the local arena outcome on this panel. The 14-loss regression is not
explained by this order-placement change alone, so do not promote this variant.
The next experiment should target repeated/per-item over-selling or an
explicit externality-aware margin gate.

