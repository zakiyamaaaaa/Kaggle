# Balance Changes

- Topic ID: 733431
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/733431
- Author: Bovard Doerschuk-Tiberi
- Posted: 2026-08-06 21:12:41.912000
- Votes: 40
- Comments: 13
- Fetched: 2026-09-12T11:44:27Z

## Post

First I want to thank all of you for participating - it's been a lot of fun to see the strategies and leaderboard develop so quickly! 

From the data we are getting so far there are a couple small changes which will help create more compelling gameplay:



we're reducing the overall demand for products from the town

shops will now be sampled WITH replacement (so you can have 2x Donut Shops and 0 Yarn Shops)


Details

The Town Center used to buy products 2x/day and have a 2x/4x multiple later into the game, this change will make it only buy products 1x/day and never increase from purchasing 1 of each product. The large demand from the TC meant that markets were too resistant to sell pressure later in the game. The products purchased by the TC remain unchanged.

Since shops are now sampled with replacement, each game will be very different (for example in rare cases 4x or more of a single shop type can be spawned). Shops will continue to buy on the same schedule and demand as previously. The shop spawning schedule is also unchanged.

See details here: https://github.com/Kaggle/kaggle-environments/pull/1394

This change is now rolling out and should be hitting the leaderboard shortly, make sure to upgrade to >= 1.32.6

## Comments

- **Malcolm Durosaye** (2026-08-06 21:59:08.430000, votes: 9)
  Hi @bovard: Thanks for sharing the update! When will these balance changes take effect?

  - **venks** (2026-08-07 15:10:46.423000, votes: 0)
    Hey, same question. Will this change be implemented today? Seems pretty major for a mid-competition change

    - **Jack** (2026-08-07 15:29:51.680000, votes: 3)
      It's been a week, wym mid-competition 😆

    - **venks** (2026-08-07 15:34:19.737000, votes: 0)
      Nah you're right 😂 just got things working yesterday then found this post so I have to port everything into the new engine

- **Abdullah Razi** (2026-08-09 09:20:54.257000, votes: 1)
  are the docs upto date with these changes? I still see the multiplier in the docs or am i messing it up somewhere. If not it would be cool if it gets updated so new contestants and the old ones know what they are dealing with now. 😀

  - **Domino Weir** (2026-08-10 14:06:18.223000, votes: 0)
    Which docs source are you looking at? I believe I updated the README, the dataset, and the competition overview page- but always possible I missed something!

    - **Abdullah Razi** (2026-08-10 14:10:46.327000, votes: 0)
      its updated now 😀

- **Domino Weir** (2026-08-07 17:21:25.597000, votes: 2)
  Just to signal boost: these changes are rolling out and hitting the leaderboard! Please be sure to upgrade to >= 1.32.6

- **Vaibhav** (2026-08-13 07:53:12.590000, votes: 0)
  Hi @bovard when will these changes be reflected in the leaderboard? The previous sdk solutions will they be regraded or stay up with the same score. Having updated public score helps.
  Also I would recommend doing the a full run similar to final evaluation every 2 weeks during the competition as well, just to remove drifts

- **Ragheb haddara** (2026-08-10 21:45:34.507000, votes: 0)
  Balance changes mid-competition are always tricky. The key is to have an adaptive strategy rather than hardcoding specific crop choices. Wheat and carrots are fast turnover (2-4 days to harvest), while tomatoes give ongoing yield. Having a mix of both short-term and long-term crops helps adapt to balance changes. Also, fertilizer is often undervalued — it can significantly boost yield per tile.

- **chupaletas** (2026-08-08 05:03:54.013000, votes: 0)
  more eggs now? :)

- **Axel Ahmer** (2026-08-07 04:14:36.473000, votes: 0)
  I believe there is a 1 second time limit per agent step - i was curious if it's being considered to modify this? Currently, live routing / planning systems are extremely difficult to get working with such time constraints - even grounding a logic program would take at least 1 second. I'd be in favour of a game clock solution as opposed to a turn clock - i.e. 720 seconds for the whole game, as opposed to 1s per turn. But more time in general would favour more sophisticated strategies in general that involve deeper reactive planning. As it stands, it seems like 1s just promotes "smart" precomputed lookup table policies. Even forcing things through a pre-baked NN i could imagine taking longer than a second… Anyone else running into such issues?
  
  This all said, I'm not 100% sure there even is a 1 second time limit. Would appreciate anyone that could shed light.

  - **robga** (2026-08-07 07:25:28.073000, votes: 1)
    Re "I'm not 100% sure there even is a 1 second time limit. Would appreciate anyone that could shed light.". If you ask your agent the same question while referring it to the source code for kaggle-environments it will provide an answer:
    
    "These values are defined by the Kaggriculture specification, with the 60-second initial bank in its observation schema. The framework’s action wrapper performs the timeout check, and core deducts only the excess over one second."
    
    I've not entered this competition yet, but generally an idea is a) encode any match-long look up precomputed data as part of submission.zip, b) "use up" any remaining of the 1 second per turn + overage/steps with other future search, c) invest effort in measuring and optimising search efficiency.
