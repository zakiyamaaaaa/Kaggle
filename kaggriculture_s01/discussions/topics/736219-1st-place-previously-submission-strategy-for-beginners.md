# 1st Place(previously)- Submission Strategy for beginners

- Topic ID: 736219
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/736219
- Author: Ryo Hasegawa
- Posted: 2026-08-19 22:38:49.801000
- Votes: 83
- Comments: 10
- Fetched: 2026-09-12T11:44:29Z

## Post

Disclaimer: This post includes assumptions based on my experience. The best way is always to experiment for yourself!

How the rating actually moves, how to read your score, and how many times you should (not) submit.

I spent some time studying the rating curves of my own submissions and built a small Elo-style simulator to understand them. Most of what follows is structured as "mechanics → consequence → what to do," so you can skip the mechanics if you only want the checklist at the end. The numbers come from fits to my own submissions and from the simulator; treat them as rules of thumb, not facts about Kaggle's internal system.

TL;DR



A new submission starts at 600 and is ~90% converged after ~60 games, usually within the first ~5 hours. New submissions initially play ~15 games/hour, then slow to ~1–2/hour.

After that, the score grows only logarithmically—roughly +50–70 per 100 games, or per 3–4 days—and residual noise remains around ±25–50 points. Differences of only a few dozen points are more likely luck than skill.

The live leaderboard is not the final ranking. Per the Evaluation page, after the deadline games keep running for ~two weeks and a Bradley-Terry tournament on those episodes produces the final leaderboard. Your live rating's history, its lucky start, and its "age" count for nothing at the end—only how your last 2 submissions actually fare against the field.

Only your 2 most recent submissions are active, and each new submission starts again at 600. Re-submitting an unchanged bot to "re-roll" its trajectory only moves the live number (and costs you the older copy); it changes nothing about the final ranking. Submit only genuine improvements.

The score counts wins and losses only and matches you against opponents near your current rating. Optimize win rate against the bots around you, not average coin totals. Evaluate offline over enough games.


1. What the score is



The system appears to be Elo-like: after each game, your rating moves by K·(result − expected result). Only W/L matters, not the coin margin. Opponents are selected near your current rating, so your score depends on how often you beat the bots around you—not on how decisively you beat weaker ones.

The update factor K is large at first and shrinks as the number of games, n, increases: roughly K ≈ 200·e^(−n/26), plus a small floor. Consequence: the first few dozen games determine the overall level; everything afterward is mostly slow drift.


2. How it moves (measured)

Based on fits to my submissions, the median curve is close to μ(n) ≈ a + b·ln(n). Here, b depends mainly on your win rate (~50–190 in my fits), while a reflects the luck of your first ~40 opponents (approximately ±130 in my fits; others in this thread report byte-identical copies ending 300–1400 apart, so the early path dependence can be much larger than my two submissions suggest). Simulated trajectories for a bot with a fixed underlying strength look like this:




games n
share of its 400-game rating
trajectory spread (≈ ±1 SD)
time since submission




20
~60%
±160
~1.5 h


40
~80%
±140
~3 h


60
~87%
±105
~4–5 h (end of the burst)


96
~92%
±80
~1 day


150
~95%
±65
~2–3 days


200
~97%
±50
~4 days


300
~99%
±35
~1 week




(The wall-clock estimates are based on two of my submissions: a burst of ~15 games/hour for the first 4–5 hours, followed by ~1–2 games/hour. Your results may differ.)

3. So—how should you read your score?



Don't judge a submission before ~60 games (≈ 5 hours). At 20–40 games, it can sit 100–200 points below where it will eventually settle purely because of the opponent draw.

Compare two of your submissions at the same game count. Never compare a new submission at 50 games with an old one at 300. The older submission may have a 100–150-point advantage purely from age.

Treat differences under ~50 points as noise, even after 200 games. If you "fix" something because your rating fell by 30 points in a day, you are fitting noise.

The same logic applies to the leaderboard: the top ~15 submissions are within one or two SDs of one another. Their order can change daily even when nobody changes their code—and the final ranking will be recomputed from scratch anyway (see below).


4. So—how often should you submit?



Only the 2 most recent submissions are active (up to 5 submissions per day). Submitting a third retires the oldest, and the new submission starts from 600. Those same 2 are what enter the final evaluation.

Re-submitting the same bot for a more favorable draw—a "re-roll"—is worth, in expectation, about +40 live points if judged at 96 games, +25 at 200 games, and +10–15 once both copies have converged, while a freshly submitted copy has less than a 5% chance of overtaking an already-converged copy before ~150 games. And none of that survives the final Bradley-Terry pass. A re-roll costs you a converged trajectory and buys you a nicer number to look at for a while.

Therefore, keep your best bot in one slot and let it age—for your own information, not for the final ranking. Use the second slot only for a version you genuinely believe is stronger, or for a deliberately different version that hedges against a shifting meta—not for copies or tiny parameter changes.

Timing matters less than you think, but not zero: the final tournament is computed from the ~two weeks of games played after the deadline, so what you need on deadline day is simply your two strongest, error-free submissions in the two slots. Don't push untested code at the last minute (an erroring agent plays nothing), and do leave yourself a day to confirm the final pair runs cleanly on the ladder.


