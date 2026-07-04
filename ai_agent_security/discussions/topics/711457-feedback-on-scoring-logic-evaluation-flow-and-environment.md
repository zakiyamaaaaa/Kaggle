# Feedback on Scoring Logic, Evaluation Flow, and Environment

- Topic ID: 711457
- URL: https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/711457
- Author: hiyodori411
- Posted: 2026-06-21 13:20:08.402000
- Votes: 41
- Comments: 14
- Fetched: 2026-06-27T08:42:53Z

## Post

Hello. 

First of all, I would like to express my gratitude to the hosts for organizing this competition. However, after working on this competition for about 10 days, several issues have become apparent. Some of these may overlap with points raised by other participants across multiple threads. Nevertheless, since many of these concerns do not seem to have received sufficient responses, I would like to lay them out here, regardless of the overlap.

The Score Function encourages simple loops

The current score function does not seem to reflect the intended goal of the competition. Specifically, the score monotonically increases simply by repeating the exact same successful attack action.

This behavior forces participants to find an attack that maximizes the score per second, and then blindly repeat it until the time limit runs out. This does not align with the core objective of proposing algorithmic methods to explore vulnerabilities. Furthermore, since participants cannot know the exact latency of the replay environment, this creates an unnecessary "game of chicken" where we must guess how many times to repeat the attack without hitting a timeout.

To address this, the scoring system should be designed so that the exact same finding is rewarded only once.

Weak correlation between Public and Private Leaderboards

While I understand the importance of preventing overfitting to the Public Leaderboard, the current issue is that the public guardrail and the private guardrail seem to be completely distinct, single entities.

Because of this, the public score fails to act as a reasonable surrogate metric for the effectiveness of our algorithms. Specifically, the current OptimalGuardrail used in the public environment virtually nullifies two out of the four attack types, making a strategy that simply sends a fixed embedded string via http.post excessively strong. This makes designing an exploration algorithm incredibly difficult. We cannot validate half of the attack types on the public leaderboard, and the public score fails to reward smart exploration algorithms. As a result, guessing the hidden properties of the private guardrail will heavily dictate the final standings. The public score must provide a functional feedback loop for development.

Evaluation on a single Private Guardrail introduces high variance

The final standings are determined by a private guardrail evaluation. However, using only a single type of private guardrail is problematic.

This competition should ideally evaluate the generalization capability of attack exploration methods across diverse guardrails. Evaluating on just one guardrail turns the final result into a gamble. A robust, generalized method might perform poorly if it happens to have bad compatibility with that specific guardrail. Conversely, a narrow method with limited general capability might rank high just by luck. This high variance will drastically lower the correlation between a team's actual methodological merit and their leaderboard position. To properly measure generalization, evaluations should be conducted across multiple distinct guardrails and aggregated.

Evaluation flow and Time-Based Side-Channel risks

There is still ambiguity regarding whether independent exploration phases are executed for public and private environments.

If the exploration phase runs only once and the generated findings are evaluated by both public and private guardrails, the private leaderboard only measures how well the pre-generated findings bypass the private guardrail. It fails to evaluate the agent's ability to adapt using feedback from the private guardrail.

On the other hand, if independent exploration phases are run for the public and private environments, the current infrastructure may expose a timing side channel that participants could use to infer properties of the private guardrail. Based on my observations, my submissions take roughly 10 hours to process. This leads me to infer that scores might be returned only after both public and private evaluations are fully completed.

Under this setup, participants can utilize the submission processing time as a side channel to leak information about the private guardrail. For example, to determine whether the private guardrail bans http.post, the algorithm could attempt an http.post during the exploration phase. If it succeeds, the submission could immediately return an empty list of findings to finish the execution instantly. If it gets blocked, the submission could return a long list of findings that takes hours to replay. If the private guardrail allows http.post, the submission finishes in minutes with a 0.0 score. If it is banned, the evaluation runs for hours. By measuring this response time, participants can systematically map out the private guardrail policies during the competition period.

A similar timing side-channel may exist even if the exploration phase runs only once. During the replay phase, a pre-generated, multi-hop finding could include a later-turn prompt that instructs the agent to inspect the output of an earlier tool call. Depending on whether that tool call was allowed or denied, the agent would then switch between a shorter or longer execution sequence. Repeating such findings could amplify the resulting difference in total evaluation time.

GPU throughput mismatch in the scoring environment

As previously pointed out by user Kawasaki ( @zhtngr ), there is a massive difference in execution time between the Kaggle Notebook T4 GPU and the actual scoring environment.

In a standard notebook, replaying 2,000 findings does not take 9,000 seconds. However, in almost all actual submissions, replaying just 600 to 800 findings consumes nearly the entire 9,000-second budget.

While the hosts have stated that GPUs are utilized in the competition, the throughput we are observing does not match what is expected from a T4 GPU in a Kaggle Notebook. We need a clear clarification on the resource allocation and potential bottlenecks in the backend.

I would highly appreciate hearing the thoughts of @owenvallis on these points. Thank you again for hosting this challenging competition, and I hope these observations help improve the experience for everyone.

## Comments

