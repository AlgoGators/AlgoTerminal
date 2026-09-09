# Book Strategy — Edge Rationale: Where the Edge Comes From vs v1

This document rebuilds the systematic and economic rationale for the final
Book strategy (factor_book.py) from first principles, and contrasts it with
the original v1 strategy at every step. It answers one question: why does
the Book succeed when v1 did not, and where exactly is the edge derived
from?

Data: 3y daily, 2023-09-08 to 2026-09-08, yfinance (CL=F, BZ=F, RB=F,
HO=F, NG=F). Book stats are post-warm-up (>= 2024-01-01), in-sample, no
costs.

---

## TL;DR

v1 did not fail because the thesis was wrong. It failed because it could not
measure the thesis, then measured the wrong timescale, on the wrong series,
with the wrong sign.

1. The engine fed it CL's raw price, not the crack. 2. The crack was built
in mixed units (per-gallon products minus per-barrel crude). 3. It faded a
20-day stretch, but the refiner-hedging force operates over 90-180 days.
4. It faded both directions, but only the "crushed" side has a forced
physical adjustment behind it. 5. It ignored seasonality, so "crushed" was
measured against noise, not against normal.

The Book keeps the correct thesis (refiner hedging pressure mean-reverts a
crushed margin) and fixes all five errors, then multiplies the result
across five nearly-independent expressions of the same structural logic.
The single-factor edge is modest (~1.2-1.5 Sharpe). The 2.63 Book Sharpe
is the diversification math working: five average Sharpe factors at ~0.1
correlation compound to about 2.6.

The progression: data honesty (v1 -0.54 Sharpe) -> correct signal
(v3 +1.25) -> two-leg book (v4 +1.44) -> five-factor book (+2.63).

---

## Part 1 — What v1 actually was (the autopsy)

v1's backtest said: CAGR -5.9%, Sharpe -0.54, MaxDD -18.7%, 141 trades.

Every one of those numbers was an artifact:

| v1 element | What it actually did | Why it was wrong |
| --- | --- | --- |
| Engine input | `run_backtest` passed `data[primary]["close"]` = CL raw price | The strategy docstring itself says: "A raw instrument close such as CL alone does not express the thesis and will not work." It mean-reverted crude oil futures, i.e. it traded the mock of a crack thesis. |
| Crack construction | `(2*RB + HO)/3 - CL` | RB/HO are quoted in USD/gallon; CL is USD/barrel. 1 barrel = 42 gallons. The mixed-unit level sits around -71 when the real crack is around +29. It was a meaningless number, not a margin. |
| Data | HO returned 0 rows; RB had 15 months | yfinance needs `HO=F`, not `HO`. The complex was incomplete. |
| Lookback | 20-day z-score | The hedger-pressure force acts over weeks (90-180d). At 20d the crack behaves like momentum: after a stretch it usually goes further, not back. The fade bet the wrong direction on the wrong horizon. |
| Side | Symmetric: short stretched AND long crushed | Only the long side has a forced physical adjustment. The short side was beaten by the first-half uptrend (+18.7% adverse fwd20). |
| Seasonality | None | The crack has an annual cycle (summer ~38, winter ~21). Raw z-scores call a normal summer level "stretched" and a normal winter level "crushed". The signal was triggered by the calendar, not by stress. |

Net: v1 was a short-horizon, symmetric, unseasonal fade of the wrong
series. It should not have worked, and it did not.

## Part 2 — The correct economic logic

The thesis, restated precisely:

A refiner is structurally short the crack. The business is: buy crude, sell
products, capture the margin. To lock in earnings, refiners hedge by selling
product futures and buying crude futures. Therefore:

- A **crushed** crack (margin below normal) forces physical action. Refiners
  cut runs, import products, and switch yields. Product supply falls, crude
  demand falls, the margin recovers. The force is real, slow, and structural.
- A **stretched** crack does not force the reverse fast enough. It can stay
  stretched while crude supply or demand momentum persists. The force on
  that side is weak and regime-dependent.

The correct edge is: **buy the seasonally-crushed margin, wait for the
physical economy to fix it.** That is a weeks-long, long-only reversion.

## Part 3 — The four systematic upgrades

