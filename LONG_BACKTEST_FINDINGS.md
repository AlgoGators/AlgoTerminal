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

---

# Round 2 — the gaps the 16y window surfaced, and the fixes (2026-09-10)

Same worktree, same data, same frozen IS parameters. The 16y window exposed
three structural problems in the factor-book engine that the 3y IS window
could not see. Each is a real gap, not a tuning change. The fixes raise the
honest OOS book Sharpe from 0.46 to 0.95 and cap OOS MaxDD near -11%.

Scripts: `book_oos_v4.py` (corrected engine + design space),
`book_oos_v3.py` (basis fix only), `validate_config.py`, `final_config.py`,
`control_test.py`, `debug_*.py` (diagnostics).

## G1 — the cross_sectional leg-switch phantom (the biggest gap)

F2 holds the single most-crushed leg of {crack_321, crack_gas, crack_ho}.
The three legs have completely different dollar scales (the gas crack is
~$7, the HO crack ~$27). The old return builder chained the chosen leg's
level into one series and measured P&L as position x d(series). When the
chosen leg switches, the series jumps from one leg's level to another and
the jump is booked as P&L.

Evidence:
- 2012-01-09: cross_sectional "return" -22.5%. Raw level moves that day
  were tiny (+0.3% max). The chosen leg switched from crack_ho (27.39) to
  crack_321 (18.96); the $8.4 gap was booked as a loss.
- 2007-12-20: -53% on the same mechanism.
- 2024-01-12: -43% in the IS window. Part of the recorded IS "edge" for F2
  was this artifact.
- The engine's circuit breaker also fired on the phantom jump, zeroing the
  position for the cooldown period (whipsaw).

Fix: F2 rebuilt per-leg. Position, return, hard stop, circuit breaker and
trade cost are per leg. A leg switch is a real exit + entry trade pair,
measured on each leg's own level and own base. Switches now pay real
turnover in the cost model.

Effect (v4 corrected engine, no gap cap):
- cross_sectional OOS Sharpe 0.59 (was 0.49 in the bugged honest table),
  OOS vol 40.7%. The phantom was noise in both directions.
- The true edge is a bit better, the vol is still enormous.

## G2 — sizing and return basis disagreed

The engine sized positions on rel = dlevel / level but priced returns as
dlevel / base (base = rolling mean |level|). Near zero-crossings the two
agree poorly. bzwti (BZ-CL) crosses zero 548 times in 2007-26, so its
"low vol" was partly an artifact of a small denominator, and inverse-vol
weights over-concentrated in it.

Fix: size and measure on the same basis (dlevel / base) everywhere.

The honest number: cross_sectional IS Sharpe drops from 1.02 (bugged
honest table) to 0.75 with the correct basis + per-leg fix. OOS 0.59.

## G3 — gap-day notional is uncapped

Positions run up to 1.0 notional. Real -20% level days become -18% book
days:
- 2019-09-03 (crack_321 -18.2%). Real event: RBOB crashed -8.9% that day.
- 2020-03-12 (crack_321 -14.7%, cross_sectional -13.8%). COVID.
- 2020-04-20 (bzwti -31.1%). Negative WTI.

Fix option: cap each factor's position so a 3-sigma level move loses at
most CAP3SIG of the book (CAP5 = 5%, CAP8 = 8%). This reduces raw OOS
MaxDD (CORE3 EQ: -29.8% -> -21.0% at CAP5) at a Sharpe cost (~0.71 -> 0.65
raw). Under the DD overlay the cap provides little extra; the overlay
already de-risks. Recommend the no-cap engine + overlay unless trading live
today with a hard gap constraint.

## Factor verdicts (corrected, net, 5bps/20roll)

| factor | IS Sh | OOS Sh | OOS MaxDD | OOS vol | daysOn OOS |
| --- | --- | --- | --- | --- | --- |
| crack_321 | 0.83 | 0.40 | -36.1% | 18.9% | 11.5% |
| crack_ho | 0.11 | -0.08 | -68.7% | 14.8% | 11.5% |
| cross_sectional | 0.75 | 0.59 | -67.7% | 40.7% | 38.8% |
| ng | 0.67 | 0.11 | -62.0% | 23.6% | 28.5% |
| bzwti | 1.53 | 0.25 | -41.8% | 16.5% | 52.1% |

