# Long Backtest — Findings (16y Out-of-Sample, Real Costs)

Date: 2026-09-09. Worktree: `/home/sebas/algoterminal-strategy-dev` (branch
`strategy-dev`).

Data: yfinance continuous futures, back-adjusted closes, 2007-07-02 to
2026-09-09 (4829 rows). CL=F, BZ=F, RB=F, HO=F, NG=F. Same tickers and
construction as the recorded research.

Method: frozen factor_book.py parameters. No re-tuning. Full-panel single
pass (all windows causal). Return basis fixed (see bug below). Book weights
frozen from the IS window, applied to OOS (walk-forward). Costs: 5 bps per
side on traded notional + 20 bps/yr roll drag (sensitivity shown).

## 1. A measurement bug in the recorded pipeline (found by the 16y test)

factor_book.py prices PnL as `pos * level.pct_change()`. That explodes when
a spread level crosses zero:

- BZ-WTI crosses zero 548 times in 2007-2026 (it is a differential that
  legitimately goes both positive and negative).
- crack_gas crosses zero 60 times; crack_321 once (2008-09-23).
- `pct_change` near zero produced single-day returns of +12006%, +inf in
  this window. The "worst OOS day" of my first run (-50% on 2007-12-12) was
  pure artifact (level went from +$0.18 to -$0.37).

Why the recorded 3y window never exposed it: in 2023-2026 BZ-WTI stayed
positive (roughly +$3-6), so `pct_change` was finite and plausible. The
bug is invisible in-sample and fatal out-of-sample.

Fix used here: spread-relative return
`ret = pos.shift(1) * diff(level) / base.shift(1)` where
`base = rolling mean(|level|)` — the exact denominator the size math uses.
This is the internally consistent measure of the intended risk, is finite
near zero, and equals `pct_change` when the level is positive and stable.
The strategy module itself is unchanged; only the PnL measurement changed.

## 2. The recorded IS numbers reproduce as-is (2.63), and the honest IS is 1.69

`python factor_book.py --start 2023-09-08` reproduces the recorded table
exactly: per-factor Sharpes 1.29 / 1.15 / 1.53 / 1.23 / 1.55, book Sharpe
2.63, MaxDD -3.88%, book vol 8%. So the published numbers are not a
fabrication — they are reproducible on the raw pipeline.

But that pipeline contains three in-sample selection biases:
1. `pct_change` basis: during crush episodes the level is below its rolling
   mean, so `diff/level_prev` > `diff/mean|level|`, inflating reversion
   returns in a mostly-up 3y tape.
2. Inverse-vol weights computed on the same post-warm-up sample they are
   evaluated on (lookahead weighting).
3. No costs, no roll model.

Measured honestly (corrected basis + costs + frozen weights), the same IS
window gives book Sharpe 1.69, not 2.63.

## 3. Out-of-sample result: the edge survives but at ~27% of IS strength

IS window (2023-09 -> 2026-09, tuning window):

| factor | CAGR | Sharpe | MaxDD | annVol |
| --- | --- | --- | --- | --- |
| crack_321 | 11.25% | 0.83 | -16.5% | 14.0% |
| crack_ho | 0.43% | 0.11 | -40.8% | 17.0% |
| cross_sectional | 47.2% | 1.02 | -46.1% | 48.0% |
| ng | 17.5% | 0.67 | -29.7% | 31.3% |
| bzwti | 25.0% | 1.53 | -5.9% | 15.4% |
| BOOK (IS-frozen weights) | 17.7% | 1.69 | -13.5% | 9.9% |

OOS window (2007-07 -> 2023-09, ~16y):