1. **Data honesty**
   - Real crack: `(2*RB + HO)/3 * 42 - CL`, per barrel.
   - Full panel (CL, RB, HO) fed to the strategy, not CL alone.
   - Correct tickers (HO=F). This did not add edge; it made measurement
     real. v1 on the true crack was still -0.60 Sharpe.
2. **Timescale**
   - Z-score lookback 90d (from 20d). The force lives at 90-180d.
   - Empirical: at lb=20 the fade has no edge; at lb=120 buying a crush
     reverts +7% fwd20; deseasonalized, +12-15%.
3. **Seasonal norm**
   - "Crushed" = deseasonalized z-score vs a trailing same-calendar-month
     mean (expanding, no lookahead).
   - This isolates genuine margin stress from the deterministic calendar:
     a crush is "low for late summer", not just "low".
4. **Asymmetry**
   - Long-only. The short side is excluded (weak edge, trend-regime risk).
   - Bleedout note: the continuation of the crush in the first ~5 days is
     handled by holding through it (the seasonal signal is positive from
     day 1; no stop forces you out of the reversion).

## Part 4 — The diversification engine

### Why near-zero correlation compounds Sharpe

For N factors with equal Sharpe S and common pairwise correlation rho, the
equal-vol portfolio Sharpe is approximately:

    SR_portfolio = S * sqrt(N / (1 + (N-1)*rho))

With N=5, average factor Sharpe ~1.35, average rho ~0.08:

    sqrt(5 / (1 + 4*0.08)) = sqrt(5 / 1.32) = sqrt(3.79) = 1.95
    1.35 * 1.95 = 2.63

That is the exact Book Sharpe. The point is structural: 2.63 is what you
expect when you combine five honest, independent ~1.3-Sharpe edges. It is
not one magic factor; it is the sum of independence.

### Each factor's economic identity

| Factor | Market | Edge source | Economic rationale | Sharpe |
| --- | --- | --- | --- | --- |
| F1a | WTI 3:2:1 crack | seasonal crush reversion, long | Refiner run-cut hedging pressure restores refined margins | 1.29 |
| F1b | WTI heating crack | seasonal crush reversion, long | Same force on winter demand; different refining (distillate) side | 1.16 |
| F2 | WTI complex (3:2:1, gas, HO) | long the single most-crushed leg | Yield-switching: refiners rebalance within the barrel; the most-crushed product recovers relative to peers | 1.53 |
| F3 | Natgas | seasonal crush reversion, long | Same logic in a different commodity (weather/storage demand); zero correlation with crude complex | 1.23 |
| F4 | Brent-WTI spread | z-reversion of the basis, both sides | Geography/logistics arbitrage: flows, tankers, export capacity keep the crude basis anchored | 1.55 |

F1a and F1b: the original crack thesis, corrected. Gasoline vs heating
cracks are 0.11 correlated (different seasons, yield tradeoffs), so even
the two core legs diversify each other.

F2: not a new market, a new construction. Rank the complex, hold the most
crushed leg only when it is genuinely crushed (z < -0.5). This
concentrates the reversion bet where it is strongest and sidesteps the
gasoline leg's poor standalone profile.

F3: the same "seasonal crush -> forced adjustment -> reversion" pattern in
a separate market. Natgas demand is weather/storage driven, uncorrelated
with refining margins. Correlation with the complex: ~0-0.2.

F4: a pure geographic basis trade. WTI-Brent is anchored by logistics
(flows respond to the price gap). Weak per-trade, but trades often and
sits at ~0 correlation with everything.

### Cross-correlation matrix (post-warm-up)

    F1a 1.00  0.20  0.08  0.25  0.01
    F1b 0.20  1.00  0.09  0.18 -0.05
    F2  0.08  0.09  1.00 -0.03 -0.01
    F3  0.25  0.18 -0.03  1.00  0.06
    F4  0.01 -0.05 -0.01  0.06  1.00

Max pairwise correlation 0.25. Most are 0.00-0.10. That is the entire
point: each factor fails in a different scenario, so the book survives any
single failure.

## Part 5 — The progression (attribution)