Verdicts:
- crack_ho: no OOS edge. Drop. (-0.08, -68.7% DD.)
- ng: dead OOS (0.11). Drop from the book; its diversification did not pay.
- cross_sectional: real OOS edge (0.59) but at 40% vol with -68% DD. Kept
  in the book at equal weight; the DD overlay and book weight tame it.
- bzwti: the IS 1.53 -> OOS 0.25 collapse is real (the convergence edge
  was mostly a 2023-26 phenomenon). Kept small as an uncorrelated leg.
- crack_321: the core seasonal-crush thesis. Half IS strength OOS. Keep.

The subset that wins OOS is CORE3 = crack_321 + cross_sectional + bzwti.
Dropping the two dead factors raised OOS raw Sharpe from 0.58 (FULL HLV)
to 0.71 (CORE3).

## Why equal weights beat the IS-tuned inverse-vol weights

- EQ: IS Sh 1.31 / OOS Sh 0.71 (raw, CORE3)
- HLV: IS Sh 1.47 / OOS Sh 0.71
- INV: IS Sh 1.58 / OOS Sh 0.67

IS-tuned inverse-vol over-concentrates in bzwti because its near-zero-mean
vol looks small. Equal weight is OOS-robust and needs no IS information.
The per-factor signal parameters stay IS-frozen; only the outer book
weights are equalized.

## The DD overlay (v2)

Book-level de-lever. Hysteresis state machine keyed on the EXPERIENCED
equity drawdown:
- Full (1.0) -> Cautious (0.5) when experienced drawdown <= -6%
- Cautious -> Off (0.0) when experienced drawdown <= -10%
- Off/Cautious -> Full only when the underlying engine makes a new high
- Vol gear: min(1, 10% / trailing 20d vol)

All causal (state decided at close t-1, applied to day t).

The v1 overlay keyed on the engine's drawdown. That decoupled from the
experienced equity (the experienced dd reached -26.9% while the engine dd
was only -7% in 2011). v2 keys on the experienced equity; that is the fix.

## Recommended config (was: baseline)

CORE3 (crack_321 + cross_sectional + bzwti), equal weights, no gap cap,
DD overlay (cut -6%, halt -10%, re-cock on engine new high).

| window | CAGR | Sharpe | MaxDD | ann vol | worst day |
| --- | --- | --- | --- | --- | --- |
| IS (2023-09 -> 2026-09) | 7.26% | 1.13 | -10.25% | 6.4% | -2.32% |
| OOS (2007-07 -> 2023-09) | 6.27% | 0.95 | -11.14% | 6.6% | -2.85% |

Baseline (old pipeline, FULL inverse-vol, no overlay): OOS Sh 0.46, CAGR
4.0%, MaxDD -21.9% at 9.5% vol. The new config: double the OOS Sharpe,
halve the MaxDD, same order of CAGR, at 30% lower vol.

At 10% vol (reporting normalization, not a trading rule) the overlay line
scales to Sharpe 0.95 / MaxDD -16.4% / CAGR 9.4%. Better than the
baseline at its own vol. The honest framing: the strategy runs at ~6.5%
vol; its MaxDD is -11%. The "max 10% DD" target is met only at this
reduced vol level.

## What the overlay costs and why it is not overfit

- It sat out 2014-2016 (engine did not make new highs until 2017). Raw
  CAGR 11.1% -> 6.3%. The DD cap is not free.
- 2013 -23.1% raw becomes -6.2% overlaid. 2019 -15.3% becomes -0.9%.
- Worst OOS days: raw -12.2% (2019-09-03) -> overlay -2.85%. Single-day
  gaps are reduced by the vol gear, not eliminated.
- Negative control: shuffle the return series in time. The overlay Sharpe
  falls to 0.36 (raw 0.71) and DD only improves to -16.4%. On iid noise
  the overlay Sharpe collapses 0.54 -> 0.15. It exploits temporal
  drawdown clustering, not a mechanical artifact.
- Threshold sweep (cut -4 to -7.5%, halt -8 to -12%) is a plateau:
  Sharpe 0.88-0.95, DD -9.8% to -13.1%. Not a spike.

## 2013 and 2019 explained (per-factor, corrected)