5. So—what should you optimize offline?



Optimize win probability against the bots near your target rating, not mean coin totals. A bot that wins 70% of its games by small margins outrates one that wins 60% by huge margins. Most "improvements" that raise your average coin total but increase variance are rating-negative—and Bradley-Terry is, again, fitted on wins and losses only.

Local evaluation has the same noise problem as the ladder: a win rate calculated from 5 games means nothing. Compare variants using the same seeds.

Judge a change by its win rate against each strong opponent, not by the pooled mean. A change that adds +3k coins on average but turns two wins into losses against the #2 bot is a loss on the ladder.

The opponents that matter are the ones that will be on the ladder during the two post-deadline weeks. The population drifts (older engine-version agents drop out, new copies of strong notebooks arrive), so re-check your agent against the current meta every week or so rather than tuning once and freezing.


6. Checklist ("because → do")



Because ~90% of the level is established in the first ~60 games → wait ~6 hours before judging; judge at 100+ games.

Because the curve follows a + b·ln(n), with roughly ±50 points of residual noise → treat moves under 50 points as noise; compare submissions at equal n.

Because only the 2 most recent submissions are active, every new submission starts at 600, and the live number does not enter the final ranking → never re-submit an unchanged bot; use the second slot for a genuine improvement or a hedge.

Because the score (and the final Bradley-Terry fit) counts only W/L against the nearby pool → optimize win rate against strong opponents, using the same seeds.

Because the final leaderboard is a Bradley-Terry tournament on the ~2 weeks of games after the deadline → your final two slots should hold your two strongest, error-free agents; the rest of the live history is irrelevant.


Kaggle's actual rating-update schedule and matchmaking may differ, and the final Bradley-Terry details are only as described on the Evaluation page. If you have trajectories that disagree with the table above, I would genuinely like to see them.

## Comments

- **shanzhong8** (2026-08-23 09:11:05.653000, votes: 3)
  nice sharing ，may I ask if you are using rl or rule base currently？

- **SaiKushal185** (2026-08-20 09:16:58.090000, votes: 2)
  Thanks for breaking down how elo works bro

- **Ryo Hasegawa** (2026-08-19 22:59:28.203000, votes: 0)
  Any feedback is appreciated🙏

  - **Syed Asad Ali** (2026-08-20 03:48:19.963000, votes: 1)
    Hi Ryo,
    
    Thank you so much for writing this for the benefit of community overall. Really appreciate your insights. The convergence table matches what we've measured almost exactly. Two of our fresh submissions were at ~98% of their current rating by game 60 and the burst rate was 16–17 games/hour for the first 4 hours.  I have some questions that I'd love your take on, with my own numbers as trade:
    
    K-decay shape. From (updated − initial)/(actual − expected) on our own episodes, K doesn't decay smoothly: it sits flat at ~220 for the first ~10 games, then cliffs to ~45–55 by game 20, and floors at ~8.5 by game 80. Your 200·e^(−n/26) is gentler in the middle. Did your fits actually prefer the smooth exponential, or would a plateau-then-cliff fit your data too? It matters for how much the first 10 games dominate.
    
    Ties in the final Bradley-Terry. With so many byte-identical family agents on the ladder, forced draws are common. Do you know (or assume) whether the post-deadline BT fit treats ties as half-wins, discards them, or something else? For agents that mirror a big family this changes the optimization target.
    
    Seat asymmetry. destbreso's notebooks mention a measured seat-0 win-rate edge. Does your Elo simulator model it, and how large do you estimate it? We're deciding whether to weight our paired evaluations for it.
    
    The hedge slot. When you say the second slot should be "a deliberately different version" - in practice, how different? A different route family entirely, or a different adaptation layer on the same chassis? Curious how you trade off hedging vs. fielding your two strongest.
    
    Offline sparring pool. You suggest re-checking against the current meta weekly. What do you use as the offline opponent set - reconstructions from ladder replays, public notebook agents, or your own older versions? Reconstructions of adaptive agents are frozen and can mislead, so I'm curious how you handle that.
    
    Hope the answers help others climbing the same curve. Thanks again!

- **Braxton Dyer** (2026-08-29 23:26:08.390000, votes: 0)
  thank you. I'm just getting into kaggle comps so this really helps. I am a lowly newb

- **Tien N.** (2026-08-24 02:56:25.040000, votes: 0)
  I must add - you should not re-submit unchanged bot UNLESS it started out badly. It's really up to you to define how many consecutive wins is a good start, but the first loss really largely affects where your final score range ends up in.

- **Heisenberg** (2026-08-20 08:02:15.010000, votes: 0)
  Thank you for this great analysis. Do you think that actually publishing your own strong agent is a good idea? Since the game is relatively symmetric, distilling a strategy from replays seems to be quite simple. Since you are currently the best-performing player, your perspective would be really interesting.

  - **** (2026-08-21 03:18:57.370000, votes: 0)

- **** (2026-08-30 06:35:10.960000, votes: 0)

- **hengck23** (2026-08-24 03:05:08.793000, votes: 0)
  thank you very much for your post!
