# How are people making RL work in Kaggriculture?

- Topic ID: 740792
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/740792
- Author: Aaweg Bhaladhare
- Posted: 2026-09-11 10:03:39.439000
- Votes: 1
- Comments: 2
- Fetched: 2026-09-12T11:44:34Z

## Post

I am convinced reinforcement learning can work in Kaggriculture. The real question is how to make it learn reliably and generalize against the leaderboard field. Some strong agents show varied, state-dependent behaviour consistent with learned policies, although replays alone cannot confirm their private implementations.

The game looks like a natural RL problem, but a straightforward formulation is surprisingly difficult. A match lasts 719 decisions, each turn can contain actions for several workers plus market orders, and an early purchase or crop decision may affect the result hundreds of steps later. Legal actions also depend heavily on position, inventory, cash, land, and previous commitments.

In my experiments, flat end-to-end PPO can learn some mechanics and occasionally beat weaker agents, but it has not yet matched a strong engineered policy consistently. More training alone has not fixed the main failures. The policy often makes individually plausible choices that do not form a coherent economy across a full match.

The approaches that currently seem most promising to me are:



Hierarchical RL: choose a persistent economic plan at a daily or phase level, then use a lower-level controller to execute it.

Recurrent policies: retain the chosen plan and a summary of opponent behaviour instead of treating every observation independently.

Autoregressive action heads: choose worker actions sequentially so later workers can condition on earlier assignments.

Imitation for mechanics, RL for strategy: initialize movement, planting, feeding, and other routine execution from demonstrations, then relax the imitation constraint while learning strategic choices.

Opponent leagues: train against several strong policies and past checkpoints instead of optimizing against one opponent or one averaged critic.

Search-generated value targets: branch from real states, evaluate a small set of legal strategic alternatives with the simulator, and train a conservative selector from those counterfactual outcomes.


The last approach has been particularly informative. It turns an extremely large raw action space into a smaller decision problem: keep the current plan or choose among a few complete, executable alternatives. It also supplies direct negative examples—actions that looked reasonable locally but reduced the terminal result.

Evaluation is another challenge. Results can change with the map, opponent and seat, so a small improvement against one opponent may disappear on a broader panel. Training curves alone also do not show whether a policy has learned a stronger strategy or merely adapted to its training opponents.

For people who have tried RL here:



Do you train one policy over every worker and market command, or separate strategy from execution?

Are recurrent policies materially better than feed-forward policies here?

What reward or return formulation gives useful credit across the full 719-step match?

Do you use self-play, a fixed opponent league, population-based training, or a mixture?

Have you found model-based rollouts, MCTS, evolutionary search, or offline RL more effective than PPO?

How do you keep exploration coherent across a match rather than adding unrelated randomness every turn?

Roughly how many simulated games did you need before seeing stable improvement?

How large does an evaluation panel need to be before you trust a result?

Is CPU simulation enough for useful progress, or has GPU training been essential?


I am not asking anyone to reveal a complete solution. Even high-level observations about what failed, what stabilized training, and how progress was evaluated would be useful.

## Comments

- **Syed Asad Ali** (2026-09-11 11:23:14.877000, votes: 2)
  I went down several of these roads without RL, so some negative results that may save you time.
  
  On 2: I can't speak for recurrent networks, but I can price the information you'd want them to carry. I run an opponent identification layer that tracks the rival's visible farm and pins their agent family by around step 12. Acting on that memory is worth about $38 a game to me, against roughly $224 if I let it cheat and read their future sells directly. The opponent summary is thin here. Plan persistence is also a non-issue: the strongest public agents hold one plan for hundreds of steps already.
  
  On 3: sequential worker conditioning is necessary. I built a scheduler that assigns each hand conditioned on the ones already placed, and it still lost heavily to a much dumber fixed script. Separately, adding workers has zero marginal value in my measurements. Coordination between workers is not the binding constraint.
  
  On 8, which I think is the most important question you asked: bigger than you expect, and the design matters more than the size. Play every seed in both seat orders and average the pair into one number before you do statistics, or you will double-count. Then hold out a seed block you never look at while tuning. I have watched the same change measure +2,301 on one "fresh" block and -1,259 on another, purely from having selected on the first. There is also a trap specific to this game. Weed spawning consumes one random draw per empty tile on both farms, so when you drop your agent into a recorded game your own play changes which shops the town unlocks. The opponent's recording is then executing a plan for a world it never saw, which flatters you badly. Split your results into the games where the shop sequence survived and the ones where it re-rolled. Against the top ten my win rate is 78% in re-rolled games and 40% in
  preserved ones. Only the second number is real.
  
  On 9: CPU is plenty. My simulator does about 670k steps a second on one core. The bottleneck is encoding observations, not the game.
  
  On your last bullet, search-generated value targets: that is the one I would bet on, and it is the only one of the six that needs no RL. The reason imitation from replays stalls is that you cannot ask the expert what to do in the states your own policy reaches, and you only have their recordings. If the simulator generates the targets, that loop closes.

- **cm391** (2026-09-11 11:26:20.007000, votes: 0)
  you should think about what you are actually modelling. expecting rl to learn optimal placement of crops and mapping workers is a lot of work… try and understand the game. you should understand the game as one-player to begin with (maximise production and money) then move on to pvp mechanics and market tricks when playing against someone else.
