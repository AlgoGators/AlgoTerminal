> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Phase 2 — Multi-crush basket + depth sizing (preregistered)

Status: preregistered. No numbers measured yet.

## Question

Can the book capture two crushes at once, and does crush depth carry
sizing information?

v1 holds exactly one leg (argmin z). Concurrent crushes are ignored.
Depth below the entry threshold is never used for sizing.

## Hypotheses

H1. Holding every crushed leg (z below threshold) at product level beats
holding one leg on OOS return and drawdown.

H2. Sizing by crush depth improves Sharpe without increasing tail risk.

H3. Product-level legs (gas crack, HO crack) avoid the double-counting
inherent in holding 3:2:1 plus single legs.

## Experiments

1. Product-level basket, multi-leg concurrent holding, per-leg stops.
2. Depth-weighted sizing vs flat-on sizing.
3. Turnover comparison: multi-leg vs single-leg construction.

## Negative controls

- Shuffled depth ranking.
- Random leg subsets.

## Deliverable

Decision memo: v2 basket construction and sizing rule. Written to
`findings/phase2_findings.md`.
