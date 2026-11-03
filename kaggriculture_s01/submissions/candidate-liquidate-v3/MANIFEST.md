# candidate-liquidate-v3

- Base: `candidate-front-run-v2`
- Change: on day 29, replace fixed SELL quantities with all currently held shed inventory
- Screen: seeds 15000–15007, both seats
- Validation: seeds 16000–16031, both seats
- Validation result versus candidate v2: 58–6, mean reward difference `+425.25`
- Paired-seed result: 32 positive, 0 negative, 0 tied
- Paired reward difference: min `+6`, median `+475.5`, max `+572`
- Errors/timeouts: 0

Build with:

```bash
uv run python scripts/build_candidate_submission.py \
  --variant liquidate-v3 \
  --output submissions/candidate-liquidate-v3.zip
```
