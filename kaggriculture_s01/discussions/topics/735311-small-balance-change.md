# Small balance change

- Topic ID: 735311
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/735311
- Author: Bovard Doerschuk-Tiberi
- Posted: 2026-08-15 00:30:11.721000
- Votes: 25
- Comments: 7
- Fetched: 2026-09-12T11:44:28Z

## Post

I'm adding a small change to eggs, tomatoes and carrots, such that their price will increase significantly if there is a large shop demand and no production.

Since the shop demand is randomized, each of these products will start to see the levels of prices increases (assuming NO production):



tomatoes => 50% of games

carrot => 26% of games

eggs => 22% of games 


The intent of these changes it to roughly preserve the existing market dynamcs, but make these products viable in some situations, not universally. This should lead to more interesting end game decisions.

Details here: https://github.com/Kaggle/kaggle-environments/pull/1399

This should be the last change, excepting game breaking bugs.

This should roll out shortly. You should update to >=1.32.7

Happy Kaggling!

## Comments

- **Georgy Mamarin** (2026-08-25 04:30:04.477000, votes: 0)
  A population-level follow-up to destbreso's measurement, from the other end: what the ladder actually did with the change. I split 37,343 public episodes - 74,686 seat-games, two agent seats per episode - by each replay's module_version (the engine_version column of the dataset), windows split by version, not by date. Short version: the field repriced carrots within a day, nobody picked up tomato, and the new scarcity payouts are not showing in banks yet.
  
  The rollout itself, measured: the PR went public Aug 14 at 02:38 UTC, and on Aug 15 the merge, the PyPI upload and the ladder cutover all happened inside 17 minutes (01:24, 01:35, 01:38-01:41 UTC - last 1.32.6 game, first 1.32.7 game, nothing in between).
  
  Realized price ceilings (per-episode price_<good>_max):
  
  
  
  carrot: never exceeded 43 in any of 50,220 pre-patch seat-games (median per-game max 42); post-patch median 57, p90 116, p99 360 - 82% of games clear the old all-time ceiling.
  
  tomato: p99 128 -> 786; seat-games above the old p99 went 0.8% -> 29.8%.
  
  egg: p99 84 -> 167; 0.8% -> 9.4% - weakest of the three, matching destbreso's read.
  
  melon is the clean control: identical at every checked quantile (272/272/272 at median/p90/p99, max 274) in both windows. Wheat's tail actually shrank (p99 56 -> 53) - consistent with the meta shift below, not with any global price drift.
  
  
  What the field did: carrot planting went from 6.3% to 44.2% of seat-games. The paired evidence says resubmission, not adaptation: of 332 submissions with at least 3 games in each window, zero flipped whether they plant carrots or tomatoes (frozen code stays frozen); among submissions that debuted after the cutover, 60% plant carrots versus 12% for pre-window debutants. The switch started before the switch: carrot share was already a quarter of seats on Aug 14, the day the PR went public (with a smaller rise on Aug 12-13 I cannot attribute). Tomato, whose realized ceiling moved the most in absolute terms (max 1,803), was not adopted: 0.7% -> 1.0%.
  
  Banks are the honest null. The across-all-teams median moved +4.6%, but the pre-window generates the same drift internally (+3,939 from Aug 8-10 to Aug 12-14), and for the 723 teams with at least 5 games in both windows the per-team delta collapses to +610 coins (373 up, 350 down - a coin flip; p=0.41). Tails opened less than the median: bank p90 +2.2%, p99 +2.0%, and the single-game maximum actually fell. Either the spike money is not being captured yet, or it is competed away as fast as it appears; bank data cannot tell these apart. One outcome did move: the median winner-loser bank gap narrowed from 6,810 to 4,454 coins (533 of 723 paired teams narrowed, p~1e-38) while the matchmaking rating gap stayed flat (daily medians 36-45 in both windows) - either the carrot floor compressing outcomes, or the meta converging on the same carrot line; I cannot fully separate the two.
  
  Everything above splits on the engine_version column in kaggriculture-episodes, one line of pandas to slice differently.

- **Forrest** (2026-08-15 08:03:50.033000, votes: 3)
  Maybe you should update README.MD

  - **Bovard Doerschuk-Tiberi** (2026-08-15 17:42:09.283000, votes: 2)
    README and "How to play" page updated

- **destbreso** (2026-08-17 14:46:12.243000, votes: 1)
  I reproduced the firing rates independently, and they land where you said. Reading market["inventory"] every turn across 120 recorded episodes replayed with both seats playing their own recorded actions, so no agent of mine in the loop, games cross the new knee for tomato 55.0 %, carrot 28.3 % and egg 25.8 % of the time, against your 50 / 26 / 22. Melon is a useful control: untouched by the change, in no shop menu, and its deepest scarcity across those episodes is 11 units against a knee of 300, so it crosses 0 of 120.
  
  The stated intent also checks out, and I think this is the more interesting half. Median scarcity sits just below each new knee, 219 against 200 for tomato, 316 against 450 for carrot, 228 against 332 for egg. So the median game is almost exactly the old game: dumping 100 units at median scarcity pays 1.00x the old revenue for tomato and egg to the dollar. At p90 it is about 2x, and the large multiples only appear in the deepest game of the 120. "Viable in some situations, not universally" is what the numbers do.
  
  Two notes that might be worth a line in the PR description. Carrot's below_target also moved, 0.20 to 1.00, which the post does not mention and which lifts its curve below the knee as well as past it. And on my measurements egg does not reach the money at any percentile short of the deepest game, 1.00x at the median and at p75 and 1.06x at p90, so of the three it is the one where the change may not do what the firing rate suggests.
  
  Also worth saying for anyone worried about their existing work: recorded episodes have both sides fixed and replay identically on either build, 40 of 40 banks to the dollar in my checks. Holding agent, seed and opponent fixed and switching only the build moved 118 of 224 banks and changed 0 of 224 winners.
  
  The same shape shows up in the closed-form ceiling on total money in an episode, which is a sum over market_price and so re-derives itself on any build: on 1.32.7 it moves 0.2 % at median demand and 9.7 % at the most generous shop draw in 120 seeds, with no episode of 32,570 above either. Median untouched, tail opened, again.
  
  One consequence for anyone tuning against a target rather than against wins: a change that adds nothing to the median and a lot to the tail is a dispersion change, and dispersion and expectation point different ways depending on whether you are ahead or behind. The argument for why the objective here is Pr[win] = Φ(μ/σ) rather than expected margin is in Wins, not money. Happy to publish the reachability measurement itself if it would be useful.

- **Raymang0** (2026-08-16 08:31:37.590000, votes: 1)
  I like that the rules have changed over time, it has made the game more balanced for sure. But it would be interesting if there were a reward for top players for a given rule set, so compute isn’t seen as wasted

- **alex chilton** (2026-08-15 08:10:22.140000, votes: -7)
  r u havin a laugh - people use compute to tune a lot then you just pull the rug on it…? a little thought might be in order - thats the third long run changed…

- **VynoDePal** (2026-08-15 21:54:31.070000, votes: -1)
  Good update. But please, Make it possible to buy them in town. At least one.
