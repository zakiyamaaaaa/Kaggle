# Learnings from PPO to 80k terminal cash

- Topic ID: 738619
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/738619
- Author: Mark Schatza
- Posted: 2026-09-01 02:53:34.656000
- Votes: 16
- Comments: 11
- Fetched: 2026-09-12T11:44:29Z

## Post

Hey all, was not expecting RL to be such a difficult challenge compared to Orbit Wars! And I'm not the only one struggling so wanted to share how I at least got to 80k terminal cash submission (but far from the top) so maybe someone else can crack my ceiling.

Throughput
It's RL. We need to be fast. JAX end to end is what I'm using. Getting about 10k SPS throughput (although this keeps slowly getting chipped away at as I add features). Very CPU limited so rust/C++ may be a better option tbh. Telling codex to recreate with parity works great here. I enabled the full action space to the policy. Only masking illegal moves and limiting to 16 hands hired at a time. 

Warm-up
I tried two different warm-ups. First I tried rewarding each product individually from production to selling and adding them one by one. This worked for a bit, but after 5 products I had overfit the policy so much it struggled to do all 5. The next thing I did was use the open heuristic code and build some traces and train my policy only to match the heuristic replays. I didn't training for long, I believe I got to ~7% exact action parity with the replays. But that was enough to get the policy somewhat aware of how the game worked. On to real training now.

Training
Classic PPO. Nothing too crazy here. Not much hyperparameter tweaking just LR, gamma and rollout length. 50% self play/25% active opponent/ 25% bank opponents. Train for 1000 updates with 128 rollout length. Eval against active opponent. If >60% win rate add to bank (FIFO w/ 5 latest banked opponents). If >70% promote to active. With some testing I determined temperature of 0.8 best for training and 0.5 best for formal eval and submission. Much later once the policy was somewhat competent I added the heuristic as 10% of the play taking from self play. 

Reward Shaping
I started with a 75/25 reward structure. With 75% being having more sales from produced product than the opponent (note sales from produced product, not any sales…) and 25% being more terminal cash than the opponent. As I've seen many times in the discussions, this will naively produce a melon farm. To combat this I added a exploration reward. +0.2 the first time it sold any of the nine sellable products, once per game. Was massive to give it incentive to try to produce other products. Eventually inverted the 75/25 to have terminal cash be the stronger of the two once it had learned to produce 80k+ a game. Finally last piece was to add a absolute scaling from 50k up to 120k final cash reward because it got stuck trying to game the market against itself rather than improve. 

Feature
Added some history information to track how much we've produced this game already. Calculated value horizons of current farm in different buckets of the future. And gave the policy some future exact information on the town demand rather than expecting it to learn what each building does. Better exact worker information, who was holding what, some previous state information. 

Conclusion
The above got my to 80k terminal cash purely RL with full action space allowed. And then I absolutely hit a wall that I have not been able to climb out of. The logits were very saturated as they needed to be with such important per state turns, but struggled to get exploration without collapse. Critic showed really high EV, but struggled to turn that into early game rollouts. 

Next steps
I progressively over the last few weeks made updates that have made policy worse and worse. Currently trying a more hybrid approach. An entirely new policy that only tells intents of each square and whether to upkeep this turn or skip w/ a executor underneath to perform the actions. Plus market purchases/sales. This policy is surprisingly struggling to even reach the highs of the old one even trying to follow the above playbook. May hop back to that best policy and see if I can resurrect it with fresh eyes. 

Hope this helps! Best of luck RL'ing everyone. 

P.S. All of the above is hand written, but I've written the entire codebase and guided all training exclusively through the codex app on my phone. I have a tailscale connected with a live dashboard that I can check from anywhere to see how my training/evals are going. Highly recommend!

## Comments

- **hwe owe** (2026-09-03 09:55:42.890000, votes: 3)
  I am current at 8 TH place and not using rl.i am trying a strategy that ml a model to sell things on correct timing

- **yamakawanin** (2026-09-01 09:31:25.280000, votes: 3)
  To be honest, I'm not convinced RL is the right approach for this competition. Maybe I just haven't figured out how to make it work properly yet.

  - **Praveen** (2026-09-02 15:00:09.373000, votes: 0)
    It indeed isn't… Peak dp btw bro :)

  - **venks** (2026-09-03 00:41:16.513000, votes: 0)
    I was thinking that too but it seems plausible that at least one of the t30 yesterday was running RL. Haven't started anything related to RL though

- **Friaseus ** (2026-09-01 18:35:03.087000, votes: 1)
  Hey Mark, great write-up! Really impressive engineering setup, especially running the whole pipeline via Codex and Tailscale from your phone. 10k SPS in JAX is no joke.
  
  I totally agree with your conclusion in the "Next steps" section, and I think you are exactly on the right track with the hybrid approach.
  
  The main issue with pure RL in Kaggriculture is that the environment is incredibly unforgiving with its exact math. The AMM pricing curves (especially the quadratic behavior in some products) and the long time horizons (720 steps) make it a nightmare for a neural network to deduce the underlying financial formulas purely through reward shaping. It's very easy for the policy to find a local minimum (like the melon farm you mentioned) because it can't mathematically project the opportunity cost of an action 10 days into the future.
  
  The breakthrough for many successful architectures is treating this less like a traditional grid-world game and more like a Corporate Finance and Operations Research problem.
  
  If you build that "executor" layer you mentioned using deterministic pathfinding and task-assignment algorithms (like BFS or Hungarian matching) to handle the micro-logistics perfectly, your RL policy will be freed from the burden of learning how to walk without bumping into walls. You can then train your RL to act as the "CEO": making purely macro-decisions (e.g., when to buy land, which crop matches the town demand, when to hoard vs sell).
  
  Best of luck with the hybrid architecture! You've got the hardest engineering parts figured out, wrapping a heuristic executor under your policy will likely shatter that 80k ceiling.

- **Gerardo Del Toro** (2026-09-02 03:00:10.460000, votes: 0)
  Thank you very much for sharing your approach. I also participated in Orbit Wars and tried to apply RL again here. It seems the credit assignment problem and length of the game are quite an issue here. +1 -1 rewards are not enough signal haha.
  
  May I ask whether your reward shaping of having more sales than the opponent is a +1 -1 zero sum reward, a quantity reward, and whether it's per turn or also terminal?
  
  Also, I am quite concerned about for how long your train took to get some learning and these results. Was it 100M steps or how far?

  - **Mark Schatza** (2026-09-02 03:41:27.657000, votes: 0)
    I tried all kinds of things with varying success. Most success I had was with splitting 0.75 reward for winning on cash and 0.25 reward with beating on produced sales revenue. And then added some small rewards on top of that for absolute cash trying to entice it to win by producing more rather than just putting its opponent down. 
    
    Oh I’m probably well in the billions of steps by now. Starting training a few days after the competition started. But most of that has been failed experiments. My best was probably around 500M before it plateaued if I had to guess. With a quick JAX setup samples shouldn’t be too much of a problem even on fairly poor hardware.

    - **Zotar** (2026-09-02 08:54:49.713000, votes: 0)
      does a step mean a turn of the game or a backward pass or something else?

    - **Mark Schatza** (2026-09-02 14:47:06.210000, votes: 0)
      One turn of a game.

- **** (2026-09-01 07:19:16.880000, votes: -6)

  - **Swachhith B** (2026-09-01 07:25:48.787000, votes: 0)
    Using RL?
