# Local / Public evaluation tracking

Public evaluation is used as an external calibration signal, not as the main
optimization loop. Keep the submitted ZIP immutable and join its score to the
local result by candidate ID and source SHA-256.

## First calibration candidate

| Candidate | Source SHA-256 | Local panel | Paired games | Win rate | Mean reward difference | Public score |
|---|---|---|---:|---:|---:|---:|
| `candidate-calibration-v1` | `3b1cb91f...dff8fe9` | baseline | 64 | 100% | +147,768.5 | 846.0 |

Kaggle submission ref `56348566` completed on 2026-09-19 and showed Public
score `846.0` in the latest CLI snapshot. An earlier submission described as the public
Salem reference (`56186872`) had Public score `974.2`, but its exact submitted
source hash was not recorded in the Kaggle description. Treat it as a
same-family historical result, not proof that an identical artifact received
two scores. Use a multi-candidate calibration set and do not promote a
candidate from local win rate alone.

## Frozen local correlation panel

For candidate-to-candidate correlation, use seeds 17000–17031 with both seats
against the immutable `public_salem` reference. The first candidate is the
reference itself, so its local reward difference is zero by definition.

| Candidate | Source SHA-256 | Games | Win rate vs reference | Mean reward difference | Public score |
|---|---|---:|---:|---:|---:|
| `candidate-calibration-v1` | `3b1cb91f...dff8fe9` | reference | reference | 0.0 | 846.0 |
| `candidate-front-run-v2` | `8dc0fd92...be9362` | 64 | 93.75% | +270.30 | 761.2 |
| `candidate-liquidate-v3` | `5c113946...dedecd` | 64 | 93.75% | +727.09 | 779.7 |

Historical Kaggle CLI snapshot checked on 2026-09-19 14:17 JST:

| Candidate | Submission ref | Status | Public episodes | Public score snapshot |
|---|---:|---|---:|---:|
| `candidate-calibration-v1` | `56348566` | COMPLETE | 4 | 846.0 |
| `candidate-front-run-v2` | `56348673` | COMPLETE | 3 | 761.2 |
| `candidate-liquidate-v3` | `56348847` | COMPLETE | 2 | 779.7 |
| `candidate-early-milk-v1` | `56361538` | COMPLETE | — | 977.7 |

## Previous CLI snapshot (2026-09-20)

The latest read-only `kaggle competitions submissions kaggriculture --format json`
query returned `candidate-early-milk-v1.zip` as the newest submission:

| Candidate | Submission ref | API date | Status | Public score |
|---|---:|---|---|---:|
| `candidate-early-milk-v1` | `56361538` | `2026-09-19T14:13:44.160000` | COMPLETE | **977.7** |
| `candidate-liquidate-v3` | `56348847` | `2026-09-19T05:03:43.473000` | COMPLETE | 1004.9 |
| `candidate-front-run-v2` | `56348673` | `2026-09-19T04:55:27.373000` | COMPLETE | 1000.1 |
| `candidate-calibration-v1` | `56348566` | `2026-09-19T04:50:23.237000` | COMPLETE | 846.0 |

The new MILK candidate is currently below the v2/v3 Public snapshots (977.7 vs
1000.1/1004.9), despite its substantially stronger held-out local Population
Arena result. This is evidence that local opponent strength and the live Public
rating are not identical; it is not evidence of a local execution mismatch.
The ZIP/source hash recorded in the submission description matches the local
manifest: source SHA-256 `fd01b94915ce0bfe54acb4a95f08cfacc60d68dc0ab79016c1b576863928305d`.

These values are live ratings, not fixed-test scores. The official evaluation
continuously matches submissions against similarly rated bots and updates the
rating from wins, losses, and ties; coin margin is ignored. The CLI returns
historical submissions, while each Public score can move as more episodes are
played. Therefore dated snapshots must not be treated as immutable fixed-test
scores. With only a small number of Public episodes per candidate, none of these
snapshots alone is suitable for estimating local/Public correlation.

The v3 candidate also beat v2 56–8 with mean reward difference `+436.42` on
the same seeds. Public scores must be joined by the exact ZIP/source hashes;
do not substitute a rebuilt or edited archive under the same candidate ID.

The candidate is the attributed public Salem policy and is not an original
improvement. Its purpose is to anchor the scale before submitting independently
developed variants.

## Latest independent submission snapshots (2026-09-21)

| Candidate | Submission ref | ZIP SHA-256 | Status | Public score |
|---|---:|---|---|---:|
| `independent-economy-v4` / `economy_mix50` | `56396545` | `c13e88c9...014dcb` | COMPLETE | **599.5** |
| `macro-bc-ppo-league-v1` / `macro_bc_ppo_v1` | `56397965` | `1baff22b...a40a8a2` | COMPLETE | **560.6** |

The economy submission used the locally verified
`submissions/independent-economy-v4.zip`. Its local holdout was 7,680 games
with a positive paired score delta versus `planner_cows8`, and its live Public
rating was 599.5 at this snapshot. The local holdout also had
`economy_mix50` lose 510 of 512 games to `candidate`, so retaining `candidate`
as the main policy is directionally consistent with the Public result. Because
`planner_cows8` was not submitted for Public evaluation, this result does not
show whether the measured improvement over `planner_cows8` transferred to the
live opponent distribution.

The later macro-policy submission used
`submissions/macro-bc-ppo-league-v1.zip`. Its Public rating was 560.6 at this
snapshot. Its local manifest records 600.0 from an earlier check; the difference
is expected for a live rating and must not be interpreted as an artifact change.
Use these results to prioritize opponent-distribution and market-behavior
diagnostics, while retaining the exact ZIP hash and observation time for every
comparison.

## One More Wheat initial snapshot (2026-09-21)

| Candidate | Submission ref | Archive SHA-256 | Status | Public score | Public episodes |
|---|---:|---|---|---:|---:|
| `one-more-wheat-v1` | `56409440` | `4fd9470d...33fcec0` | COMPLETE | **706.1** | **1** |

The initial 600.0 snapshot had only validation episode `111423009`. The first
public episode, `111424300`, was a 141,033–52,356 win over Artem Zenkevich and
moved the display to 706.1. One game is still far too little to compare with
Salem's mature 974.2 snapshot.
The submitted tar contains `LICENSE.txt`, `NOTICE.txt`, and `main.py`; its
`main.py` exactly matches the downloaded public source with SHA-256
`10f58185b916392ca39697c83f67f455df81a74dfb6eb1aacd60fd81d50c9970`.
The local evidence remains 48 wins from 48 paired games against `public_salem`,
but its transfer to the live opponent distribution is unresolved until public
episodes accumulate.

## Correlation protocol

For every later submission, record the exact ZIP hash, local seed range,
opponent panel, paired win rate, paired mean reward difference, and Public
score. Use the same frozen local panel for comparisons.

Do not report a correlation coefficient from one or two submissions. Starting
at three distinct policies, report both Spearman rank correlation and Pearson
correlation, while retaining the raw table. Five or more strategically distinct
policies are preferred because nearby variants are not independent samples.

The Public leaderboard is noisy and opponent-dependent. A single Public result
may reject a badly calibrated local metric, but should not by itself select a
new champion.
