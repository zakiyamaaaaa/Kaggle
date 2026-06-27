# exp-003-mixed-v1

- Name: mixed-v1
- Kaggle tag: `exp-003-mixed-v1`

## Hypothesis

exp-002 scored 0.0 because EXFILTRATION-only recording dropped wins that exp-001 relied on (especially CONFUSED_DEPUTY).

Strategy:

1. **Phase 1** — Keep exp-001 baseline prompts (direct exfil + confused deputy + multi-turn)
2. **Phase 2** — Merge exp-001 snapshot follow-ups with exp-002 encoding POST variants
3. **Phase 3–4** — Run exp-002 exfil grid but record **any** predicate (like exp-001)
4. Dedupe identical message chains via `seen`

## vs exp-002-exfil-encoding

- Record any predicate, not EXFILTRATION only
- Baseline wins run first before expensive exfil grid
- Reduced exfil grid (5 follow-ups vs 8) to preserve time budget

## vs exp-001-baseline

- Adds guardrail-aware multi-turn exfil attempts from exp-002
- Adds deduplication
- Extended snapshot branching with encoding POST variants

## Result

- Public score: **0.060** (submitted 2026-06-26)
- exp-001 baseline: **0.255** — mixed strategy underperformed despite including same Phase 1 prompts

## Post-mortem (why 0.060 < 0.255)

Likely causes:

1. **Generation time budget** — Phase 3 adds 15+ multi-turn attempts (`margin_s=240`). On production LLM each interact is slow; budget may exhaust before replay collects as many wins as a short exp-001 run.
2. **Replay load** — More returned findings → longer replay phase; partial scoring or fewer successful replays if infra is tight.
3. **Non-deterministic agent** — Same prompts do not always reproduce; exp-001 score may have been a favorable run.
4. **Exfil grid still low yield** — Extra attempts did not add replayable EXFILTRATION; only a small deputy/exfil subset (~12 raw ≈ 0.060 LB) may have scored.

Next: exp-004 should prioritize **fast exp-001 wins**, expand **cheap deputy variants**, skip or gate heavy exfil grid behind `time_left`.
