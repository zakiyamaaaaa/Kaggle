# OMW forecast4 repeat guard

This local experiment keeps the `omw-forecast4` candidate unchanged except
for a per-item cooldown on the distant (3–4 turn) forecast branch.

- the immediate 1–2 turn branch is unchanged
- after a distant forecast SELL fires for an item, that item cannot fire the
  distant branch again for 4 turns
- cooldowns are independent for MILK, WOOL, and STRAWBERRY
- quantity, order placement, feed, and risk layers are otherwise unchanged

The goal is to isolate repeated per-item early selling without mixing in an
externality-aware margin gate. This is a local experiment only; no submission
is made.

