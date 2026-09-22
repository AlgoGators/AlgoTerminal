> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Phase 1 — Side structure (preregistered)

Status: preregistered. No numbers measured yet.

## Question

Is the v1 long-only book a regime artifact or a structural law?

v1 concluded "short side is dead" from an in-sample test with no OOS
confirmation. The OOS engine never shorted a crack leg.

## Hypotheses

H1. Fading stretched cracks (z > +0.75 / +1.0) has period-dependent
edge. It pays in margin-compression regimes and bleeds in tightness
regimes.

H2. A stretch-momentum leg (ride stretched margins while they persist)
captures the right tail that reversion fades.

H3. A split book (left reversion + right momentum) beats the long-only
book on OOS Sharpe and drawdown.

## Experiments

1. Short-side fade on corrected engine, OOS window, costs 5bps/20roll.
2. Stretch-momentum leg, same engine and costs.
3. Book variants: v1 long-only, balanced reversion, split book.
4. Regime drill: 2011-2014 (compression) vs 2023-26 (expansion).

## Negative controls

- Shuffled signal labels.
- Same construction on shuffled returns.

## Deliverable

Decision memo: v2 side structure. Written to `findings/phase1_findings.md`.
