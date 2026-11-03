# From replay orders to actual trades: a cash-flow breakdown

- Topic ID: 739972
- URL: https://www.kaggle.com/competitions/kaggriculture/discussion/739972
- Author: 3정훈
- Posted: 2026-09-07 15:27:15.864000
- Votes: 2
- Comments: 0
- Fetched: 2026-09-12T11:44:31Z

## Post

A replay might contain ["SELL", "STRAWBERRY", 100], but that does not mean 100 strawberries were sold. And even if the order fills, those units may trade at different prices.

I put together a notebook that reconstructs the fills and turns them into a revenue-and-cost breakdown: Kaggriculture | From Orders to Actual Trades

Here is what the gap looks like on one public leaderboard replay. The units sold and the reconstructed revenue come from the notebook's ledger. I calculated the estimate separately, from the replay's raw SELL orders and the quote recorded at the start of each turn.




Player
Units offered for sale
Units sold
Order-quantity estimate
Reconstructed sales revenue




A
1,751
1,456
$107,392
$90,079


B
1,332
1,332
$96,976
$92,407




For Player A, the quantity sold fell 295 units short of the quantity requested. Player B's orders filled in full, but realized revenue was still $4,569 below the estimate because execution prices differed from the pre-turn quotes. The first comparison involves both quantity and price; the second isolates the pricing gap.

There are two things to account for.

Prices change within an order.

The engine settles trades one unit at a time. Each sale above the $1 floor adds market inventory, which can lower the quote for subsequent units. The engine pairs the two players' orders by queue position. Within each position, it quotes the next eligible unit for each player from the same inventory snapshot, attempts both fills, then repeats with the updated inventory.

To isolate that effect, here is a hypothetical sale starting at the default inventory of 10,000, with no opponent trades, no town consumption, and no shed limit:




Product
Quantity
Quantity × starting quote
Reconstructed proceeds
Estimate / proceeds




Strawberry
100
$12,000
$3,847
3.1×


Milk
122
$19,520
$6,227
3.1×


Wool
105
$21,000
$7,974
2.6×


Melon
300
$75,000
$26,627
2.8×


Carrot
450
$15,750
$8,418
1.9×


Wheat
400
$10,000
$8,313
1.2×




The quantities use the engine's T constants. This is an illustration of the pricing effect, not a feasible single-turn sales plan. In the first four rows the ratio also reflects units that sell at the $1 price floor rather than at a gradually falling quote: 38 of the 100 strawberry units, 46 of 122 milk, 46 of 105 wool and 142 of 300 melon. Excluding those units from both the estimate and the proceeds gives ratios of 2.0×, 2.0×, 1.5× and 1.5×. Carrot and wheat have no floor sales.

The difference can also be small. In the notebook's demo the farmer sells in small batches, and the same order-quantity estimate, again computed outside the notebook, comes to $8,907 against the notebook's $8,892 of reconstructed revenue, a difference of about 0.2%. The size of the error depends on the product, market inventory, order size, and the other player's trades.

Orders may fill partially — or not at all.

The engine reads only the first maxMarketOrdersPerTurn orders of a turn, 10 by default, and discards the rest. Of those, sales stop when the shed runs out of the item. Purchases can stop when cash runs out, and product or animal purchases also need room in the shed. Later orders retain their original queue positions.

The shed itself can change before trading begins. A farmer might drop goods off, pick something up, or build a structure before a hand places an animal in it. The notebook applies those actions in order, then replays both players' market queues with the resulting stock.

Checking the reconstruction

My saved copy of this replay includes the tile grid only twice per game day, but the notebook needs it at every step. So I regenerated the episode from its seed and recorded actions, then verified that every field the saved copy retained matched, including both players' cash at all 720 steps. The ledger checks below run on that regeneration. The quote check runs on the original recording, where it is not circular.

The reconstruction produced 826 ledger entries. The checks were:



Reconstructed net cash changes match the recorded changes for all 1,438 player-turns.

Total absolute error and the largest single-turn error are both $0.00.

Separately, all 6,480 recorded quotes match the installed engine's price function using the episode's parameters.


The cash check compares net changes per player per turn, so offsetting errors within one turn could still pass. It is a consistency check rather than proof of every individual fill.

The notebook's tables break the season into revenue by product, with units and average sale price, and spending by category. Its charts show the cash balance through the season, daily cash in and out, spending by category, and how each product's selling price changes as market supply accumulates. You can also compare realized revenue with what the same quantities would have earned at base prices.

It requires both players' full private observations and the farm's tile grid at every step. If your saved replay omits the grid, regenerate the episode using the original seed (in downloaded Kaggle replays this is info.seed; configuration.seed is often null), the configuration, the recorded actions, and a matching engine version, then check the regenerated observations against the fields you retained. This notebook uses kaggle-environments==1.32.7.

To point it at another replay, load it into a dict and run A = analyse(my_episode), then inspect A["report"] before reading the P&L.

If you try it and find a replay that does not reconcile, please share the engine version and the failing turn. I'd be interested in tracking down the difference.
