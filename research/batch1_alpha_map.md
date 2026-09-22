> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Batch 1 — alpha source map, cheap items (preregistered)

Correction record: the serial phase plan scoped only part of the
captain-named space. This batch covers the cheap rows of
`research/alpha_source_map.md` in parallel. Selection happens only
after coverage.

Rows covered: 1 (winter maintenance), 2 (cold-weather vehicle demand),
3 (fuel blends), 7 (norm drift), 11 (correlations), 9/10 (multi-crush
basket + depth).

No parameters fitted in this batch. Thresholds are stated here before
measuring.

## M1 — winter maintenance calendar (source 1)

Mechanism: refineries take planned maintenance in winter to prep for
summer. Supply is tighter in the maintenance months, so a crushed
margin reverts stronger there.

Construction (causal):
- Utilization weekly, 6-day lag, forward-filled (EIA WPULEUS3).
- Ex-ante maintenance calendar = same-month expanding mean of
  utilization. A month is a maintenance month when that mean is at
  least 1.0 point below the expanding annual mean, evaluated at t-1.
- Tilt: scale up crack_321 and cross longs by 1.25 in maintenance
  months, else 1.0.

Controls: shuffled calendar (20 seeds), inverted calendar.

## M2 — cold-weather vehicle demand (source 2)

Mechanism: cold weather raises gasoline consumption (longer warmup,
thicker fluids, drag, tire pressure). Cold spells should precede
gasoline-crack strength in winter.

Event study (no position change):
- NYC T2M (NASA POWER, daily).
- Cold spell = Nov-Mar day with same-month expanding temperature z
  <= -1.0.
- Compare forward 10/20-day returns of crack_gas (RB*42-CL) and
  crack_ho after cold days vs after non-cold winter days. Return
  basis = diff / rolling mean |level|.
- Control: shuffled cold labels, 20 seeds.

## M3 — fuel blends (source 3)

Mechanism: summer/winter blend switches move gasoline cracks
independent of demand.

Construction:
- Windows: spring = Mar 20..Apr 15, fall = Sep 1..Sep 30.
- Compare inside vs outside window: seasonal z of crack_gas,
  forward 20-day return, 20-day realized vol.
- Control: shuffled windows, 20 seeds.

## M7 — norm drift (source 7)

Diagnostic only. Same-month mean and std of crack_321 and utilization
in 2007-2015 vs 2016-2026. Output: drift table. No position change.
Decision: whether the seasonal norm needs adaptive re-estimation.

## M11 — correlation matrix (source 11)

Re-export leg-level correlation on corrected net returns. Matrix IS
and OOS for crack_321, cross_sectional, crack_ho, ng, bzwti.
Output: CSV.

## M9/10 — multi-crush basket + depth (sources 9, 10)

Mechanism: hold every crushed leg at product level, not just the most
crushed. Depth beyond the entry threshold carries sizing information.

Construction:
- Legs: crack_gas, crack_ho (product level; avoids double counting
  from 3:2:1 plus singles).
- Long when seasonal z <= -0.75, exit z >= -0.5 (v1 hysteresis).
- Flat book: crack_gas + crack_ho + bzwti, equal weight.
- Depth book: position multiplier
  depth = clip(1 + 0.5 * (|z| - 0.75), 1.0, 2.0) while on.
- Compare both against the frozen champion (crack_321 + cross +
  bzwti).
- Control: shuffled depth multiplier ordering, 20 seeds.

## Deliverables

findings/batch1_findings.md. Statuses updated in
research/alpha_source_map.md.
