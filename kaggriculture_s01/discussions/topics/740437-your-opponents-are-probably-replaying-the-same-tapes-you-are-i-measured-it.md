# Your opponents are probably replaying the same tapes you are (I measured it)

- Topic ID: 740437
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/740437
- Author: Lê Quang Cảnh
- Posted: 2026-09-09 17:03:23.748000
- Votes: 2
- Comments: 0
- Fetched: 2026-09-12T11:44:33Z

## Post

I kept running into games where the opponent farmed almost exactly like me. So I measured it, and the number is higher than I expected.

I pulled the replays of the last 26 games of my scoring submission, extracted the opponent's farm commands, and compared them against 51 tapes I had reconstructed from the public CC0 replays.

opponent matched >60% of farm turns to a known tape:  25/26  (96%)
   matched 100%:                                       1
   matched 95-97%:                                     3
mean match over 8 games sampled in detail:            87.4%


So my local bench and the real arena are drawing from the same pool. Beating a tape locally is not independent evidence that I will beat the field, because the field largely is that tape.

Here is what that does to a score over a run:

first 20 games   win 95%   opponent mean 1473    600 -> 2190
games 21-45      win 68%   opponent mean 2316   2190 -> 2380
games 46-65      win 70%   opponent mean 2378   2380 -> 2426
last 20 games    win 56%   opponent mean 2419   2426 -> 2432


Elo pairs you by rating, so by 2400 you are meeting people running the same kind of tape and winning about half. The score converges to the average of the crowd replaying tapes, not to the strength of the team the tape came from. That team sits around 2888 while my replay of it settled at 2432.

The reason I am actually posting is the three bugs this exercise found in my own tooling.

Extraction was off by one. The first step of a replay is initialisation. Before I fixed that, opponents matched my tapes at 0.1 to 0.6 percent and I nearly concluded that nobody was copying anything. The check that caught it: extract your OWN commands from your OWN replay and compare them to your own agent. That has to come out 100%. If it does not, your extraction is wrong, not the world.

My evaluation harness had a seat bug. It always put my agent in seat 0 and the opponent in seat 1, no matter which seat the tape was originally recorded in. A "98/120 = 82%" number that I had used to pick which submission to field was measured in the wrong seat.

My seat hypothesis was wrong too. The local simulator said a seat-1 tape run from seat 0 only gets 70%, against 88.9% for a native seat-0 tape, so I built a two-seat agent to fix it. Real match history says otherwise:

seat 0:  36/49  win 73%
seat 1:  24/34  win 71%


No real difference. Head to head, the two-seat agent and the old one produced identical results, 31/36 for both, matching seat by seat. I spent a while assuming that was a bug in my comparison harness. It was not.

I am curious whether other people see the same 96%. If your opponents are mostly tapes as well, then bench win rate is a much weaker signal than it looks, and the gap between local and arena is not noise, it is the same distribution measured twice.
