# candidate-early-milk-v1

- Base: `candidate-liquidate-v3`
- Change: sell all held MILK from day 28 hour 12; retain full day-29 liquidation
- Front-running: MELON, MILK, STRAWBERRY, WOOL, WHEAT, FERTILIZER
- Development: seeds 30000–30031, both seats, 384 games, score 0.9085
- Adoption: seeds 40000–40127, both seats, 1,536 games, score 0.9333
- Final: seeds 60000–60255, both seats, 3,072 games, score 0.9394
- Final versus previous champion: 471–41, mean reward difference `+588.69`
- Final errors/timeouts: 0
- Source SHA-256: `fd01b94915ce0bfe54acb4a95f08cfacc60d68dc0ab79016c1b576863928305d`
- ZIP SHA-256: `03eef8e6d37c9f6dca41ededce861bac7a8bef6902bd2e12086c3da2bf0b4c06`
- Public evaluation: submission `56361538`, COMPLETE, Public score `977.7`
- Kaggle API record date: `2026-09-19T14:13:44.160000`

Build with:

```bash
uv run python scripts/build_candidate_submission.py \
  --variant early-milk-v1 \
  --output submissions/candidate-early-milk-v1.zip
```
