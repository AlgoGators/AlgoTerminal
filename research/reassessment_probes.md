> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Reassessment probes — Tier 1 phenomenon tests (preregistered)

Three resurrected leads from findings/reassessment.md get Tier 1
evidence before any machine is built. Thresholds stated before
measuring. No positions, no costs in the bucket tests. One light
construction check for the multi-leg F2 lead.

## N1 — NGL/propane winter (ch27)

Chain: winter RVP allowance pulls butane into gasoline, drawing
NGL/propane stocks; NGL state may condition the gasoline leg and NG
winter.

- Propane same-month z (WPRSTUS1, 6-day lag, forward-filled).
- Season windows: winter = months {11,12,1,2,3}, summer = {5,6,7,8,9}.
- Bucket propane z into quintiles within season; forward 20-day
  gasoline-crack return per bucket (diff/rolling mean |level|).
- Same buckets vs forward 20-day NG level return (winter only).
- Control: shuffle propane z labels within season (20 seeds),
  compare real top-minus-bottom delta.

Verdict: monotone positive top-minus-bottom in winter = N1 present.

## C1 — Cushing utilization ratio (ch29)

Chain: fullness (stocks / trailing 3y max) is the physical utilization
measure; high fullness predicts the WTI discount closing (spread
narrowing).

- Fullness = Cushing / trailing 156-week max, 6-day lag, ffill.
- Bucket fullness quintiles; forward 20-day change of bzwti level.
  Hypothesis: high fullness buckets have negative mean (narrowing).
- Combined: fullness >= 0.85 and Cushing draw z >= +1 (tank tops
  clearing) vs all other days.
- Control: shuffled combined condition (20 seeds).

## M1 — multi-leg F2 depth phenomenon (ch30)

Chain: deeper crush carries stronger reversion per held leg; the
single most-crushed leg loses simultaneous crushes.

- Phenomenon buckets: pooled crushed days (seasonal z <= -0.5 on any
  cross leg), bucket crush depth |z| into quintiles; forward 10/20-day
  return of the held leg's own level. Monotonicity check.
- Light construction (the only machine here): multi-leg F2 with depth
  multiplier clip(1 + 0.5*(|z| - 0.5), 1, 2); per-leg risk, costs
  5bps/20roll; compare leg net OOS stats vs the v1 single most-crushed
  cross leg. No book, no overlay.
- Control: shuffled depth multiplier among on-days (20 seeds), top-
  minus-bottom delta.

Verdict by both phenomenon monotonicity and construction delta.

## Deliverable

findings/reassessment_probes.md. Status updates for chains ch27,
ch29, ch30 in research/graph/chains.csv.
