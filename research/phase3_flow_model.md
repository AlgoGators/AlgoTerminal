> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Phase 3 — Flow modeling with EIA (preregistered)

Status: preregistered. No numbers measured yet.

## Question

Does directionally modeled physical flow beat on/off gating?

v1 falsified gates (weather, storage, utilization). It never tested
directional modeling. The Cushing stock z-score was the one variable
with the predicted sign.

## Hypotheses

H1. Refinery utilization direction and product-supplied (implied demand)
condition crack-crush reversion better than no conditioning.

H2. Cushing utilization (stocks divided by capacity) improves the
Brent-WTI leg more than a stock z-score.

H3. Flow features work as scaling or tilt on positions, not as switches.

## Experiments

1. Features with 6-day release lag and forward fill (machinery from the
   EIA fundamental experiment).
2. Directional overlay on positions.
3. Per-leg attribution: flow-driven (cracks) vs physical (Brent-WTI).
4. Long-run regime diagnostics: capacity trends, EV share.

## Negative controls

- Shuffled feature timing.
- Lag-inverted features.

## Concrete tilt rules (stated before measuring)

Data: EIA weekly series fetched 2007-01-05 .. 2026-09-04 (engine/eia/raw_*.csv).
Codes selected: WGTSTUS1 gasoline, WDISTUS1 distillate, WCESTUS1 crude,
W_EPC0_SAX_YCUOK_MBBL Cushing, WPULEUS3 utilization.
WPRTOTUS1 (product supplied) and crude runs return empty from the API.
Implied demand proxy = product stock draw (gasoline + distillate change).

Feature pipeline (causal, reuse of the EIA experiment machinery):
weekly changes -> same-month expanding z (min 12 obs) -> release date
plus 6 days -> forward fill onto the daily panel -> scale = tilt.shift(1).

The tilt is a position multiplier, never a switch. Thresholds +-1.0
on the z-score, multipliers 1.25 / 0.75.

| Tilt | Leg | Rule | Mechanism |
| --- | --- | --- | --- |
| T1 utilization | crack_321, cross | util_z <= -1 -> 1.25; >= +1 -> 0.75 | Utilization falling means capacity exit, faster reversion |
| T2 demand (product draw) | crack_321, cross | draw_z >= +1 -> 1.25; <= -1 -> 0.75 | Draws mean demand support, stronger reversion |
| T3 Cushing fullness | bzwti | fullness >= 0.85 and draw_z >= +1 -> 1.25; fullness >= 0.85 and draw_z <= -1 -> 0.75 | Tank tops clearing -> WTI discount closes |
| T4 combined | all | T1 + T2 on cracks, T3 on bzwti | Joint flow state |

Fullness = Cushing level / trailing 156-week max (capacity proxy).

Books: baseline A (no tilt) must reproduce the frozen champion. Then
A+T1, A+T2, A+T3, A+T4. Report IS/OOS raw and overlay.

Controls (per tilt):
1. Shuffled tilt timing: permute the tilt series in time, 20 seeds.
2. Sign-flipped tilt: swap 1.25 and 0.75. Direction specificity.

Combination rule from Phase 1R applies: a tilt joins the book only if
it improves OOS Sharpe or drawdown for its leg without degrading the
other legs.

## Deliverable

Decision memo: v2 driver map. Written to `findings/phase3_findings.md`.
