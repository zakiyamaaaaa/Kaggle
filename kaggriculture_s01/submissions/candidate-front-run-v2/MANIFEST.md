# candidate-front-run-v2

- Base: attributed public Salem 2900 policy
- Change: add `WHEAT` and `FERTILIZER` to one-step market front-running
- Reference source SHA-256: `3b1cb91feb451b44d075d853f9211be216aea7f85df09d91fa232e4e9dff8fe9`
- Screen: seeds 12000–12015, both seats
- Validation: seeds 13000–13031, both seats
- Validation result versus calibration candidate: 61–3, mean reward difference `+292.46875`
- Paired-seed result: 32 positive, 0 negative, 0 tied
- Errors/timeouts: 0

Build with:

```bash
uv run python scripts/build_candidate_submission.py
```
