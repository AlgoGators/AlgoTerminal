> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Phase 1R — mechanism-based short side (preregistered)

Status: preregistered. Supersedes the Phase 1 mirror test for the short
side. Phase 1 findings remain as the record of the naive construction.

## Why this revision exists

Phase 1 tested the short side as a mirror of the long side: same z
threshold, same state machine, same sizing. The long side reverts via
capacity exit and seasonal demand return. The short side must end a
tightness episode. The two mechanisms need different signals.

This revision builds four short candidates, each with its own entry
shape. No combining until a candidate is profitable on its own OOS.

## Common input

Seasonal z of the level (v1 definition). Candidate-specific entry
conditions below. Common exit: z <= +0.5 (symmetric with v1's long
exit). Sizing, risk, costs identical to v1: fixed-vol scaling, per-leg
circuit breaker, hard stop, cooldown, 5bps/20roll.

## Candidates

| ID | Direction | Entry (all use z >= +0.75) | Exit | Assumption |
| --- | --- | --- | --- | --- |
| S1 easing-fade | short | 5-day z change < -0.2 | z <= +0.5 | The stretch ends when it stops stretching. Fade the inflection, not the level |
| S2 acceleration-ride | long | 5-day z change > 0 | 5-day z change < 0 or z <= +0.5 | Tightness persists while it accelerates. Ride the stretch, exit at first easing |
| S3 regime-conditional short | short | level above its trailing 252-day mean (expansion regime) | z <= +0.5 | Phase 1 drill: shorts paid only in expansion regimes. The regime is part of the signal |
| S4 seasonal-top fade | short | calendar month in {3, 4, 9, 10} (shoulder months after winter and summer peaks) | z <= +0.5 | Stretched margin on the wrong side of a demand peak rolls over |

All conditions causal: z and 5-day change use observations up to the
prior close. The regime filter uses the level shifted by one day.

## Test design

- Each candidate runs on crack_321 (level 3:2:1).
- Each candidate runs on the cross-sectional leg (most-stretched leg of
  {crack_321, crack_gas, crack_ho}) with per-leg conditions.
- Report standalone leg stats, then candidate book = crack leg +
  cross leg + bzwti, equal weight.
- Negative control per candidate: time-shuffle its signal (20 seeded
  permutations), rebuild the book, compare OOS overlaid Sharpe.
- Combination rule: a short leg may join the v1 long book only if it is
  independently positive OOS on its own.

## Deliverable

findings/phase1r_findings.md. Decision: which short-side mechanism, if
any, survives. The physical-data candidates (utilization-pinned tops,
inventory-rebuild fades) are preregistered in Phase 3.
