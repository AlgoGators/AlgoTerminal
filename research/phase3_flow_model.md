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

## Deliverable

Decision memo: v2 driver map. Written to `findings/phase3_findings.md`.
