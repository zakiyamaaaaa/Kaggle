# OMW forecast4 overlay

This experiment keeps the One More Wheat controller frozen and adds only the
Herd-Safe v3 v2 forecast4 gate to its existing `v9/2 PREDICT` layer.

- control: `omw-original.py` (byte-for-byte copy of the current OMW source)
- candidate: `main.py`
- immediate signals: the original 1–2 turn, `K=4`, `H=48` behavior
- distant signals: turns 3–4 are allowed only when the selected stream has at
  least 3 matched events and at least 70% precision over the prior 240 turns,
  using the existing ±1 turn matching rule
- feed/risk layers: unchanged

The source snapshot used for both files is
`references/kaggle-scan-2026-09-21/extracted/one-more-wheat/main.py`.

This is a local experiment only. It must pass the existing panel screen before
being considered for validation or submission.
