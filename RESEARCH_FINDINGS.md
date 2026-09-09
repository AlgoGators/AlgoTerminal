# Crack Spread Mean Reversion — Research Findings

Dev branch: `strategy-dev` (worktree: `/home/sebas/algoterminal-strategy-dev`)
Data: 3 years daily (2023-09-08 to 2026-09-08) via yfinance, CL=F / RB=F / HO=F.

## 1. The strategy as recorded had never traded the real crack spread

Two compounding bugs meant the recorded backtest (CAGR -5.9%, Sharpe -0.54)
was meaningless:

1. **Engine plumbing.** `run_backtest` passed only `data[primary]["close"]`
   (CL raw price) to the strategy as a single series. `_crack_spread`
   passes a single series through unchanged, so the strategy was
   mean-reverting CL's raw price — exactly what its own docstring warns
   "does not express the thesis and will not work."
2. **Unit mismatch in crack construction.** RB and HO futures are quoted in
   USD/gallon; CL is USD/barrel (1 barrel = 42 gallons). The strategy
   computed `(2*RB + HO)/3 - CL`, a unit-mismatched number that sits around
   -70. The real per-barrel 3:2:1 crack is `(2*RB + HO)/3 * 42 - CL` and
   sits around +18 to +30.
3. **Data gap.** HO had 0 rows because yfinance needs `HO=F`, not `HO`.
   RB only had ~15 months.

## 2. The edge, honestly measured

On the correct crack spread, the mean-reversion edge is:

- **Not at short lookbacks.** A 20-day z-score fade has no edge (in-sample
  forwards are flat-to-positive after a stretch — momentum, not reversion).
- **Long and asymmetric.** At a 120d z-score, buying a crushed crack
  (z < -1.5) reverts **+7.1%** over 20 days; fading a stretched crack
  (z > +1.5) has **no reliable edge** and lost badly in the first-half
  uptrend (+18.7% adverse). The short side is dead — exclude it.
- **Seasonality is the real signal.** The crack has a strong annual cycle
  (summer driving season ~38, winter ~21). Defining "crushed" as the
  deseasonalized z-score (vs. the trailing same-calendar-month mean) lifts
  the 20-day forward return to **+12-15%** across lookbacks 60-180d.
- **No bleedout on the seasonal signal.** Forward returns are positive from
  day 1 (+0.8% fwd1, +5.1% fwd10, +15.4% fwd20). The raw-z version bled
  first (its -0.5% fwd5) — one reason the seasonal version is better.

Tuning caution: the edge surface is in-sample. Picks were taken from the
middle of stable plateaus (Z_LOOKBACK=90, Z_ENTRY=0.75), not peaks, to
limit overfit. Only 3 years of data; the seasonal estimate has few
same-month observations early (SEASON_MIN_OBS=10).

## 3. Tail events

- **In-sample there are no catastrophic tail hits.** Worst single day
  is -2.87%; the circuit breaker never triggers; the largest crack moves
  (a 10.4-point / ~7σ gap on 2026-09-01) happened while the strategy was
  flat.
- **The real tail is out-of-sample.** A 7σ adverse gap while long at 0.6
  size would be about -22% in a day. The circuit breaker flattens at close,
  after the gap — it does not prevent the loss.
- **Every overlay that bites in-sample costs edge.** Tighter circuit
  breakers (1.5-2.5σ), a crude-spike filter (CL up >3-8% in 3-10d), and a
  4% hard stop all reduced CAGR/Sharpe without improving worst-day or
  MaxDD. A 6% hard stop on the crack level is only ~1.1 daily vols wide —
  it cuts winners.
- **Free insurance:** a hard stop at ~20% of the entry level (≈4 daily
  vols) never triggers in-sample but caps the catastrophic per-trade loss
  out-of-sample. Kept in v4.
- **Sizing coupling discovered:** the circuit breaker's trigger depends on
  position size (`position × crack_σ ≤ -3`), so changing the vol target
  changes when it fires. Keep risk rules on the target-size positions, not
  pre-downscaled ones.

## 4. Diversification (the "naturally more diversified hedge")

- Gasoline crack (RB-CL) and heating crack (HO-CL) daily returns are
  **nearly uncorrelated (0.11)** — different demand seasons and refinery
  dynamics.
- Leg edges (seasonal crush, buy when z < -0.75 vs 90d): gasoline +26%
  fwd20, Brent 3:2:1 +17%, WTI 3:2:1 +16%, heating +12%.
- But the gas leg's *traded* profile is poor (Sharpe ~0.3, deep drawdowns)
  — its raw edge does not survive the pipeline, and adding it dilutes the
  book (all-3 equal: Sharpe 1.18; 4:4:2 weights: 1.34).
- **Best book: WTI 3:2:1 + heating oil, equal weight.** Two Sharpe-1+
  uncorrelated legs (corr 0.19).

## 5. Results (2023-09 to 2026-09)

| Version | Setup | CAGR | Sharpe | MaxDD | Trades |
| --- | --- | --- | --- | --- | --- |
| v1 | as-recorded (CL series) | -5.9% | -0.54 | -18.7% | 141 |
| v1 | real crack, 20d z (fixed units) | -4.7% | -0.60 | -15.4% | 13 |
| v3 | seasonal z, single leg, vt=0.5 | 11.2% | 1.25 | -6.0% | 8 |
| v4 | 2-leg book, vt=0.5/leg | 28.8% | 1.44 | -18.9% | 17 |

v4 at per-leg vt=0.5 runs ~2x a single leg's vol; scale VOL_TARGET down
for lower total risk (Sharpe is scale-invariant, MaxDD scales with vol).

## 6. What is NOT yet done / honest caveats

- **Small sample.** 17 trades in 3 years. The profile is fragile; both
  halves are positive (first +, second strongly +) but the first half is
  weak evidence for the seasonal z (short seasonal history).
- **No out-of-sample / walk-forward test.** The seasonal mean uses an
  expanding same-month mean (no lookahead), but the tuning (lookback,
  thresholds, legs) was chosen on the same sample. Needs a holdout period
  or longer history (10y) to confirm.
- **Options.** The user's notes mention options for instant-gap hedging.
  Crack-spread options exist on NYMEX; the harness has no options data.
  Recommend a separate study.
- **Costs/funding.** No transaction costs, slippage, or futures roll
  costs modeled. Daily bar fills assumed.
- **Porting.** The tool's engine passes a single Series and computes
  returns as `position × primary.pct_change()`. v4 needs the engine to
  either pass the panel or a per-leg contract (see harness `run_strategy`).

## 7. Files

- `harness.py` — standalone research harness (fetch panel, build legs,
  run strategy, per-leg PnL, stats, trade summary, tail scan).
- `strategy.py` — v1 baseline (unit fix applied).
- `strategy_v2.py` — long-lookback z, long-biased (intermediate).
- `strategy_v3.py` — seasonal z, long-only, single-leg reference.
- `strategy_v4.py` — the deliverable: 3:2:1 + heating book, seasonal
  long-only signal, per-leg vol targeting, trailing stop + circuit
  breaker + 20% tail cap + cooldown.