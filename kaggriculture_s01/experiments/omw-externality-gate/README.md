# OMW forecast4 externality gate

This local experiment keeps `omw-forecast4` unchanged except for a gate on
distant forecast SELLs. Before firing, it estimates the price loss imposed on
the rival's predicted next-four-turn batch by adding our early-sale quantity
to the shared market inventory. The distant SELL is blocked when that rival
loss exceeds 50% of our estimated current-price revenue.

- immediate 1–2 turn branch: unchanged
- externality estimate: shared-market price model and public rival stream
- threshold: rival estimated loss <= 50% of our current-price revenue
- feed, risk, order placement, and quantity logic: unchanged

This is a local experiment only; no submission is made.

