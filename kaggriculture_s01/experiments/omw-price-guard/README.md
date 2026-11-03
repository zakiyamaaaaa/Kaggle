# OMW forecast4 price guard

This local experiment keeps `omw-forecast4` unchanged except for a price
guard on distant forecast SELLs. A distant SELL is allowed only when the
current market quote is above that product's model base price. The base is
品目別 in the shared market parameters: MILK 160, WOOL 200, and STRAWBERRY
120.

- immediate 1–2 turn branch: unchanged
- distant branch: block when current price <= item-specific base price
- order placement, quantity, feed, and risk layers: unchanged

This is a local experiment only; no submission is made.