<a id="3481516"></a>
- **Manish Bhatt** (2026-06-26 05:56:54.853000, votes: 0, id: 3481516)
  Special thanks to you for breaking this down for me. :) I posted a clarification - https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/714340
  
  Offline diversity, not online diversity. But the sdk is public, so you can make an online agent produce the data "offline" (look in "map elite direction" for algorithms). Thank you!

  <a id="3481587"></a>
  - **Shiner** (2026-06-26 07:55:39.957000, votes: 0, id: 3481587)
    @theprofe1321 Thx for clarification, can you explain GPU throughput mismatch in the scoring environment problem.  Is it caused by private leadborad? Or the submission SDK settup is different from the public SDK (like: submission SDK loads the GPT and Gemma model on CPU instead of GPU?)

    <a id="3482144"></a>
    - **Manish Bhatt** (2026-06-26 21:16:18.783000, votes: 0, id: 3482144)
      The problem being public may not time out but private may?

<a id="3481119"></a>
- **Shiner** (2026-06-25 16:26:40.830000, votes: 0, id: 3481119)
  Sadly, they didn't talk about GPU throughput mismatch in the scoring environment

  <a id="3481187"></a>
  - **MAJ0RT0M** (2026-06-25 17:47:07.557000, votes: 0, id: 3481187)
    IMO the private environ probably uses llm-as-a-judge somewhere in the private guardrail implementation - which explain lower throughput

    <a id="3481579"></a>
    - **Shiner** (2026-06-26 07:46:36.653000, votes: 0, id: 3481579)
      Make sense, I agree.

<a id="3480427"></a>
- **** (2026-06-24 20:02:27.643000, votes: -1, id: 3480427)

<a id="3478632"></a>
- **Renee** (2026-06-22 21:34:12.250000, votes: 0, id: 3478632)
  I also really like your comments about side channel attacks. Of course this would be mitigated by your suggestion of using multiple guardrail evaluators. I would also much prefer the scenario where the attack.py is run multiple times, at least once for each leaderboard. That would allow us to adapt our attack.py to the changing environment and be more aligned to real world scenarios, where an attack algorithm responds to the unique constraints and characteristics of its environment. I suspect this is not what they are doing because of the increased computational time it would take to run the full set of attack rules against both environments. However, I think there are ways they could reduce the computational burden on their end to make this less of a problem. For example, I am unsure why they run the attacks through two separate LLM models. I believe it would be worth it to reduce it to a single LLM, and the insights provided by allowing hackers that extra attack time and more precise focus would be more valuable than seeing how their solutions fare against multiple very similar models.

<a id="3478624"></a>
- **Renee** (2026-06-22 21:25:06.830000, votes: 0, id: 3478624)
  I think it may be interesting / helpful if they adjusted the cell hashing system to be influenced / determined by the contents of the attack cell. Even just MD5 hashing the contents of the "attack cell" and setting that to the hash would mean that every attack example would have to have at least a little variation in order to score points. I imagine this would also give the organizers more helpful data since the variety of strategies and the techniques people use to induce variation could be helpful for other security challenges.

  <a id="3479374"></a>
  - **MAJ0RT0M** (2026-06-23 17:54:22.417000, votes: 0, id: 3479374)
    Personally I think this is a bad idea 
    
    Already we can repeatedly score 16 points by replaying duplicate cell attacks 
    
    Increasing hash granularity would mean that we can more easily score the 2pt unique cell bonus on top of that
    
    IMO cell granularity should be decreased and there should be diminishing returns to attacks w/ duplicate cells

    <a id="3479528"></a>
    - **Renee** (2026-06-23 21:02:46.097000, votes: 0, id: 3479528)
      I think you may have misunderstood me. Having the hash determined by content of attack cell would mean that the hash would not automatically be unique for every single attack regardless of actual content. The way it works now, the hash is generated uniquely for every cell regardless of content. That's why the best scoring solutions right now are typically just the same attack run in a loop over and over. Setting hash from content would mean that attacks with the same content and text would automatically be given the same hash and when scored would only be counted once. This would make it harder to score the 2pt unique cell bonus because the cell would actually be identified as non-unique by the hash.

    <a id="3480414"></a>
    - **MAJ0RT0M** (2026-06-24 19:41:29.610000, votes: 0, id: 3480414)
      I think we are saying the same thing but somehow reaching different conclusions - so I think I must be misunderstanding you
      
      Or - maybe I don't understand the public scoring function
      
      My understanding is that 
      
      
      
      based off some trace metadata, including tool calls, # of tool calls, some metadata on tool call (e.g. url), a hash is determined for a trace - we then call this a "cell"
      
      based of the predicate that fires for a cell, we get some score - for severity 5 predicate we get 16 pt (in general, score is 2^severity)
      
      this score can be earned endlessly for the same cell
      
      but additionally, for a unique cell, we earn an additional 2 bonus points
      
      
      I think you are suggesting adding additional content to the input we compute cell hash from - which would increase the # of cells
      
      I think this would not decrease score earned for 2/3 - but would increase the score earned for 4
      
      Is that right? or am I misunderstanding something

    <a id="3482146"></a>
    - **Renee** (2026-06-26 21:19:46.527000, votes: 0, id: 3482146)
      Yup, slight misunderstanding! I'm not suggesting any additional content. Rather my suggestion is taking the cell generated for an attack, hashing it, and appending that hash to the cell afterwards. With this attacks that are exactly the same are given the same hash, and are only counted once by the scorer.

<a id="3477524"></a>
- **Shiner** (2026-06-21 17:01:37.413000, votes: 3, id: 3477524)
  I was about to post threads about question about guardrail and replay time as well, thx @hiyodori411sekirei
