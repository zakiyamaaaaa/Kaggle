# I came here to build a farming agent. I ended up building a replay-measurement pipeline

- Topic ID: 739273
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/739273
- Author: sobameshi
- Posted: 2026-09-03 13:00:21.561000
- Votes: 28
- Comments: 14
- Fetched: 2026-09-12T11:44:30Z

## Post

I want to share something slightly strange about how our approach to this competition has evolved, along with some measurements of the replay meta.

This is not a rules question. #737788 established that public code and public episodes are fair game, and in #738837 the host said that using public replays to build a submission is allowed and encouraged. It is also not a criticism of teams using replay or cloning strategies. We are one of them.

What we have actually been doing

Since late August, our tracked submissions have mostly been tapes: recorded 720-turn action histories from strong public episodes, replayed verbatim on new seeds, sometimes with a small market-side adjustment.

We collect recordings from the daily top-episodes dataset and from public notebooks, reproduce them locally, run them against the other public strategies, and replace our current tape when a stronger one appears.

This works surprisingly well. In our experience, cloning a sufficiently recent strong public strategy has been enough to sit around the top 10% of the leaderboard, although the exact position moves as the meta changes.

That led us to investigate why.

What we measured

We fingerprint seats in the daily dumps and in our own games by their first 120 actions. This lets us track, approximately, which opening or strategy family is being played over time.

We then ran a round-robin of 14 public implementations spanning roughly a month of the competition, on 96 fresh seeds, both seats.

What surprised me most is that the result looks much more like a ladder than a rock-paper-scissors game:



Across the 14 implementations there is no intransitive triple.

Of the 91 chronological pairs, the newer implementation beat the older one in 86.

Adjacent generations typically won 60–80% of their games; two generations apart, 90–100%.

The ordering tracks average final money remarkably closely.


In other words, at least among the public implementations we tested, a stronger economy is simply a stronger economy, regardless of which other public strategy it faces.

The replay waves

The daily dumps show the same pattern.

Across 19 daily dumps, once an opening fell below 5% of observed seats, we never saw it become common again. A new wave peaks roughly a day after its source becomes public and fades within a few days as another, stronger economy appears.

Most of these waves originate from a very small number of sources: a few prolific notebook authors, and the public recordings of a handful of strong runtime-agent teams. In the 2026-09-02 dump, the single most common opening we detected came from one public episode of one strong team: 18 teams were playing that opening, a minority replaying all 720 turns verbatim and the rest changing the later turns.

So the picture we currently see is roughly:

runtime agents discover strong economies → their episodes become public → those economies are replayed or cloned → local testing identifies which replay is currently strongest → a new runtime economy appears → the ladder moves up one rung.

The part I find strange

I think this is the source of my discomfort.

I entered Kaggriculture because I wanted to learn how to build a strong farming agent: something that observes the town, makes plans, adapts when the world changes, and discovers better economies.

A month later, the system I have spent the most time building is not a farming agent. It is a measurement pipeline. It fingerprints public episodes, reproduces strategies locally, runs them against one another, tells us which rung of the current ladder is strongest, and helps us reproduce it quickly.

There is real engineering and experimentation in doing this well, and I have learned a lot from building the evaluation infrastructure. But it is not quite the problem I thought I was signing up to solve. And the better our measurement and cloning pipeline becomes, the less farming intelligence our submitted agent needs to contain.

Where I honestly stand

I do not think the answer is simply "replaying is bad." The data is public, the rules allow it, using public information well is part of Kaggle, and checking whether a public strategy actually generalizes to fresh seeds is a legitimate experimental problem in its own right. Watching strategies diffuse through a competitive population is also genuinely interesting. 

At the same time, I find myself much more impressed by the teams whose runtime agents are actually producing the new economies that the rest of us later measure, replay, and modify. That is also the direction I originally hoped to explore when I entered this competition. 

So  I have started asking myself a different question: am I getting better at solving the farming problem, or at measuring and making use of the information ecosystem around it? Maybe both count. 

Maybe discovering, evaluating, and rapidly adapting public strategies is an intended part of this competition. Or maybe verbatim replay is unusually strong here simply because economies transfer so well across seeds. I genuinely do not know. 

I would be especially interested to hear from people building runtime agents, from people using replay-based approaches like us, and from the hosts: is this replay ladder something you expected to emerge? And how do you think about the distinction between solving the underlying simulation and solving the meta around it? 

If there is interest, I am happy to share the fingerprinting method and the full round-robin results.

## Comments

- **Zejun_** (2026-09-03 14:47:46.467000, votes: 6)
  Not fun, the goal from "be the best" turn to "be better a little than most public notebook". Only very few participants still make new things.

  - **sobameshi** (2026-09-03 14:55:58.537000, votes: 0)
    I can relate to that.
    I don't think public sharing is bad in itself, but once the main path becomes "take the strongest public replay and improve it a little," it does feel like there's less incentive to try genuinely different ideas. Hopefully we eventually reach a point where runtime agents and new approaches matter more again.

- **Yusuke Hayashi** (2026-09-03 14:06:33.417000, votes: 2)
  I strongly relate to this. I’ve also built and shared a replay-based agent, but it feels quite different from what I expected to be doing when I entered this competition. Still, part of me hopes the field climbs this ladder faster and gets closer to its ceiling—so that replay-based approaches yield diminishing returns, while genuine runtime agents become relatively more valuable.

  - **sobameshi** (2026-09-03 14:22:30.387000, votes: 0)
    That's a framing I hadn't considered — replay strategies eventually running into diminishing
    returns as the ceiling gets closer, rather than the ladder just climbing indefinitely. That's a
    genuinely useful way to look at it, thanks.
    
    And I'd like that too, if it's at all possible: for the second half of this competition to turn
    into more of a real runtime-agent contest.