| Version | What changed | CAGR | Sharpe | MaxDD | Trades |
| --- | --- | --- | --- | --- | --- |
| v1 as-recorded | (broken: CL price, mixed units, 20d, symmetric) | -5.9% | -0.54 | -18.7% | 141 |
| v1 real crack | Engine + units fixed only | -4.7% | -0.60 | -15.4% | 13 |
| v3 | Seasonal long-only signal (90d z vs seasonal norm) | ~11.2% | +1.25 | -6.0% | 8 |
| v4 | Two-leg book (3:2:1 + HO), vt=0.5/leg | 28.8% | +1.44 | -18.9% | 17 |
| Book | + cross-sectional + NG + Brent-WTI, inverse-vol | 24.3% | +2.63 | -3.9% | multi |

What changed at each step, and how much of the improvement it caused:

1. **Data honesty: no edge change.** -0.54 -> -0.60. The fix was a
   prerequisite, not a source of edge. It made the measurement real.
2. **Signal: the whole sign flip.** -0.60 -> +1.25. The 90d seasonal,
   long-only reversion is where the thesis finally had a chance to work.
   This is the single biggest contributor: fixing the timescale, the
   seasonal norm, and the direction turned a negative-expected-value
   artifact into a positive edge.
3. **Two legs: modest Sharpe gain, big activity gain.** +1.25 -> +1.44.
   HO adds a 0.2-correlated second expression; trade count roughly
   doubles. MaxDD worsened only because vol doubled (two legs at vt=0.5).
4. **Five factors: the compounding step.** +1.44 -> +2.63. The increment
   is almost entirely diversification math, not better factors. F2, F3,
   F4 are independent expressions; combining them with inverse-vol
   weighting lifted Sharpe to 2.63 while MaxDD fell to -3.9%.

Sharpe is leverage-invariant. The Book runs at ~8% annualized vol
(conservative); CAGRs are not directly comparable across different vol
levels. What matters for the edge question is the Sharpe progression.

## Part 6 — What the edge is NOT (honest caveats)

- It is NOT a proven 2.6-Sharpe strategy. It is an in-sample 2.6-Sharpe
  construction on 3 years of data, with no costs, no roll model, and
  in-sample inverse-vol weights.
- The per-factor edges (~1.2-1.5) are the economically defensible claim.
  The Book's 2.63 is the mathematical compounding of independence, and it
  is fragile to correlation spikes (an energy-wide regime shock
  synchronizes all factors).
- Parameters were picked mid-plateau, but selection still exists in the
  3-year sample. The seasonal mean is thin early (needs ~10 same-month
  observations).
- v1's 141 trades were noise trades; the Book's per-factor trade counts
  are small (F1 ~17, F2 ~25% of days, F3 ~28%, F4 ~52%). Small samples,
  especially for the less-frequent factors.

The economic case is plausible; the empirical case needs out-of-sample /
10y confirmation before capital.

## Part 7 — Code map (rationale -> implementation)

| Rationale | Code |
| --- | --- |
| Correct crack (per barrel) | `build_levels` : `(2*RB + HO)/3 * 42 - CL`, `RB*42 - CL`, `HO*42 - CL` |
| Trailing seasonal norm, no lookahead | `seasonal_mean` : expanding mean of same calendar month, strictly before t |
| Deseasonalized z, 90d, strict 45 obs | `seasonal_z` |
| Long-only crush reversion with hold-through-bleedout | `f1_positions`, `f3_positions` hysteresis (enter z<-0.75, exit z>=-0.5) |
| Cross-sectional concentration | `f2_positions` : argmin z among legs, only if min z < -0.5 |
| Geography convergence, both sides | `f4_positions` : z of BZ-CL, symmetric hysteresis |
| Per-factor vol targeting | `vol_scale` (vt per factor) |
| Per-factor risk calibration | `apply_leg_risk` + `TRAILING_STOP_ON` dict |
| Tail cap / gap protection | hard stop 20% of entry + 3-sigma circuit breaker + cooldown |
| Portfolio compounding | `main` : inverse-vol weights, correlation matrix, book stats |

## Summary

v1 derived no edge because it could not express the thesis. The Book
derives its edge from one corrected economic force (refiner hedging
pressure on a seasonally-crushed margin, long-only, 90d horizon) expressed
in five nearly-independent markets (two product cracks, cross-sectional
crush, natgas, crude basis), combined so that the diversification math,
not any single factor, produces the 2.63 Sharpe.

The single most important difference: v1 faded a 20-day artifact of the
wrong number. The Book buys a 90-day seasonal-margin stress in five
independent places and waits for the physical economy to fix it.