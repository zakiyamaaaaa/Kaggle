# ROGII local improvement run

- run_id: `20260722-112837-f72vd`
- branch: `codex/rogii-loop-20260722-112837-f72vd`
- worktree: `/private/tmp/rogii-loop-20260722-112837-f72vd`
- candidate: supervised HGB candidate selector with residual guard `±20 ft`
- hypothesis: narrowing the existing `±40 ft` guard will reduce large hidden-test-sensitive corrections while retaining the selector signal

## Leakage-safe evaluation

- data: 773 training wells, 3,783,989 suffix rows
- split: GroupKFold(5), grouped by well
- features: causal horizontal-well GR/MD/XYZ, observed `TVT_input` prefix, typewell TVT/GR, and prefix-only neighboring-well spatial metadata
- target use: suffix `TVT` used only as target/evaluation value
- candidate baseline RMSE: `15.5180227795`
- HGB raw RMSE: `14.7196100149`
- HGB `±40 ft` RMSE: `14.7212187583`
- HGB `±20 ft` RMSE: `14.6416272681`
- `±20 ft` well RMSE p50/p90: `10.0419284572 / 20.9248331521`
- evaluation elapsed: `688.234 sec`
- status: `improved`

## Output verification

`outputs/submissions/learned_selector_hgb_clip20.csv` has 14,151 rows, the exact `sample_submission.csv` ID order, zero null predictions, zero duplicate IDs, and prediction range `11592.9542`–`12235.2147`.

No Kaggle API, competition submission, public Notebook execution, or GitHub push was performed. The common lock was acquired only for the short ledger/note update and commit preparation, then released after the update.

Logs:

- `smoke.log`
- `full_suffix_clip20.log`
- `full_suffix_clip20_stats.log`
- `generate_clip20.log`

## Git synchronization

- Fetched `origin/main` read-only after the commit; fetched ref was `13cd87b`.
- `git merge-tree` reported conflicts in unrelated `ai_agent_security` registry/kernel metadata files.
- No merge, force push, or GitHub push was attempted; the dedicated branch and this run report retain the conflict record.
