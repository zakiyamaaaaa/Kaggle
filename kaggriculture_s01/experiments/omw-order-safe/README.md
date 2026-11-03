# OMW order-safe forecast4 overlay

This local experiment keeps the `omw-forecast4` confidence-gated predictor
and changes only the placement of new SELL orders in the distant (3–4 turn)
branch.

- existing market orders are left untouched
- a new forecast SELL is appended only when a market slot is available
- a full market skips the forecast SELL
- no forecast SELL is inserted at index 0, and no existing order is displaced
- immediate 1–2 turn behavior, quantities, feed, and risk layers are unchanged

The purpose is to isolate the market-order externality from the forecast
quantity logic. This is a local experiment only; no submission is made.