2013: cross_sectional -57.9% (64.7% days on), crack_ho -32.2%, ng -7.9%,
bzwti -7.4%, crack_321 -3.9%. 2013 was a margin-compression regime: cheap
WTI, strong but stable cracks, then margin collapse. F2's reversion longs
bled through the year. With the DD overlay the book lost -6.2%, not -23%.

2019: crack_321 -27.2% and cross_sectional -27.5%; crack_ho +30.2% and
bzwti +8.6% masked them. A refining-margin compression year after the
2018 Q4 collapse. Same regime fragility, different legs.

Regime note: the seasonal-crush + cross-sectional book bleeds in
sustained margin-compression regimes (2013, 2019). The overlay converts
those bleeds into flat recovery years at the cost of some CAGR.

## Open gaps (still real)

1. Single-day gap risk is reduced but not bounded: a synchronized energy
   shock can still hit -3% in a day at 6.6% vol. Options overlay is still
   the genuine tail hedge (needs options data).
2. Trade counts are small for the core thesis: crack_321 ~11.5% days-on
   over 16y OOS, roughly 4-6 distinct entries per year. Multi-decade
   validation helps but the sample per regime is thin.
3. The overlay's "sat out 2014-2016" behavior is a policy choice, not a
   defect. If capital must be deployed, the medium-stickiness variant
   (re-enter at 0.5 when the engine recovers to -2% below high) caps DD
   at ~-10% with OOS Sh 0.93 and CAGR 5.6%.
4. No costs for leg switches inside F2 were modeled before; now they are
   (per-leg turnover). Real fills on crack switches should be checked
   against the 5bps assumption.
