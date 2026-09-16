# Multi-Factor Book — Findings & Assumption Ledger

Dev branch: `strategy-dev` (worktree `/home/sebas/algoterminal-strategy-dev`)
Data: 3y daily (2023-09-08 to 2026-09-08), yfinance CL=F BZ=F RB=F HO=F NG=F.
Stats below are post-warm-up (>= 2024-01-01); stats exclude the seasonal
warm-up period.

## The frame

Every factor is a bet on a set of assumptions. Fixing one gap (e.g. adding a
stop) creates new assumptions (the stop's distance is right for this
instrument's vol profile) that can break something else (a vol-clustered
instrument gets its trades cut). So the path to a deep edge is:

1. One factor per market/construction, few parameters, thesis-driven.
2. Each factor's assumptions written down explicitly (this ledger).
3. Combine factors whose correlations are near zero, so a failure of any
   one assumption is covered by the others.
4. Per-factor risk calibration — never a one-size-fits-all overlay.

## Factor map (final book)

| Factor | Instrument | Construction | Thesis | Sharpe | MaxDD |
| --- | --- | --- | --- | --- | --- |
| F1a | WTI 3:2:1 crack | seasonal crush, long | refiners cut runs when the crack is crushed vs its own seasonal norm | 1.29 | -5.8% |
| F1b | WTI heating crack | seasonal crush, long | same, heating-oil side (winter demand) | 1.16 | -17.4% |
| F2 | WTI complex | cross-sectional: long the single most-crushed of {3:2:1, gas, HO} | concentrate the reversion where it is strongest | 1.53 | -10.0% |
| F3 | Natgas | seasonal crush, long | winter-demand crush reversion in a different commodity | 1.23 | -14.7% |
| F4 | Brent-WTI | z-reversion of BZ-CL, both sides | crude geography convergence | 1.55 | -5.9% |
| **Book** | all of the above | inverse-vol weights | diversification of uncorrelated assumptions | **2.63** | **-3.9%** |

Combined book: CAGR 24.3%, Sharpe 2.63, MaxDD -3.88%, worst day -1.41%,
annualized book vol ~8%.

Correlations (daily returns, post-warm-up): max 0.25 (F1a vs F3); most
0.00-0.10. F2 and F4 are essentially orthogonal to everything.

## Assumption ledger (each factor's hidden assumptions + what covers them)

### F1 seasonal crush (WTI 3:2:1 + heating)
- Assumption: refiners' hedging pressure mean-reverts a seasonally crushed
  crack over ~2-4 weeks.
- Assumption: the trailing seasonal mean (expanding same-month) is a valid
  estimate of the "normal" level; requires >= 10 prior same-month obs.
- Weakness: only trades crush episodes (4.7-9.9% of days); the seasonal
  estimate is thin early in the sample; vulnerable to multi-week trend
  regimes (the 2024 first half).
- Covered by: F2 (concentrates when a crush is relative), F4 (uncorrelated
  geography), F3 (different commodity), plus per-leg vol scaling.

### F2 cross-sectional crush
- Assumption: "most crushed" is the strongest reversion candidate; holding
  one leg at a time captures more edge than holding all crushed legs.
- Weakness: it is winner-picking on the same 3y sample (in-sample risk);
  when ALL legs are stretched or none is crushed it is flat; concentration
  risk on a single leg.
- Covered by: the risk rules (hard stop + circuit breaker), the absolute
  crush floor (z < -0.5) so it is not forced into a position.

### F3 natgas seasonal crush
- Assumption: natgas winter-demand crush reverts like the crack complex but
  is a separate market (weather/storage driven).
- Weakness: extreme vol (79% annualized), gap risk on storage/weather news;
  needs its own risk calibration — the crack-tuned trailing stop destroys
  its edge (see "the trailing-stop lesson").
- Covered by: no trailing stop (circuit breaker + 20% hard stop only),
  small book weight, and low correlation with the complex.

### F4 Brent-WTI convergence
- Assumption: the WTI-Brent crude spread mean-reverts (geography/flow
  convergence); trades both directions.
- Weakness: weak economic story in an era of ample US exports; the edge is
  the thinnest per trade and it trades often (52% of days); hard stop can
  clip the mean reversion if the spread gaps.
- Covered by: small fixed vol budget (vt=0.15), no trailing stop, and large
  inverse-vol weight only because its vol is low — its per-trade edge is
  modest.

## The trailing-stop lesson (the philosophy made concrete)

The shared trailing stop (vol-distance, STOP_SIGMA=1.25) tuned implicitly
for the crack:
- crack legs: caps the 2024-09 deep drawdown (MaxDD -5.8% vs -26% without).
- NG: fires 41 times, cutting nearly every trade (Sharpe 1.16 -> -0.46).
- Brent-WTI: dropped from 1.55 -> 0.15.

Why: a fixed vol-distance stop assumes the instrument's short-window vol
equals its within-trade retracement range. NG and Brent-WTI have vol
clustering (weather, storage, flows) so normal retracements exceed 4 daily
vols; the crack does not. One-size-fits-all risk management is an
assumption that fails where it is not true. Per-factor stops are the fix,
and each per-factor choice is itself an assumption recorded here.

## What was tried and rejected (with reason)

- Momentum on the crack level (120-200d MA): no true edge — the crack's
  upward drift means "above MA" and "below MA" both go up (+0.7%/20d spread).
- CL momentum (long above 120d MA): Sharpe -0.16. No edge.
- Seasonal-phase calendar trade (long 321 in summer, short in winter):
  Sharpe -0.26 / -1.05. The seasonal LEVEL pattern does not survive
  year-to-year variance; loses badly.
- RB-HO relative-value z-reversion: fwd20 near zero. No edge.
- Gasoline crack as a standalone SMR leg: raw fwd20 +26% but traded Sharpe
  ~0.3 with deep drawdowns; dilutes the book. Kept only inside F2 where it
  is bought when it is THE most crushed.
- Brent 3:2:1 crack SMR leg: raw +17% fwd20 but traded Sharpe 0.09.
  Rejected; Brent enters the book only via the F4 crude-spread factor.
- Shared trailing stop across all factors: breaks NG/Brent-WTI. Rejected.

## Caveats (honest)

- 3 years is a small sample; 17 trades for F1, ~25-100 equity days for the
  others. All statistics are in-sample; parameters were picked from
  mid-plateau values, not peaks, but selection still exists.
- The inverse-vol weights in the combined book are computed in-sample.
- No costs, slippage, or futures roll modeling.
- The seasonal mean (SEASON_MIN_OBS=10) is thin early; longer history would
  harden it.
- The combined Sharpe 2.63 is a backtest artifact risk until confirmed on
  out-of-sample / 10y data. Do not size to it yet.

## Next steps (recommended)

1. 10y data (2016-2026) to re-validate all five factors and the book,
   including the 2016, 2018, 2020, 2022 regimes (COVID crash, negative
   WTI, refinery outages, Ukraine invasion).
2. Transaction cost / roll model: crack legs roll monthly; BZ-CL and NG
   have own rolls; realistic costs will shave the Sharpe.
3. Options: a put on the crack complex (or short product call spreads) as
   the genuine instant-gap hedge the user's notes call for. Needs options
   data (not in the current harness).
4. Portfolio-level tail overlay: the book's worst day is -1.41% in-sample,
   but a synchronized gap across factors (a global energy shock) is the
   residual risk; consider a book-level vol cap / drawdown de-lever rule.