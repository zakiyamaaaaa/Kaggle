# Low-price sale deterioration study

## Scope

This study starts from the `forecast4` candidate and focuses on its 14 OMW
mirror losses in the 32-seed screen. The price-aware rule is applied only to
the distant forecast branch; immediate one- and two-turn sales are unchanged.

## Main screen

The core panel contains OMW, Peak, and Triad, 32 seeds, both seats. It is the
part of the opponent panel where the guard changes behavior.

| Policy | Core score | OMW score | Peak score | Triad score |
|---|---:|---:|---:|---:|
| Frozen control | 0.7760417 | 0.5000000 | 0.9218750 | 0.9062500 |
| forecast4 | 0.8697917 | 0.7187500 | 0.9531250 | 0.9375000 |
| Guard at base price | 0.8020833 | 0.6093750 | 0.8906250 | 0.9062500 |
| Guard at base−80 | 0.8020833 | 0.6093750 | 0.8906250 | 0.9062500 |
| Guard at base−120 | 0.8125000 | 0.6093750 | 0.9218750 | 0.9062500 |
| Guard at base−160 | 0.8385417 | 0.6250000 | 0.9531250 | 0.9375000 |

The stricter guard recovers some mean margin, but it does not recover the
forecast4 win rate. Even the least damaging tested guard remains below
forecast4 on the core score.

## Case-level conditions

The table shows the first sale directly blocked by the base−80 guard in each
unique loss seed, and the resulting OMW mirror margin. Market inventory was
near 10,000 in all cases, so inventory alone did not separate the outcomes.

| Seed | First blocked sale | forecast4 margin | base−80 margin | Result |
|---:|---|---:|---:|---|
| 994003 | WOOL ×2 at 107 | −374 | +62 | improved |
| 994007 | WOOL ×2 at 11 | −522 | −522 | unchanged |
| 994011 | WOOL ×12 at 37 | −13 | −77 | worse |
| 994013 | MILK ×3 at 55 | −342 | 0 | improved |
| 994022 | WOOL ×3 at 1 | −629 | −717 | worse |
| 994026 | WOOL ×2 at 5 | −219 | −219 | unchanged |
| 994028 | MILK ×4 at 15 | −379 | +1000 | improved |
| 994031 | WOOL ×6 at 116 | −4258 | −4808 | worse |

This gives the following findings:

1. Current price is not sufficient. WOOL at 1, 5, and 11 can be unchanged,
   while WOOL at 37 or 116 can be harmful when blocked.
2. Quantity is not monotonic. Small quantities can help, but a larger WOOL
   block can remove a sale that was strategically useful.
3. MILK is more consistently associated with improvement in this small loss
   set; WOOL is mixed. This is evidence for item-conditioned analysis, not a
   validated MILK-only rule.
4. The harmful event is not necessarily the sale's immediate cash value. A
   distant preemption can also synchronize or desynchronize the later public
   sale sequence, so removing it can change the whole trajectory.

## Conclusion

The deterioration condition is best described as:

> a distant, forecast-only pre-sale made while the item's price is already
> depressed, whose effect depends on item-specific public-sale timing and on
> whether the sale is needed for the candidate's later cash/stock trajectory.

Therefore, “price below a threshold” is a useful diagnostic feature but not a
safe standalone gate. Keep `forecast4` as the baseline and do not add the
global low-price guard. If another iteration is justified, the next test
should be a predeclared item-conditioned state machine, especially separating
MILK from WOOL and requiring evidence about the next public sale rather than
using price alone.
