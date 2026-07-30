from pathlib import Path

import numpy as np
import pandas as pd


DATA_ROOT = Path('/kaggle/input/rogii-wellbore-geology-prediction')
TEST_ROOT = DATA_ROOT / 'test'
SAMPLE_PATH = DATA_ROOT / 'sample_submission.csv'


def well_name(path: Path) -> str:
    return path.stem.split('__horizontal_well', 1)[0]


predictions = {}
horizontal_files = sorted(TEST_ROOT.glob('*__horizontal_well.csv'))
for path in horizontal_files:
    df = pd.read_csv(path).reset_index(drop=True)
    known = pd.to_numeric(df['TVT_input'], errors='coerce').to_numpy(dtype=float)
    known = known[np.isfinite(known)]
    unknown = ~np.isfinite(pd.to_numeric(df['TVT_input'], errors='coerce').to_numpy(dtype=float))
    if len(known) == 0:
        raise ValueError(f'No known TVT_input values: {path}')
    last_value = float(known[-1])
    for row_index in np.flatnonzero(unknown):
        predictions[f'{well_name(path)}_{int(row_index)}'] = last_value


sample = pd.read_csv(SAMPLE_PATH)
submission = sample[['id']].copy()
submission['tvt'] = submission['id'].map(predictions)
if submission['tvt'].isna().any():
    missing = int(submission['tvt'].isna().sum())
    raise ValueError(f'Missing predictions for {missing} submission rows')
submission.to_csv('/kaggle/working/submission.csv', index=False)
print(f'wells={len(horizontal_files)} rows={len(submission)}')
print(submission.head())
