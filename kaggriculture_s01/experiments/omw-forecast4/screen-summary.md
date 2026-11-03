# OMW forecast4 local result

Date: 2026-09-24

## Frozen parent and change

- Parent: One More Wheat source at `references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py`
- Frozen parent SHA-256: `10f58185b916392ca39697c83f67f455df81a74dfb6eb1aacd60fd81d50c9970`
- Candidate: `main.py`
- Change: only a forecast4 overlay on the existing `v9/2 PREDICT` layer
- Immediate 1–2 turn behavior remains unchanged; 3–4 turn signals require at
  least 3 matches and 70% precision over 240 turns with ±1 turn tolerance.

## Smoke

Command used:

```text
PYTHONPATH=src .venv/bin/python scripts/evaluate_omw_forecast4.py \
  --seed 993000 --seeds 8 --workers 4 \
  --output experiments/omw-forecast4/smoke.json
```

The evaluator uses the full six-opponent panel, so this was 192 games per
policy (8 seeds × 6 opponents × 2 seats). All 384 games completed with zero
errors.

| policy | panel score | mean balanced margin | paired score delta |
|---|---:|---:|---:|
| frozen OMW | 0.864583 | 40,860.14 | — |
| forecast4 | 0.937500 | 40,928.16 | +0.072917 |

## Screen

Command used:

```text
PYTHONPATH=src .venv/bin/python scripts/evaluate_omw_forecast4.py \
  --seed 994000 --seeds 32 --workers 8 \
  --output experiments/omw-forecast4/screen.json
```

This was 768 games per policy (32 seeds × 6 opponents × 2 seats), all
completed with zero errors.

| opponent | frozen OMW | forecast4 | forecast4 mean margin |
|---|---:|---:|---:|
| OMW | 2W / 60D / 2L | 42W / 8D / 14L | 257.5 |
| Peak | 59W / 0D / 5L | 61W / 0D / 3L | 1,299.2 |
| Triad | 58W / 0D / 6L | 60W / 0D / 4L | 1,360.1 |
| Salem | 63W / 0D / 1L | 63W / 0D / 1L | 33,504.6 |
| early-milk | 63W / 0D / 1L | 63W / 0D / 1L | 33,801.6 |
| baseline | 64W / 0D / 0L | 64W / 0D / 0L | 167,083.7 |

Panel aggregate:

- frozen OMW: score `0.8828125`, balanced mean margin `39,487.89`
- forecast4: score `0.9296875`, balanced mean margin `39,551.11`
- paired score delta: `+0.046875`
- seed-bootstrap 95% interval: `[+0.015625, +0.080729]`

## Decision

The overlay passes the local screen on the primary paired score and has no
regression against Peak, Triad, Salem, early-milk, or baseline in this panel.
However, it is not promoted over the frozen OMW yet: the OMW mirror matchup has
14 losses, and this screen is only 32 seeds. Keep both files and require a
larger validation on fresh seeds before any submission decision.