| factor | CAGR | Sharpe | MaxDD | annVol |
| --- | --- | --- | --- | --- |
| crack_321 | 5.9% | 0.40 | -36.1% | 18.9% |
| crack_ho | -2.3% | -0.08 | -68.7% | 14.8% |
| cross_sectional | 10.0% | 0.49 | -58.5% | 25.7% |
| ng | -0.1% | 0.11 | -62.0% | 23.6% |
| bzwti | 2.7% | 0.25 | -41.9% | 16.5% |
| BOOK (IS-frozen weights) | 4.0% | 0.46 | -21.9% | 9.5% |

Book: IS Sharpe 1.69 -> OOS Sharpe 0.46. Positive, real, but weak. At ~10%
book vol the OOS CAGR is ~4% with a -22% drawdown. Not capital-grade.

## 4. What this says per factor

- crack_321 (F1a): the core seasonal-crush thesis holds OOS (0.83 -> 0.40).
  Real edge, half strength.
- crack_ho (F1b): no OOS edge (0.11 -> -0.08). Add nothing; -69% max DD.
- cross_sectional (F2): positive OOS (1.02 -> 0.49) but at 48% IS / 26% OOS
  annualized vol with deep DDs. Its IS charm came partly from its vol.
- ng (F3): basically dead OOS (0.67 -> 0.11).
- bzwti (F4): the biggest IS number (1.53) is the biggest OOS drop (0.25).
  The Brent-WTI convergence edge was largely a 2023-26 phenomenon (and its
  pct_change basis flattered it in IS).

## 5. Anti-overfit evidence (good news)

- Equal-weight book (zero IS information): OOS Sharpe 0.51 vs frozen
  inverse-vol 0.46. The tuned weights do NOT beat simple equal weights
  OOS. Either diversification works or the IS weights are noise — in
  either case, equal-weight is the defensible choice.
- Parameter sweep on OOS: frozen picks sit on a plateau, not a spike.
  SMR_Z_LOOKBACK 90 = 0.46 (60->0.31, 120->0.39, 150->0.33, 180->0.23);
  SMR_ENTRY 0.5-1.25 flat 0.40-0.46; F4_ENTRY flat; VT_F2/F3 flat.
- Costs: OOS Sharpe 0.50 (0) -> 0.46 (5bps/20roll) -> 0.42 (10/20) ->
  0.35 (20/40). Costs nibble, they do not kill the edge.
- OOS correlations are higher than IS (cross_sectional vs crack legs
  0.22-0.23 OOS vs 0.08-0.09 IS) — diversification is weaker than the
  3y sample suggested.

## 6. Worst OOS days are real events, not artifacts

2020-04-20 (-7.0% book, the negative-WTI day), 2020-03-12 (-5.2%, COVID
crash), 2019-09-03 (-5.1%), 2013-04 (-3.9%), 2015-10 (-3.4%). The 2007-12-12
-50% phantom from the buggy basis is gone. Tail is honest: worst OOS day
is ~4x the worst IS day.

## 7. Verdict

The seasonal-crush thesis has a real but thin out-of-sample edge. The
book's honest expectation is Sharpe ~0.4-0.5 at ~10% book vol with -20%
drawdowns, not the recorded 2.63. Most of the recorded edge was window +
measurement + weighting selection.

Do NOT size capital to the recorded numbers. Recommended next steps:
1. Drop crack_ho (no OOS edge) and possibly ng; test a 2-3 factor book
   (crack_321 + cross_sectional + small bzwti) on OOS.
2. Explain 2013 (-31% year) before trusting any version.
3. Book-level vol cap / de-lever rule (still open from earlier notes).
4. Options overlay for the instant-gap tail (2020-04-20 type day) —
   still needs options data.
5. If it must trade now, use equal weights, corrected basis, and assume
   ~0.4-0.5 book Sharpe.

## 8. Artifacts

- `long_backtest.py` — the honest 16y backtest (corrected basis, frozen
  weights, costs, yearly, tails, cost sensitivity, param sweep).
- `check_artifact.py` — zero-crossing artifact detector.
- Data cache: `/tmp/panel_adj_2007_2026.parquet`.