- **Michael Timbs** (2026-09-08 23:26:45.993000, votes: 0)
  I've been doing the same. I also noticed when i did spend a bunch of time finding novel play the entire field copied me within 24 hours so i didnt submit again for over a week. 
  
  Interestingly, for the first time since the competition started we have someone (SpaTaro) in the top 10 who is not taking this approach though and every single one of their matchups has played a unique strategy which means they are doing more than a static policy book.

- **Justin Gao** (2026-09-08 02:39:13.437000, votes: 0)
  I tried to build a three-tier real-time decision system consisting of planner, scheduler, and worker, responsible respectively for macro-level situation monitoring, micro-level fixed-task management, and actual execution. However, even with this approach, I still couldn't achieve the efficiency of a tape-based strategy. Improving efficiency in my micro-task management has been slow and frustrating—and that is the paradox of this game.

  - **sobameshi** (2026-09-08 03:06:47.867000, votes: 0)
    That sounds very similar to what I’ve been seeing with my own runtime line. Even if you separate the system into layers, meaningful improvements often require changes that cut across several of them at once. Once that happens, it becomes much harder to isolate causes cleanly, so the iteration cycle slows down a lot.
    
    At the same time, I still have the feeling that runtime agents may overtake tape-based approaches once they cross some threshold. What’s interesting is that the newer public non-runtime solutions already seem to be moving in that direction: they are no longer just “better tapes,” but tape + mechanism, with routers or state-dependent logic deciding which trajectory to follow.
    
    So I’m still optimistic that runtime will win eventually—the hard part is getting through the stage where every useful improvement becomes a multi-layer coordination problem.

- **Chris Is Kaggling** (2026-09-05 06:43:27.737000, votes: 0)
  ​I initially built a tape model simply because I joined this competition a bit late and wanted to study how others were playing, see the differences between strong models and ordinary ones, and analyze, dissect, and ponder the difference between the "essence of this competition" and the "essence of winning a top 10 spot."
  
  ​To my surprise, as everyone has shared, the proportion of runtime agents is very low and widely distributed, while meta tapes are updated heavily every day. I myself felt pretty good for a while after submitting a few tapes that got me into the top 10% on the leaderboard, but when I repeatedly thought about the final scoring system and the leaderboard ratings, I realized that trying to win in the end relying on tapes depends more on early-game winning streak luck combined with late-game rock-paper-scissors luck among same-generation tapes. However, whether it's the essence of the competition or the essence of winning, it ultimately points to runtime agents being the most stable solution under this game mode, so I also plan to try building my own agent in the time remaining, and I no longer intend to chase a good-looking leaderboard ranking.
  
  ​Though I still feel that by the end game, we'll probably see runtime agents coexisting with their tapes, haha

- **Prema Ananda** (2026-09-04 10:11:44.260000, votes: 0)
  Special thanks to everyone building replay-based bots — they're great benchmarks to calibrate a dynamic agent against.
  
  Sure, my agent's rating is nothing to write home about right now, since it computes everything in real time. But working on it is way more fun than dealing with scripted moves — those eventually hit a ceiling. So I'm betting on real-time economy and dispatch logic — feels like the more promising path to me.

  - **sobameshi** (2026-09-04 10:31:01.030000, votes: 1)
    I'm also starting to work on a runtime agent myself — honestly, seeing the reactions and discussion here gave me the push to finally start. I'm definitely getting a late start compared with some of you, but I'm going to give it a serious try. Good luck with yours too!

- **Andrew Reed** (2026-09-03 18:10:23.810000, votes: 0)
  Your experience is eerily similar to mine. Why do you think tape-replay is so effective? Is there just not enough opportunity to interact with (i.e., undermine) your opponent in this game? Are matches not sufficiently long enough (or random enough) for a dynamic agent to succeed consistently against tapes?

  - **sobameshi** (2026-09-03 19:47:56.473000, votes: 1)
    Good questions. My current guess, based on what we've measured, is that the interaction surface between two agents is simply smaller than it looks. Most of the farm plan is fairly self-contained, so a stronger economic plan often stays stronger regardless of the opponent, with the shared market being the main place where direct interference really happens.
    
    That said, I don't think dynamic play is weak. We've had several cases where adding a small reactive layer specifically for tape-like or near-mirror opponents made those matchups noticeably easier to win.
    
    So my current picture is: strong underlying economy first, then a relatively thin adaptive layer for the parts of the game where the opponent actually matters. That reactive layer alone has never been enough to get us into the top 100, though, so I suspect there still needs to be something fundamentally better in the underlying plan as well.

- **cygn** (2026-09-03 13:14:17.550000, votes: 0)
  You've hit the nail on the head. I've also been in the top 10 with some tape replay approach and if you looked at what others were doing it seems like 85% of people do it like this. 
  It's not particular interesting to me and I don't enjoy this competition atm for this reason.

  - **sobameshi** (2026-09-03 13:41:25.247000, votes: 0)
    Hi cygn, thanks for the reply!
    
    On the "not interesting" part, I feel exactly the same way, and it means something to hear that from someone that much higher up the ladder.
    
    Lately, I've mostly given up trying to solve that part and settled for at least being honest with myself about what I'm actually doing — which is really what most of the post above was about.
    
    One thing I do want to try, once our tape-making pipeline is stable enough that it no longer needs daily attention, is to build an actual runtime agent from scratch and put it in our other submission slot, just to see how far it can get on its own.