5. Dampen F2 at the engine level (its 40% OOS vol dominates the raw
   book's DD): the vt_f2 dimension moved little because the gap cap and
   overlay dominate; worth one more look if the overlay is removed.

## Artifacts (Round 2)

- `book_oos_v3.py` — G2 basis fix, v1 overlay, first design space.
- `book_oos_v4.py` — per-leg F2, G1+G2+G3, v2 overlay, full design space.
- `validate_config.py`, `final_config.py` — details and variants.
- `control_test.py` — negative control (shuffled / iid).
- `book_oos_v4_results.csv` — 72-row design-space table.
- `debug_*.py` — the diagnostics that found G1/G2/G3.
---

# Round 3 — honest assessment: why the edge is thin, what is still wrong

Date: 2026-09-10. Diagnostic pass over the current version. Script:
`diag_assessment.py`. Purpose: answer "where do the gaps hold, why is it
not extracting more edge, why is it not succeeding stronger?"

## The character of the edge (what the strategy actually is)

The 16y window shows the book is not a steady 0.9-Sharpe engine. It is a
crisis-reversion book with a slow bleed in normal regimes:

- 77% of the OOS total return (+187%) came from 5 of 16 years: 2008, 2020,
  2021, 2022, 2023. Only 2 years were negative: 2013 (-23.1%), 2019
  (-15.3%).
- 32% of the total OOS return came from the top-5 single days: 2020-04-20
  +21.1% (negative WTI), 2010-03-01 +13.8%, 2008-09-23 +10.5%.
- Rolling 3y Sharpe swings from -0.17 (2015) to +2.40 (2023). The average
  is positive; the variance across regimes is huge.

The edge is real but lumpy. The Sharpe is a thin average over a bimodal
regime distribution. That is the honest ceiling of this construction:
even in-sample the corrected raw book is 1.31, not the recorded 2.63.

## Why it is not extracting more edge

1. The signal is binary and slow. Entry at z < -0.75, exit at z >= -0.5.
   It does not size by crush depth, does not scale in or out, and uses no
   information beyond the price level. A deeper crush gets the same bet.
2. The cross-section is too narrow. F2 ranks 3 legs of one complex.
   Cross-sectional crush across complexes (Brent 3:2:1, Singapore
   distillates, jet, naphtha) would be genuinely independent and could
   raise the book Sharpe by real diversification. Current: 2 bets.
3. The diversification math is overstated. The recorded "max pairwise
   correlation 0.25, most 0.00-0.10" came from the buggy basis. Honest
   correlations: crack_321 vs cross_sectional 0.34 OOS (0.30 IS), cross
   vs bzwti -0.25 OOS. The book is really crack-complex long + crude-basis
   hedger, two independent bets, not five. The 2.63-compounding rationale
   in EDGE_RATIONALE.md does not survive the corrected basis.
4. Sizing is crude. The per-factor vol target is rarely active: MAX_LEV
   = 1.0 binds first. ng sits at the 1.0 cap 60% of its on-days, crack_ho
   39%, cross_sectional 26%. A 1.0-notional crack position turned a real
   -18% level day (2019-09-03) into an -18% book day. The engine is
   "full notional when the signal is on", not vol-targeted.
5. Regime blindness. There is no conditioning on energy vol, margin
   compression, or fundamentals. 2013 and 2019 are exactly the compression
   regimes a simple regime gate would avoid. The data infra in
   algoterminal-data (storage, weather, utilization) is unused.
6. The overlay caps the upside it was built to protect. The DD overlay
   de-risks during the exact regimes where the strategy makes its money.
   It sat flat on 2020-04-20 (raw +21.1%), 2018-07-23 (+7.5%), 2017-03-01
   (+7.2%). Of the top-5 day P&L (+60.2% raw), the overlay captured
   +13.1%. Net: Sharpe up (0.71 -> 0.95), CAGR down (11.1% -> 6.3%), and
   the 2020 windfall is mostly forgone. This is the hidden premium of the
   -10% DD cap.

## What is still wrong in the current version

1. Selection on OOS. CORE3 was chosen after seeing OOS. FULL EQ overlay
   is OOS Sh 0.75; CORE3 is 0.95. The 0.20 gap is selection gain. The
   honest post-selection expectation is ~0.75-0.8, not 0.95.
2. No true post-development data. Every year in the panel either tuned
   or selected the strategy. Real out-of-sample starts now. The "16y OOS"
   is pre-sample history, not a forward test.
3. Roll economics are unmodeled state. A fixed 20bps/yr drag ignores
   contango/backwardation. A long-biased book in backwardation earns the
   roll; in contango it bleeds. The synthetic back-adjusted series hides
   this P&L source.
4. Fills are optimistic. 5bps/side is thin in stress regimes, and the
   crack legs roll monthly at the front month with real bid-offer width.
   No official settlement prices; backtest uses yfinance closes.
5. The gap tail is reduced, not bounded. A synchronized energy shock can
   still cost -3% in a day at 6.6% vol. Options overlay is still open.
6. Regime samples are thin per episode. crack_321 makes ~90 trades over
   16y (~5.6/yr). The thesis rests on roughly a dozen crisis episodes.
   Multi-decade helps, but the per-regime evidence is narrow.

## What is NOT wrong

- The G1-G3 measurement fixes are solid and survive scrutiny.
- The overlay is validated by negative controls: shuffled returns destroy
  its benefit (0.71 -> 0.36), iid noise collapses it (0.54 -> 0.15). It
  exploits real drawdown clustering.
- Equal weights are robust; the honest correlations and the OOS evidence
  both reject IS-tuned inverse-vol weights.
- The seasonal-crush thesis has a real, positive, decade-long OOS edge.
  Thin, but it is edge, not overfit backtest noise.

## Where the next real gains are

1. Make the DD de-lever regime-aware. Keep participation through extreme
   crush episodes (the 2020 type), de-risk only in slow-bleed regimes
   (the 2013/2019 type). This attacks the single biggest cost: the
   overlay currently forgives the crisis windfalls that drive the edge.
2. Use the fundamentals the data infra already has as gating: storage
   direction, refinery utilization, weather, for the legs where they
   matter (cracks, NG). Gate, do not forecast. Strict OOS discipline.
3. Widen the cross-section across complexes. Genuine independence is the
   only free Sharpe.
4. Fix sizing at the engine: bind the vol target (lower MAX_LEV, or
   regime-scaled caps) so gap days are damped at the source and the
   kurtosis shrinks before the overlay has to eat it.
5. Correlation-aware weights with heavy shrinkage. With the honest matrix
   (0.34 / -0.25 / 0.02), a risk-parity book would not run crack-complex-
   heavy at 1/3-1/3-1/3.
6. Pre-register the next decisions. The only true test is forward. Write
   the rule now, run it on new data, do not tune on what you see.

## Artifacts (Round 3)

- `diag_assessment.py` — the diagnostics behind this section: saturation,
  concentration, rolling Sharpe, selection gap, overlay capture.
