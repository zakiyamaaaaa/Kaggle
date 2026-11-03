# My Journey So Far — Mechanics, Breakdowns, and What's Actually Working

- Topic ID: 740847
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/740847
- Author: Siva Kumar
- Posted: 2026-09-11 16:49:48.136000
- Votes: 1
- Comments: 0
- Fetched: 2026-09-12T11:44:35Z

## Post

Hey all, wanted to share my progress and the hard lessons I've picked up since day one. This turned out to be the deepest comp I've touched and I figure writing it out helps both me and anyone else grinding through it.

Where I started vs. where I am

Early submissions sat in the 500-600 rating range, which is basically "agent is alive but losing money." Current best is ~1399 (v80+sheep). The delta wasn't from clever ML - it came from understanding what the engine actually does vs. what the README claims.

What I got wrong early




Treated this like a tabular comp. There is no train.csv. The only way to know if something works is to submit or run it against the real kaggle_environments.make() engine. Cost me a week.


Trusted the README over the source code. The README claims town demand "escalates 2x after day 10, 4x after day 20." That logic does not exist in the shipped engine (kaggle_environments 1.32.6+). Flat shop consumption only.


Local win-rate is anti-correlated with the LB in market-driven sims. My best local performer was literally my worst LB result. The signal I trust now: real LB replays, not my own bench pool.


What actually moved the needle




Replay fingerprinting: pulling 20-60 real opponent replays and diffing their per-product sell volumes vs. mine. Found I was dumping 1,300+ wheat/game while top opponents sold ~400 wheat + ~180 strawberry.


Yield-aware FERTILIZE: the FERTILIZE op doubles tile yield, but only if you apply it 2 or fewer days before a production event. Gating on whether a yield falls in day..day+2 fixed it (0 to 54 fertilize actions).


CARE gating: pending_care_bonus only banks when the animal is also fed the same day. Caring an unfed animal is a wasted action. Fixing that: +25% milk, +51% wool.


Day-28 liquidation: reward is your coin balance at step 720 - shed stock scores zero. Bypassing sell reserves from day 28 onward recovered ~$2.8k/game.


Route commitment for feeding: PICKUP was 1,100+/game vs. the meta agent's 135. Adding a commitment contract (hand locked to one animal until delivered) cut animal deaths from ~10/game to ~1.


The hurdles I'm still fighting




Ladder path-dependency: a submission plays ~35-40 episodes in the first 24h then slows to hourly, so a score is provisional for 2-3 days. You can't re-plan off one reading.


The meta agent is a shared public notebook. A large fraction of the field runs byte-identical code (8 COW + 4 SHEEP, 62 plants, 14 hands, 264 hires, 0 deaths). The ceiling past ~1400 requires actually beating that fingerprint consistently.


Import errors on submit: any file reference in agent code crashes silently on Kaggle's evaluator. Cost me ~1800 rating points across two subs before I found it.


TL;DR for anyone early in this comp



Read the engine source (kaggle_environments/envs/kaggriculture/kaggriculture.py), not the README.

Pull your own LB replays and compare action counts vs. top opponents - that's the only honest signal.

Fix mechanical bugs before optimising strategy - they compound in non-obvious ways.

Expect 1-2 days for a score to stabilise; don't submit again until the current one has 30+ episodes.


Good luck everyone - 19 days left and still a lot of room.
