# Development value model

The first value-model experiment uses the 64-game development dataset in
`outputs/datasets/development_32seed_v1`. It is intentionally a pipeline
sanity check, not yet a policy component.

## Run

```bash
uv run python scripts/train_value_model.py \
  --data outputs/datasets/development_32seed_v1 \
  --output outputs/models/value_candidate_dev_v1
```

The default experiment selects only `candidate` observations and samples every
12th decision. It trains on 24 seeds and validates on 8 interleaved seeds.
Both seats from a paired evaluation stay on the same side of the split.

## Leakage controls

- `policy`, `opponent`, seat, seed, game IDs, and pair IDs are excluded.
- Final rewards, win labels, reward differences, and chosen actions are excluded.
- Numeric columns that are constant in this dataset are excluded.
- The model is fitted only on candidate rows. Mixing candidate and public_salem
  would let policy identity explain the outcome because candidate lost all 64 games.

## Development result

The target is the candidate's final reward minus the opponent's final reward.
The validation set contains 960 sampled states from 16 games over 8 seeds.

| Model | Validation MAE | Validation RMSE | Validation R2 |
|---|---:|---:|---:|
| Training-set global mean | 17,266.7 | 18,833.2 | -0.047 |
| Time-only mean | 17,266.7 | 18,833.2 | -0.047 |
| Histogram gradient boosting | 12,049.8 | 15,924.0 | 0.251 |

The tree model reduces validation RMSE by 15.4% and MAE by 30.2% versus the
global-mean baseline. This confirms that the recorded state contains useful
signal and that the end-to-end training path works. It does **not** establish
that the estimate improves action selection: the sample has only 32 seeds, one
opponent, and no candidate wins.

## Artifacts

- `value_model.joblib`: fitted pipeline plus the exact feature list
- `metrics.json`: baseline and model metrics
- `predictions.parquet`: out-of-split-labelled predictions for analysis
- `feature_summary.csv`: feature types, ranges, cardinalities, and missingness
- `data_split.json`: exact train/validation seeds and pairs
- `eda_summary.json`: dataset, target, sampling, and limitation summary

## Next experiment

Do not wire this model into `agent(obs)` yet. First collect trajectories against
several opponents or policy snapshots that produce both wins and losses. Then
evaluate a candidate policy change in the Arena using 32 paired seeds. Promote
only changes that survive the planned 128-seed paired evaluation.
