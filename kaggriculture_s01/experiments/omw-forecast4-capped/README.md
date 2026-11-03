# OMW forecast4 capped overlay

This local experiment keeps the One More Wheat controller frozen and retains
the forecast4 confidence gate from `omw-forecast4`. The only additional
change is a quantity cap on the distant (3–4 turn) branch: its inserted SELL
quantity cannot exceed the selected stream's predicted SELL quantity over the
next four turns.

- control: `omw-original.py` (byte-for-byte copy of the current OMW source)
- candidate: `main.py`
- immediate 1–2 turn branch: unchanged from `omw-forecast4`
- distant 3–4 turn branch: confidence gate plus predicted-next-four quantity cap
- feed/risk layers: unchanged

This is a local experiment only. It must pass the same paired panel screen
before being considered for validation or submission.

