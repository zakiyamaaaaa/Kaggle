# [FIXED] Submission Scoring Delays/Errors Due to GPU Capacity Constraints

- Topic ID: 712828
- URL: https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/712828
- Author: MartynaPlomecka
- Posted: 2026-06-23 14:43:05.618000
- Votes: 13
- Comments: 7
- Fetched: 2026-06-25T11:49:55Z

## Post

We are currently experiencing capacity issues on the backend due to exhaustion of available T4 GPU quota.

As a result, some submissions may remain queued and eventually fail after reaching the maximum runtime limit (currently 15 hours) without ever starting execution.

Our kernel backend team is actively working to secure additional capacity and restore normal operation as quickly as possible. 

We apologize for the disruption and appreciate your patience while we work through the issue.
We will provide further updates as soon as we have more information.

## Comments

<a id="3480880"></a>
- **Дворкин Евгений Владимирович** (2026-06-25 10:30:31.770000, votes: 0, id: 3480880)
  Hello, I've had 6 consecutive Submission Format Error. for the past 2 days. Although some of them are exactly the same, the value is slightly higher but not Timeout, but Submission Format Error

<a id="3480206"></a>
- **Yao Yan** (2026-06-24 15:36:52.343000, votes: 2, id: 3480206)
  We have cleared some backlog submissions and restored capacity. Thank you for your patience, and please feel free to report any capacity constraints you observe. We’ll continue to monitor and address them.

  <a id="3480251"></a>
  - **mikelou1** (2026-06-24 16:11:04.680000, votes: 0, id: 3480251)
    Hi. Is 1x T4 given when running or 2x? The statement says GGUF via llama.cpp on T4 GPU and isn't really specific. Thanks.

    <a id="3480271"></a>
    - **Yao Yan** (2026-06-24 16:39:06.553000, votes: 0, id: 3480271)
      Hi @mikelou1, please try T4 x2

    <a id="3480295"></a>
    - **mikelou1** (2026-06-24 16:59:32.497000, votes: 0, id: 3480295)
      Thank you!

    <a id="3480298"></a>
    - **Mark Susol** (2026-06-24 17:02:33.767000, votes: 0, id: 3480298)
      To be clear, our notebooks are pretty much simple stubs we run as T4x2 and they take 20-40 seconds. When we submit, then the same notebook is picked up during scoring but then ACTUALLY runs for 9000s etc. on the T4x2. If you do not save and submit the notebook with that accelerator, the scoring wil not automatically pick the accelerator?
      
      I push and run my notebook changes using kaggle CLI, and I have not been able to set the accelerator programatically. Having to manually set accelrator and run once, then save and submit is a tedious process and I keep forgetting the acclerator if my question above is accurate?

    <a id="3480303"></a>
    - **mikelou1** (2026-06-24 17:08:22.980000, votes: 0, id: 3480303)
      --accelerator NvidiaTeslaT4 for 2xT4 I believe (might be wrong)
