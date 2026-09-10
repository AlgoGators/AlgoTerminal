# Evaluation Lens — Behavior First, Numbers Second

This file owns the evaluation procedure for every experiment in this
worktree. LONG_BACKTEST_FINDINGS.md references it. Read it before judging
any run.

## Why

The edge is episodic and convex. 77% of the OOS total return came from 5
of 16 years. 32% came from the top-5 single days. A single Sharpe number
over such a payoff is a thin average over a bimodal regime distribution.
Optimizing a number rejects regime information and convexity before they
are understood.

## Procedure: answer all seven before any verdict

1. Behavior: which regimes and states did it win in, which did it bleed
   in? Decompose by year, by episode, by state.
2. Mechanism: why did the behavior happen? What does it say about the
   edge's true driver (flow vs physical, level vs inflection, demand vs
   positioning)?
3. Retained signal: what did it capture that is still usable? Direction,
   size, regime identity, correlation info. A failed gate can carry a
   working direction.
4. Control: what did the negative control actually prove? It proves "this
   construction carries no information", never "the underlying idea is
   dead".
5. Scope: which exact hypothesis failed, and which neighbors are still
   standing? Name both.
6. Variants: what implementation was not tested? Most failures are
   failures of one naive construction.
7. Next question: what is the sharpest new question this run raises?

Verdicts use the full space. Kill a construction. Keep the idea until the
variant space is plausibly covered.

## Metrics are evidence, not verdicts

Report the standard stats, then add what the profile demands:

- payoff concentration: share of return from top-N days and top-N years
- stress correlation: relation of strategy returns to stress states
  (energy vol, drawdown phases)
- participation: what the DD overlay forgives on the upside vs what it
  caps on the downside
- convexity: does it gain more in shocks than it bleeds in slow regimes
- per-regime stats: compression, stress, and calm separately

## What a finding is

A finding is a behavioral fact plus a mechanism hypothesis plus the
falsified construction, written so the next experiment can use it. A
table row is not a finding.
