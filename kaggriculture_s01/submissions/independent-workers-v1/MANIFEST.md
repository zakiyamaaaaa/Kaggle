# independent-workers-v1

- No fixed action replay and no import from the Salem submission
- Replans from the current observation every step
- Eight daily hands manage all 25 NW plots
- MELON production followed by late WHEAT production
- Deterministic task priority: water, harvest, dig, plant, transport
- Registry agent: `independent_workers`
- Environment: `kaggle-environments==1.32.7`
- Validation: seeds 19400–19431, both seats
- Result versus baseline: 64–0, mean reward `30,144.046875`, mean difference `+26,608.203125`
- Result versus current Salem-family candidate: 0–64
- Errors/timeouts: 0
- Source SHA-256: `95665ed3b202e9b923cebc63031d2c1534853477faa141bb52a33d51ec1965de`
- ZIP SHA-256: `5007bc2726c5205342744a14d6638944007e7b0a84400e86c2190bad1a27bef8`
- Status: safe independent calibration submission; not a replacement for the current champion

Build with:

```bash
uv run python scripts/build_independent_submission.py
```
