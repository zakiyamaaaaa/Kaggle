# Crucial Information for Starters and Organizers: Documentation vs. Engine Discrepancies

- Topic ID: 732450
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/732450
- Author: SIDHAARTH SHREE
- Posted: 2026-08-03 03:59:05.608000
- Votes: 27
- Comments: 6
- Fetched: 2026-09-12T11:44:26Z

## Post

If you are building strategies based strictly on the documentation, please note that the underlying game engine executes several mechanics differently. Where the docs and the engine disagree, the engine wins, adjust your agent's logic accordingly:

Game Mechanics & Yield Discrepancies




Animal Care Bonus: The Rulebook states that feeding and caring for an animal increments pending_care_bonus by 2. In the engine, the payout increments by only +1 per day.


Fertilizer Selling: The Getting Started guide explicitly notes that fertilizer can only be bought, not sold. In practice, the market logic accepts SELL operations for fertilizer.


Digging Up Structures: The Rulebook implies the DIG action can clear goose coops or pastures. In the engine, DIG fails on occupied structures; it only works on empty ones.


Planting-Day Watering: The main Rulebook omits immediate watering rules, while the Getting Started guide notes the planting day counts as the first unwatered day. Because the end-of-day increment runs before the weed check, an unwatered seed turns into a weed that exact same night.


Melon Bonus Window: The Object Types table lists the Melon's Time to Max Yield as 12 days. In practice, because yield reaches the maximum of 6 units at age 10, the last two days of the documented 6–12 window are dead turns that add no yield.


Strawberry Yield Limit: The Object Types table lists Strawberry as an ongoing crop with "Subsequent Yields: every other day". In reality, production is capped at a max yield of 4. A strawberry plant produces exactly 4 times (ages 10, 12, 14, 16) at +1 unit each, and then dies. It is not an indefinite producer.


Yield-Per-Day Calculations: The "Max yield / tile / DAY" table entries (e.g., Tomato at 4, Strawberry at 2, Cow at 1.0, Sheep at 0.67) use inconsistent formulas. Actual effective per-day yields differ significantly (e.g., the actual per-day yield for Tomato is 1, and for Strawberry it is 0.5).


Map & Unit Traps




Shed Grid Absence & Location: The documentation states actions require being "orthogonally adjacent to the shed" without specifying coordinates. Note that the shed does not exist as a tile object in the tiles array, so a starter script searching the array for it will find nothing. Its access points are strictly the four center tiles: (4,4), (5,4), (4,5), and (5,5).


Farm Hand Spawning on Locked Tiles: Hired hands spawn across the four center access tiles, prioritizing a free space following NWSE, or the least occupied space. Because only the NW quadrant is unlocked at the start, hands can spawn on LOCKED tiles. While most can step out within a turn, a hand landing on (5,5) (diagonally opposite the start) is completely enclosed by locked tiles and cannot move until you buy land.


Submission & Notebook Pitfalls



Bare main.py vs. Notebook Submission: The Getting Started guide's quick-start dictates a main.py file at the root. However, if you are using a Kaggle Notebook and strictly writing %%writefile main.py, the notebook's "Submit to Competition" feature produces no submission artifact and fails at scoring. Ensure you are bundling your files properly or using submission.py depending on the platform's execution environment.

## Comments

- **Domino Weir** (2026-08-04 19:05:02.757000, votes: 3)
  Thanks for your patience! README.md and AGENTS.md have been updated, as has the competition overview page. TLDR: engine is the source of truth. I'll run through these one by one:
  
  Game Mechanics & Yield Discrepancies
  
  
  
  
  Animal Care Bonus: Confirmed +1. Fixed in docs.
  
  
  Fertilizer Selling: Yes, SELL is valid for fertilizer. Fixed in docs.
  
  
  Digging Up Structures: Correct, DIG only works on unoccupied structures. If the structure is occupied, animals would have to escape first. Explicitly stated in rules.
  
  
  Planting-Day Watering: Yes, an unwatered plant will turn into a weed if you do not water it on the day it is planted (conceptually, I'm thinking of this as "you have to water a seed for it to grow"). Getting started guide is updated and watering rules are now explicitly stated everywhere.
  
  
  Melon Bonus Window: Updated time to max yield in docs for melons.
  
  
  Strawberry Yield Limit: Yes, strawberries and tomatoes are both "ongoing crops" that yield multiple times over, but they are not infinite. Subsequent yields are every other day up to a certain point before decay sets in and the plant dies. This is a slight distinction from animals, which are also ongoing but don't eventually decay. Subsequent yields column in the object types table has been updated to reflect that nuance.
  
  
  Yield-Per-Day Calculations: Updated in docs, using engine implementation as the source of truth.
  
  
  Map & Unit Traps
  
  
  
  
  Shed Grid Absence & Location: Access coordinates are now explicitly stated.
  
  
  Farm Hand Spawning on Locked Tiles: This was an actual bug and has been fixed. Spawned hands on locked tiles can move back to actionable tiles (also stated in readme).
  
  
  Submission & Notebook Pitfalls
  
  Good reminders here, appreciate the thoroughness!

  - **Charles Kalaba** (2026-08-04 19:39:00.423000, votes: 0)
    Do BUY_SEED / BUY_PRODUCT / SELL / BUY_LAND / BUY_ANIMAL market orders require a farmer or hand to be standing at one of the shed access tiles (4,4)/(5,4)/(4,5)/(5,5) to execute, similar to PICKUP/DROP? In my replay, these orders never executed once across 30 days despite being submitted every turn, while HIRE worked every time.

    - **Domino Weir** (2026-08-05 15:39:41.453000, votes: 0)
      No, they do not require you to be standing on an access tile- they can be executed regardless of where you are.

  - **Akul Sareen** (2026-08-14 23:09:29.373000, votes: 0)
    Does the last turn of the last day count? A minimal agent which just logs observations only printed 719 values up to day 29 turn 22 (0-indexed).
    
    https://github.com/Kaggle/kaggle-environments/blob/master/kaggle_environments/envs/kaggriculture/kaggriculture.py#L945 also makes it look that way.

- **Domino Weir** (2026-08-03 17:26:56.037000, votes: 2)
  Hey @sidhaarthshree, I'm looking into these discrepancies now!

- **** (2026-08-14 23:08:10.173000, votes: 0)
