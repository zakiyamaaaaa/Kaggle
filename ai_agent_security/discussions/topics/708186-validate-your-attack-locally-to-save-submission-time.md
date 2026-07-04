# Validate Your Attack Locally to Save Submission Time

- Topic ID: 708186
- URL: https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/708186
- Author: Kh0a
- Posted: 2026-06-14 07:19:04.576000
- Votes: 65
- Comments: 18
- Fetched: 2026-06-27T08:42:52Z

## Post

I have created a local validation setup that runs both gpt-oss and gemma to evaluate your prompt attacks and score them based on the competition SDK.

While this setup only allows us to inspect how prompts perform against the public guardrails, it is highly useful for analyzing exactly how each prompt works. This allows you to simply submit your final prompts directly, completely bypassing the need to call the interact() method at submission time.

How to Evaluate Your Attack




Open this notebook: AAS Local Validation


Replace the placeholder script with your own attack script.


I have currently only evaluated the starter notebook, but the local score correlates quite well with the public leaderboard score.

Local Validation Results:
{
  "gpt_oss_public": 0.27,
  "gemma_public": 0.24,
  "local_public_mean": 0.255
}

Public Leaderboard Score: 0.24

## Comments

<a id="3481112"></a>
- **Shiner** (2026-06-25 16:20:35.863000, votes: 0, id: 3481112)
  Why the your local attack cost much shorter time than the submission attack? You both use T4.

  <a id="3481370"></a>
  - **MAJ0RT0M** (2026-06-25 22:42:30.420000, votes: 0, id: 3481370)
    Submission uses a remote GPU pool for replay - not kaggle gpu

<a id="3475117"></a>
- **Freak2209** (2026-06-19 11:35:33.017000, votes: 0, id: 3475117)
  I am facing issue while using this notebook

<a id="3473941"></a>
- **Navneet** (2026-06-17 08:50:00.853000, votes: 0, id: 3473941)
  Thank you for validating your attack, Trick @llkh0a

<a id="3473856"></a>
- **Mando** (2026-06-17 06:24:30.747000, votes: 3, id: 3473856)
  I want to share my result. BTW, great appreciation to KH0A

<a id="3473623"></a>
- **P.Shedrach** (2026-06-16 20:00:25.487000, votes: 0, id: 3473623)
  Is this issue specific to my setup, or are others experiencing it as well? If anyone knows what's causing it or has found a workaround, I'd really appreciate your help. Thanks!

  <a id="3473624"></a>
  - **P.Shedrach** (2026-06-16 20:02:25.677000, votes: 0, id: 3473624)
    followed by these after i clicked the "ok" button. also there is not log or printout after this sections:

  <a id="3473626"></a>
  - **P.Shedrach** (2026-06-16 20:03:11.063000, votes: 0, id: 3473626)
    @llkh0a Please i need you assistance

    <a id="3473743"></a>
    - **Kh0a** (2026-06-17 01:38:52.057000, votes: 0, id: 3473743)
      If the GPU is working, then it is fine

<a id="3473352"></a>
- **Uchechukwu Ajuzieogu** (2026-06-16 11:11:40.717000, votes: 0, id: 3473352)
  I appreciate you full time!

<a id="3472927"></a>
- **P.Shedrach** (2026-06-15 12:58:14.430000, votes: 0, id: 3472927)
  Hello @llkh0a , I’m having an issue with the notebook. When I run it, I get a restart prompt (see image below). After clicking “OK,” I also notice warnings in the outputs of ## gpt_oss and ## gemma sections, which appear to stop the notebook from executing. Please see the attached images for details.
  
  
  
  and then for the :

<a id="3472850"></a>
- **P.Shedrach** (2026-06-15 10:15:08.700000, votes: 0, id: 3472850)
  i got this specific warning "An attached model requires additional steps to be accessed. See the Models panel for details." on the notebook. Check the attached screenshot to see what i mean.
  
  Can anyone explain what this means and how i can resolve it?

  <a id="3472857"></a>
  - **Kh0a** (2026-06-15 10:37:52.210000, votes: 0, id: 3472857)
    It worked fine for me, can you screenshot the details?

    <a id="3472865"></a>
    - **P.Shedrach** (2026-06-15 11:08:48.317000, votes: -1, id: 3472865)
      has it got something to do with the llama_cp? it managed to run but i got the error as int he attached image

    <a id="3472870"></a>
    - **Giovanny Rodríguez** (2026-06-15 11:14:24.610000, votes: 1, id: 3472870)
      https://www.kaggle.com/models/llkh0a/gemma-4-26b-a4b-it-ud-q4-k-m-gguf/PyTorch/default/1   .Just sign the Google contract and you're done.

    <a id="3472878"></a>
    - **P.Shedrach** (2026-06-15 11:32:43.373000, votes: 1, id: 3472878)
      Thank you for the help. i got the warning resolved

<a id="3472539"></a>
- **P.Shedrach** (2026-06-14 12:50:45.137000, votes: 1, id: 3472539)
  I Appreciate you

<a id="3472506"></a>
- **Giovanny Rodríguez** (2026-06-14 11:15:14.057000, votes: 1, id: 3472506)
  Thank you
