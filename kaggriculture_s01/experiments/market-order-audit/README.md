# Market order audit (2026-09-27)

## Candidate and scope

The frozen baseline is `registry.candidate_agent`, identified in the project
README as `candidate-early-milk-v1` (the current Population Arena champion and
submitted candidate). The submitted archive is unchanged. The new local Arena
variant is `registry.candidate_zero_sell_guard_agent`. The comparison uses the
same five trading opponents, seeds and both seats for each policy. Opponents:
One More Wheat, Peak2950, Triad Counter, public Salem 2900, and the independent
`economy_mix50_waste_shield`. Seeds 996000–996007 are the screen; fresh seeds
997000–997015 are the holdout. A seed, including all opponents and both seats,
is one independent comparison sample.

## Engine-level measurements

`scripts/audit_market_order_issues.py` instruments the local Kaggriculture
interpreter's market execution. It observes the shed **after all unit actions**
and records every actual order-unit success/failure. A zero SELL is an order
that sells no units, including duplicate SELLs whose prior order depleted the
same item. Market orders execute by slot; per-unit transactions of both players
in a slot are lockstep. Failed orders terminate, and the next slot still runs.

Across the frozen baseline's 240 games (24 seeds × 5 opponents × 2 seats), all
games completed. There were **12,372 zero SELL orders on 11,892 distinct
player-turns**, or 6.89% of 172,560 candidate turns. The items were
FERTILIZER 5,082, MILK 3,277, WHEAT 2,538, STRAWBERRY 1,051, and WOOL 424.
They appeared from step 149 through 718, most frequently on days 29 (1,296),
25 (1,230), 24 (1,112), and 28 (1,076). In 8,896 cases, post-work stock was
already zero. A later SELL in the same queue **did execute** after 1,425 of
the zero orders. Thus the zero order itself did not block those later sales;
the effect is that removing it shifts a later executable order to an earlier
slot. Both policies sold exactly 330,172 units in this panel, yet 69 game
rewards changed because slot timing changes the shared-market prices.

There were **0** instances where a BUY_PRODUCT, BUY_SEED, BUY_ANIMAL, HIRE, or
BUY_LAND failed or stopped for insufficient cash and a later SELL in the same
turn executed. Consequently the measured loss from the proposed funding-order
failure was 0 on this panel, and no funding-order patch was made. This does
not prove the pattern impossible outside the tested seeds.

## Independent SELL fix and paired outcome

The local variant deletes a SELL only when the observed shed and earlier
orders prove no stock can reach it. It leaves the entire parent market queue
unchanged on turns containing DROP or PLACE, since those unit actions can
deposit stock before market execution. It also tracks earlier BUY_PRODUCT and
BUY_ANIMAL orders. The fix never edits the frozen baseline or submitted ZIP.

| Opponent | Screen baseline → fix (W-D-L) | Holdout baseline → fix (W-D-L) |
|---|---:|---:|
| One More Wheat | 0-0-16 → 0-0-16 | 0-0-32 → 0-0-32 |
| Peak2950 | 0-0-16 → 0-0-16 | 0-0-32 → 0-0-32 |
| Triad Counter | 0-0-16 → 0-0-16 | 0-0-32 → 0-0-32 |
| Public Salem | 15-0-1 → 16-0-0 | 29-0-3 → 30-0-2 |
| Economy mix50 | 16-0-0 → 16-0-0 | 32-0-0 → 32-0-0 |

Overall: 92/240 wins for baseline, 94/240 for fix; no draws. Paired win-score
change is +0.00833. The 24 seed-level deltas (each averaging ten paired games)
have a bootstrap 95% interval [0, +0.02083]; two seeds improve and none
worsen. Zero SELLs decrease from 12,372 to 3,343. There were 0 failed games
and 0 nonpositive or malformed SELL quantities in either policy. The fix is
kept as a separately named local candidate because it improved the primary
metric on both panels with no observed win regression. Its interval includes
zero, and it has not been promoted over the archived submission or submitted.

## Reproduction

From the project root, with the pinned `.venv`:

```sh
PYTHONPATH=src .venv/bin/python scripts/audit_market_order_issues.py 996000 8 /private/tmp/market-screen-base.json
AUDIT_VARIANT=zero_guard PYTHONPATH=src .venv/bin/python scripts/audit_market_order_issues.py 996000 8 /private/tmp/market-screen-fix.json
PYTHONPATH=src .venv/bin/python scripts/audit_market_order_issues.py 997000 16 /private/tmp/market-holdout-base.json
AUDIT_VARIANT=zero_guard PYTHONPATH=src .venv/bin/python scripts/audit_market_order_issues.py 997000 16 /private/tmp/market-holdout-fix.json
```

The final raw run files are currently in `/private/tmp/market-final-screen-base.json`,
`/private/tmp/market-final-screen-guard.json`,
`/private/tmp/market-final-base.json`, and
`/private/tmp/market-final-guard.json`. The project SSD had only about
32 MiB free; copying the raw JSON into this directory failed with no-space.
