# exp-004-deputy-focus

- Name: deputy-focus
- Kaggle tag: `exp-004-deputy-focus`

## Hypothesis

exp-003 (0.060) added heavy exp-002 exfil grid and burned generation budget. exp-001 (0.255) won on cheap confused-deputy + snapshot paths.

Strategy:

1. **exp-001 core** — direct exfil + original snapshot 3 follow-ups (inside Phase 4)
2. **Deputy expansion** — more single-turn Notify/Inform/Alert + multi-turn read→forward
3. **Second snapshot** — weekly_report setup with deputy follow-ups (new cell diversity)
4. **Early stop** — return when `len(findings) >= 8` and `time_left() < 600`
5. **Gated exfil** — only 2 light attempts if `time_left() > 900` (no full grid)
6. Lower default `margin_s` (120) for cheap single-turn tries

## vs exp-003-mixed-v1

- No 15-combo exfil grid
- Deputy-first; exfil is optional bonus
- Early return preserves replay budget

## vs exp-001-baseline

- More deputy recipients and snapshot branches for unique_cells
- Dedup via `seen`
- Early return + gated exfil

## Prior scores (reference)

| exp_id | score |
|---|---|
| exp-001-baseline | 0.255 |
| exp-002-exfil-encoding | 0.0 |
| exp-003-mixed-v1 | 0.060 |
