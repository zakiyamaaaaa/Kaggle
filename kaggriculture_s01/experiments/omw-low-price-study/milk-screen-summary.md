# MILK-only low-price guard: battle evaluation

## Policy tested

Starting from `forecast4`, only distant forecast-only MILK sales were blocked
when the current MILK price was at or below 80. Immediate sales and all other
items were unchanged.

Evaluation: 32 seeds × 6 opponents × 2 seats, 1,152 games per three-policy
comparison panel, with no errors.

## Results

| Policy | Overall score | Mean balanced margin | OMW | Peak | Triad |
|---|---:|---:|---:|---:|---:|
| Frozen control | 0.882813 | 39,487.89 | 0.500000 | 0.921875 | 0.906250 |
| forecast4 | 0.929688 | 39,551.11 | 0.718750 | 0.953125 | 0.937500 |
| MILK-only guard | 0.895833 | 39,525.29 | 0.609375 | 0.890625 | 0.906250 |

Against the OMW mirror, forecast4 had 42W / 8D / 14L. The MILK-only guard had
28W / 22D / 14L: it did not reduce the 14 losses and converted several wins
into draws. It also reduced the Peak and Triad scores.

## Decision

Do not adopt the MILK-only low-price guard. The earlier loss-case signal was
real as a diagnostic clue, but it does not generalize as an action rule. Keep
`forecast4` as the candidate baseline.
