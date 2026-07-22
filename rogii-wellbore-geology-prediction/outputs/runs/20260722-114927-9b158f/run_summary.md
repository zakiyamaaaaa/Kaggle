# Run 20260722-114927-9b158f

- Candidate: `safe_lowfreq_trend_recent250_alpha010_clip40`
- Status: `rejected`
- Hypothesis: a recent prefix-only `TVT_input`–`MD` low-frequency trend could correct last-value drift.
- Evaluation: 773 wells / 3,783,989 suffix rows; predictor used only observed `TVT_input` prefix and suffix `MD`.
- Result: RMSE `15.9700905732`; well RMSE p50/p90 `10.8245261513 / 22.4623813844`; elapsed `5.528 s`.
- Comparison: worse than last-value `15.9098529` and full-suffix HGB selector `14.7196100`.
- Decision: do not generate or promote a submission candidate. Keep trend as a possible future selector feature only.
- External actions: no Kaggle submission or public Notebook execution.
- Git: commit `5456585` created; origin/main was fetched and merge-tree had no content conflict. Push failed on DNS and the approved retry was blocked as private-workspace export, so no push was performed.

Metrics are in `low_frequency_trend_eval.json`; the rejected result is recorded in the shared experiment ledger and learning notes.
