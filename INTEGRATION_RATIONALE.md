# Integration Rationale — Book Strategy (Energy Margin Factor Book)

Ready-to-paste prose for the algoterminal research record. Covers the
hypothesis.yaml fields (thesis, expected_edge, risk_notes), the writeup
Methodology section, and a short summary.

---

## Thesis (hypothesis.yaml `thesis`)

Refiners are structurally short the crack spread: they buy crude, sell
products, and capture the margin. To lock in earnings they hedge by selling
product futures and buying crude futures. When a refined-product margin is
crushed below its normal level for the season, the physical economy is
forced to adjust: refiners cut runs, shift yields, and product supply
falls. The margin then reverts toward normal. This reversion is slow
(weeks, not days), asymmetric (the crushed side reverts; the stretched
side can stay stretched while crude momentum persists), and it shows up
independently in several markets at once.

## Expected edge (hypothesis.yaml `expected_edge`)

The edge is a long-horizon (90-day), seasonal, long-only mean reversion on
refined-margin stress, expressed in five nearly-independent places: the WTI
3:2:1 crack, the WTI heating-oil crack, the single most-crushed leg of the
WTI complex (cross-sectional), natural gas winter-demand crush, and the
Brent-WTI crude basis. The five factors have near-zero pairwise
correlation (max ~0.25), so the combined book compounds their edges
through diversification: single-factor in-sample Sharpe ~1.2-1.5, combined
book ~2.6 (3y daily data, no costs). The original v1 strategy had no
measurable edge: it traded the wrong series (primary close instead of the
crack), built the crack with a unit mismatch (per-gallon products minus
per-barrel crude), used a 20-day horizon where the force does not act, and
faded both directions when only the crushed side reverts.

## Risk notes (hypothesis.yaml `risk_notes`)

The book is exposed to energy-wide regime shocks that synchronize all
factors: a crude supply shock, a demand collapse, or a major weather event
can move every leg at once. Instant gaps cannot be pre-positioned; a gap
while positioned is the residual tail. Protection is per-factor: a 3-sigma
daily circuit breaker, a 20% hard stop below entry (a tail cap that never
triggers in normal moves), and a cooldown after forced flattens. The
trailing stop is used only on the crack legs. On vol-clustered instruments
(natgas, Brent-WTI) a fixed-vol-distance stop cuts trades on normal
retracements, so those factors run without it. Bleedout risk: a crushed
margin can continue a few days before reverting; the strategy holds
through it. In-sample there were no catastrophic tail hits. The residual
out-of-sample tail (a synchronized multi-factor gap) is the main unbudgeted
risk; a book-level vol cap or options hedge would address it. Parameters
are mid-plateau picks on a 3-year sample. Results are in-sample, exclude
costs and futures rolls, and need out-of-sample validation before capital.

## Writeup Methodology (paragraph)

The strategy is a portfolio of five factors, each a simple expression of
one assumption. F1 buys the WTI 3:2:1 crack and the WTI heating-oil crack
when their deseasonalized z-scores are crushed below -0.75 against a
trailing same-calendar-month mean (no lookahead), and exits when the crush
fades above -0.5. F2 ranks the WTI complex each day and holds the single
most-crushed leg of {3:2:1, gasoline, heating}, but only when it is
genuinely crushed (z < -0.5): a yield-switching concentration bet. F3
applies the same seasonal-crush logic to natural gas, a separate market
driven by weather and storage. F4 mean-reverts the Brent-WTI crude basis
in both directions, capturing geography and logistics flows. Each factor
is sized by per-factor volatility targeting and risk-managed per-factor
(circuit breaker, hard stop, cooldown; trailing stop on the crack legs
only). The five factors are combined with inverse-volatility weights, so
the book's Sharpe is the diversification compounding of near-uncorrelated
edges. The economic rationale for each factor is the same forced-physical-
adjustment story: a margin crushed below its seasonal norm triggers real
supply responses (run cuts, yield shifts, imports, flows) that restore it.

## Short summary (writeup conclusion / one paragraph)

The Book Strategy replaces the original symmetric 20-day fade of the crack
spread with a long-horizon, seasonal, long-only reversion of refined-margin
stress, expressed in five nearly-independent markets and combined so that
diversification, not any single factor, produces the edge. Where v1 traded
an artifact (a unit-mismatched number on the wrong series at the wrong
horizon and the wrong sign), the Book trades a real economic force: a
crushed margin forces the physical economy to fix it, over weeks, and that
reversion is captured independently in WTI products, natgas, and the crude
basis. In-sample the single factors show Sharpe ~1.2-1.5 and the combined
book ~2.6 with MaxDD -3.9%; the numbers are in-sample and uncosted, so the
next step is 10-year out-of-sample validation and a transaction-cost and
roll model before sizing capital.
