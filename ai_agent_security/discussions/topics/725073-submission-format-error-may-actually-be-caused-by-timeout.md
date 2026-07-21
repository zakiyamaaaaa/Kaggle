# Submission Format Error may actually be caused by timeout, not by a bad CSV format

- Topic ID: 725073
- URL: https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/725073
- Author: KALYPHEUS
- Posted: 2026-07-14 (approx.; page shows "4 days ago" as of 2026-07-18)
- Votes: 4
- Comments: 0 (no replies visible without sign-in at fetch time)
- Fetched: 2026-07-18T04:59:00Z

## Post

I checked the official gateway code, and I think Submission Format Error may not necessarily mean that your submission.csv has the wrong columns or formatting.

Another possible cause is:

a timeout during attack generation or replay causes the gateway to raise INVALID_SUBMISSION, so the final valid submission.csv is never written.

Here is why I think so.

In the base gateway, the submission file is written only after all predictions are successfully completed.

Path: ai-agent-security-multi-step-tool-attacks/kaggle_evaluation/core/base_gateway.py

Relevant code:

```
predictions, row_ids = self.get_all_predictions()
self.write_submission(predictions, row_ids)
```

So if get_all_predictions() fails at any point, write_submission() is never reached.

In this competition-specific gateway, submission.csv is written only at the very end.

Path: ai-agent-security-multi-step-tool-attacks/kaggle_evaluation/jed_attack_134815/jed_attack_gateway.py

Relevant code:

```
with open("submission.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Id", "Score"])
    for row_id, score in predictions["row_scores"].items():
        writer.writerow([row_id, score])
```

So the CSV is not produced incrementally during evaluation. It is written only after the full evaluation finishes successfully.

More importantly, timeout exceptions are explicitly converted into INVALID_SUBMISSION.

Path: ai-agent-security-multi-step-tool-attacks/kaggle_evaluation/jed_attack_134815/jed_attack_gateway.py

Relevant code:

```
except (ModelAttackTimedOut, ModelEvaluationTimedOut) as err:
    raise GatewayRuntimeError(
        GatewayRuntimeErrorType.INVALID_SUBMISSION,
        str(err),
    ) from err
```

INVALID_SUBMISSION is an official gateway error type.

Path: ai-agent-security-multi-step-tool-attacks/kaggle_evaluation/core/base_gateway.py

Relevant code:

```
INVALID_SUBMISSION = 6
```

Based on this, my current understanding is:

If attack generation or replay times out for any model, the gateway may raise INVALID_SUBMISSION immediately, and the normal final submission.csv may never get written. In that situation, the Kaggle UI may show Submission Format Error, even though the real problem is not the CSV schema itself.

So for this competition, Submission Format Error may sometimes actually mean:

- evaluation did not finish
- a model timed out
- the gateway marked the run as invalid

rather than:

- wrong CSV header
- wrong number of columns
- malformed CSV file

If others have already verified that their CSV format is correct but still see this error, I'm wondering whether the timeout / interrupted evaluation path might also be a possible cause here. I'd love to hear your thoughts — does this reasoning make sense, or am I missing something?

## Comments

(No replies visible without sign-in at fetch time.)
