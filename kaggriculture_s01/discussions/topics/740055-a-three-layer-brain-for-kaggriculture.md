# A Three-Layer Brain for Kaggriculture

- Topic ID: 740055
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/740055
- Author: Justin Gao
- Posted: 2026-09-08 03:01:11.941000
- Votes: 3
- Comments: 0
- Fetched: 2026-09-12T11:44:32Z

## Post

Although the leaderboard is now flooded with various pre-programmed tape-based strategies—where all planning is finalized at the very beginning, and every crop, animal, and employee in each turn operates like finely meshed gears, squeezing out every last bit of efficiency—I still feel that this might deviate from the original intent of the game. An "agent," after all, should at least have an agent loop to play the game, shouldn't it?

Now please allow me to share my design architecture.

A Three-Layer Brain for a 1v1 Farming Race

Kaggriculture: a 1v1 farming simulation. 30 days × 24 steps = 720 steps. You win if you have more cash than your opponent at the end.

Building the agent, the interesting tension was this: the game is nearly deterministic, but the execution layer is not trivial. Every unit — a crop or an animal — needs a sequence of visits across different days (seed, water daily, harvest at the right day, replant; or buy, place, feed, care, collect). If the executor re-decides "what's nearest" every step, it spends most of its time walking and keeps interrupting multi-day tasks.

So we split the agent into three clean layers.

+------------------------------------------------------------------+
|  Layer 1 — Strategy                                                |
|  WHAT to produce, WHEN to sell, how many hands, when to buy land.  |
|  portfolio(day) -> {crops:{...}, animals:{...}}; sell_policy;      |
|  num_hands_for_day(day); land_days. Objective = relative cash.     |
+------------------------------------------------------------------+
                │ emits commands only
                ▼
+------------------------------------------------------------------+
|  Layer 2 — Execution state machine (cerebellum)                    |
|  Turn the portfolio into per-unit lifecycles and run them.         |
|  Two orthogonal dimensions:                                        |
|    • ProductionUnit — a view over one board tile; reports needs.   |
|    • Worker         — one farmer + hired hands; holds a persistent |
|                       queue of coarse tasks.                       |
|  Real engine state is the ONLY source of truth.                    |
+------------------------------------------------------------------+
                │ sits on a deterministic substrate
                ▼
+------------------------------------------------------------------+
|  Layer 3 — Deterministic production schedule                        |
|  Given planted_day and our watering/feeding choices, every harvest  |
|  day is computable. Crop/animal milestones are derivable, not       |
|  stochastic.                                                       |
+------------------------------------------------------------------+




Layer 1 — Strategy

This layer decides the plan, not the movements. It produces, once per day:



portfolio(day) — crop and animal targets,

sell_policy — per-product sell timing,

num_hands_for_day(day) — how many workers to employ,

land_days — when to buy land.


Its objective is relative cash: since winning is about having more than the opponent, it reasons about my cash minus the opponent's cash, not my raw cash. It says nothing about where to place or which tile to water — that belongs to Layer 2.

Layer 2 — Execution state machine

Layer 2 takes the portfolio and runs the full lifecycle of every production unit. It has two orthogonal dimensions.

ProductionUnit — one object per board tile. It holds no private state about the goal; each step it reads the real tile and derives what that unit wants right now:

class ProductionUnit:
    def needs(self, tiles, day, plant_plan, portfolio):
        tile = tiles[self.y][self.x]
        # plant unwatered -> WATER; plant mature -> HARVEST
        # animal unfed -> FEED; animal with product -> HARVEST; ...


Worker — the farmer plus hired hands. Each holds a persistent queue of coarse tasks, which survives across steps and across the day boundary:

class Worker:
    tasks: list[Task]       # persistent queue
    current: Task | None
    def tick(farm, private, day, survival=None): ...   # advance current one step


Task — a coarse, multi-step object bound to a single unit. It advances itself across steps (for example PICKUP cow → walk → PLACE). While a worker is on a task it is not pulled away to do something else. One worker serves many units; tasks are inserted continuously.

Two properties are load-bearing here:




Engine state is the only source of truth. The cerebellum keeps no private copy of its goal; it reads the current tile every step (planted_day, watered_today, yield_units, consecutive_unwatered, fed_today are all on the tile). The only persistent state it keeps is the worker's task queue — because a multi-step action must survive without interruption.


Coarse multi-step tasks are not interrupted. This is what makes multi-stage work (place an animal, feed it, harvest from it) actually complete instead of being abandoned midway.


Layer 3 — Deterministic production schedule

Layer 2 is able to reason ahead because Layer 3 makes the timing computable. The engine's production rules are deterministic: given when a unit was planted/placed and the choices we make about watering/feeding, the days it produces are fixed.

def crop_milestones(crop, planted_day):
    cd = CROPS[crop]
    harvest_d = planted_day + cd["first_yield_day"]
    # water every day until harvest; harvest at first_yield; replant after

crop_milestones("WHEAT", 0)        # [(0,WATER),(1,WATER),(2,HARVEST)]
crop_milestones("MELON", 0)        # water day0..9, harvest day10
crop_next_op("STRAWBERRY", 5, 15)  # ongoing crop: harvest every interval days


Because the schedule is known, the cerebellum can move from per-step greedy selection to schedule-driven lookahead routing: precompute each unit's milestones, order the workload into a spatially coherent route, and hand each worker a short consecutive segment of it. That lets the executor be both efficient (fewer wasted steps walking) and complete (nothing is left waiting, because the route covers the scheduled work).



How the layers fit



Layer 1 decides what and when, and produces a portfolio + timing plan. It never picks a tile or a movement.

Layer 2 turns that plan into actual unit lifecycles and executes them as a state machine over real engine state, using persistent coarse tasks.

Layer 3 makes the production timing deterministic, so Layer 2 can route workers ahead of time instead of reacting greedily.


The whole design rests on one idea: separate what's strategic from what's reflexive, and let the reflex exploit the fact that the environment's production is fully computable.
