# Phase 4 — Representation rebuild (preregistered)

Status: preregistered. No numbers measured yet.

## Question

Can a structural, shape-aware representation beat the z-pipeline?

The z-score discards shape. Deep+fast-deepening (crisis V) and deep+grind
(bleed) share the same level but have opposite forward distributions.
The v1 signal cannot tell them apart.

## Hypotheses

H1. Structural calendar features (maintenance turnarounds, blend-switch
dates, holiday and seasonal demand) carry information the same-month
mean misses.

H2. Shape-aware states (depth, speed, inflection) separate crisis
windfalls from grind bleeds.

H3. The joint crisis filter (fast-deepening into deep crush plus crude
crash) integrates cleanly into a position rule.

H4. Regime typing (expansion, compression, crisis) with per-regime
exposure rules beats one global rule.

## Experiments

1. Calendar features from EIA utilization and RVP blend dates.
2. Shape-state tuple instead of a single z.
3. Joint crisis filter integration.
4. Full v2 construction with pre-registered mid-plateau thresholds.

## Deliverable

v2 final construction, frozen forward-test protocol, release manifest.
Written to `findings/phase4_findings.md`.
