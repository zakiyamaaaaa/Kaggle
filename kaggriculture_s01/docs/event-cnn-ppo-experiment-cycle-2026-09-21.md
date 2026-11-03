# Event CNN PPO experiment cycle — 2026-09-21

## Decision

Keep `event-cnn-ppo-omw-v1` as the incumbent event model. Do not promote the
stable-counterfactual retrain, feature-schema-v2 BC model, or feature-schema-v2
PPO model. No Kaggle submission was made.

## Six-opponent evaluation

The reusable evaluator compares the learned event policy with fixed OMW-002 on
OMW, Peak, Triad, Salem, early-milk, and baseline opponents.

| Screen | Learned | Fixed OMW-002 | Paired delta | 95% bootstrap CI | Errors |
|---|---:|---:|---:|---:|---:|
| 8 seeds, 96 games/policy | 0.9896 | 0.8646 | +0.1250 | [+0.0417, +0.2188] | 0 |
| 32 seeds, 384 games/policy | 0.9688 | 0.9323 | +0.0365 | [-0.0052, +0.0833] | 0 |

On the 32-seed screen, OMW improved by +0.2813. Peak and Triad each regressed
by -0.0313; their confidence intervals included zero. The aggregate interval
also included zero, so the model did not advance to validation.

## Action ablation

On the 8-seed OMW/Peak/Triad screen, the learned policy scored 1.000. Constant
policies scored 0.771 for half, 0.750 for skip, and 0.729 for full. The result
rejects the explanation that the gain comes only from choosing a single
conservative action.

## Counterfactual repair

Counterfactual interventions are now matched by seed, seat, step, item,
quantity, image, and scalar encoding. Raw callback index is no longer accepted
as identity. Dataset output includes duplicate, tie, and feature-saturation
diagnostics.

The stable v1 dataset used 8 seeds and produced 64 labels: 32 skip, 18 half,
and 14 full. Its exact-context duplicate rate was 42.9%, tie rate was 31.3%,
and `market_inventory` was saturated in 100% of 224 captured events. A model
retrained from it scored 0.9688 on an 8-seed panel, while the original v1 model
scored 1.000 on the identical seeds. The retrain was rejected.

## Feature schema v2

Schema v2 preserves v1 inference exactly for existing artifacts. It replaces
clipped market inventory with normalized `log1p` inventory and adds
exposure-per-unit and net-stock-ratio features. The v2 8-seed dataset produced
64 labels (34 skip, 23 half, 7 full), a 31.9% duplicate rate, 34.4% tie rate,
and zero saturated scalar features.

On a fresh 8-seed six-opponent panel:

| Policy | Score | Delta vs fixed | Peak delta | Triad delta |
|---|---:|---:|---:|---:|
| Fixed OMW-002 | 0.9583 | reference | reference | reference |
| Feature-v2 PPO | 0.9167 | -0.0417 | -0.1250 | -0.1250 |
| Feature-v2 BC only | 0.8958 | -0.0625 | -0.1250 | -0.1250 |

Both feature-v2 models were rejected. Removing saturation was correct, but the
small, duplicated, tie-heavy supervision is insufficient.

## Hard-gate sweep

The sweep covered buffer 8/12/16 and exposure 0.5/1/2 on OMW, Peak, and Triad:
432/432 games completed with zero errors. All learned settings went 24-0-0 on
the four-seed screen. Buffer 16 had the largest mean margin (+1651.33), but the
screen was saturated at 100% win rate. Exposure 0.5/1/2 produced identical
results and action counts, showing that this threshold was inactive on the
sampled event distribution. No gate change was promoted.

## Next experiment

Generate substantially more stable counterfactuals across multiple opponent
families, deduplicate exact contexts, and train from soft margin/ranking targets
instead of hard argmax labels. Split by seed and opponent family. Only then
compare v1 and v2 encoders, with OMW/Peak/Triad regression gates applied before
larger validation.

