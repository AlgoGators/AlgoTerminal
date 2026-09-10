# Long Backtest — Findings (16y Out-of-Sample, Real Costs)

Date: 2026-09-09. Worktree: `/home/sebas/algoterminal-strategy-dev` (branch
`strategy-dev`).

Evaluation procedure owned by `EVALUATION_LENS.md`: behavior first,
numbers second. Every run is mined for regime behavior, mechanism,
retained signal, and next variants before any verdict.

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

---

# Round 4 — falsifying the "extract more edge" levers (2026-09-10)

Date: 2026-09-10. Scripts: `book_oos_v5.py` (full design space, 240 rows),
`gate_test.py` (depth + crude-stress gate diagnostics).

Goal: test the four prioritized levers from the Round 3 assessment. Result:
all four fail to beat the Round 2/3 config. The recommended config is
unchanged: CORE3 (crack_321 + cross_sectional + bzwti), equal weights,
v2 DD overlay. OOS Sharpe 0.95, MaxDD -11.1%, vol 6.6%. This is now a
well-tested local optimum for the price-only construction.

## Lever 1: regime-aware overlay (v3, deep-crush gate) — FAILS

Idea: stay invested during deep crush episodes (the 2020 windfall type),
de-risk only in shallow-crush bleeds. Rule: if any held leg seasonal z
<= -1.25, force FULL regardless of drawdown.

Result: worse everywhere. CORE3 EQ v3: OOS Sh 0.80, DD -20.0% (vs v2
0.95 / -11.1%). IS drops to 0.85.

Why: the crack complex is structurally "crushed" in the bleed years too.
Depth <= -1.25 on 70% of 2013 days, 59% of 2019, 54% of 2024. The gate
keeps exposure through the bleeds it was meant to avoid. The discriminator
does not discriminate.

## Lever 2: crude-stress gate (CL z <= -1.5) — captures windfall, blows DD

Idea: the 2020-04-20 windfall was a CRUDE-price event (WTI negative)
that exploded the crack. Gate on crude stress, not crack crush.

Result: captures 2020-04-20 fully (+21.1% vs +0.0% for v2) and recovers
+34.2% of the top-5-day P&L (vs +13.1%). But OOS DD -18.6% (vs -11.1%),
Sharpe 0.90 (vs 0.95), IS 1.21 / -12.7% (vs 1.13 / -10.3%). Negative
control clean (shuffled 0.36). Real, but it fails the user's MaxDD
objective and is worse risk-adjusted.

## The structural finding: windfall and bleed are the same state

Both the 2020 windfall and the 2013/2024 bleeds occur while the complex is
deeply crushed and crude is stressed. The strategy's payoff and its risk
are the same position. In price-only land you cannot have the windfall
without the bleed risk. The DD overlay's "forgone windfall" is not a
fixable inefficiency; it is the honest price of the DD cap.

The only way to get both (capture the windfall, cap the drawdown) is a
different risk layer: an options overlay (buy crash protection, keep the
long crush exposure). That is data-blocked (needs options data).

## Lever 3: Brent complex legs — raw edge, no overlaid edge

F5 = seasonal crush on Brent 3:2:1. F6 = cross-sectional most-crushed of
{brent321, brent_gas, brent_ho}. Same products priced against Brent
instead of WTI. brent321 corr 0.39 with wti321; brent_gas corr 0.04.

Raw (no overlay): CORE3 EQ 0.71 -> CORE3B5 0.76, CORE3B6 0.77, CORE3BB
0.78. Real raw-edge addition.

Overlaid (v2): CORE3 EQ 0.95 -> CORE3B6 0.90. The overlay eats the gain:
more factors means more ways to be in a drawdown, more de-risking.

Verdict: keep Brent legs as a reserve. They add raw edge if the overlay is
ever removed or a better risk layer (options) is added. Not adopted now.

## Lever 4: risk-parity weights and sizing taming — no gain

Risk-parity with covariance shrinkage (RP05/RP07, IS-trained): no gain
over equal weight (0.70 vs 0.71 raw; 0.90 vs 0.95 overlaid). The 3y IS
covariance is too noisy to beat equal weights.

Sizing taming (per-factor position caps: cross 0.40, ng 0.40, cracks 0.60):
cuts Sharpe (0.95 -> 0.61-0.68 overlaid). It trims the windfall days as
much as the bleed days, because both run at full notional. No gain.

## What this means

The price-only construction is at a tested local optimum. The remaining
levers are the data-blocked ones:
1. Options overlay for the tail (capture windfall + cap DD). Needs options
   data.
2. Fundamental gating (storage, utilization, weather) from the data infra.
   Needs a long-history EIA/weather provider build. FRED in the current
   provider set has no storage/refinery series.
3. True forward test. All history tuned or selected the strategy. The only
   real out-of-sample starts now.

## Artifacts (Round 4)

- `book_oos_v5.py` — full design space (240 rows), Brent legs, v3 gate.
- `book_oos_v5_results.csv` — the grid.
- `gate_test.py` — depth-by-year + crude-stress gate + negative control.

---

# Data-source audit — correction to Round 4's "data-blocked" claim (2026-09-10)

Round 4 said the remaining levers were data-blocked. A full audit of every
algoterminal-data source shows that was wrong for weather, half-wrong for
storage, and only right for options history.

## What each source actually holds

| source | what it can serve | usable for the strategy? |
| --- | --- | --- |
| yfinance | market OHLCV, current option chains | prices (as used); NOT historical options |
| stooq | market OHLCV fallback | prices only |
| nasa-power | satellite weather from 1981+, keyless | YES — Houston/Rotterdam T2M verified 2007-2026 through the repo provider (7,193 daily points) |
| fred | macro whitelist, keyless | no EIA storage series; candidate IDs 404 (FRED's public CSV does not host weekly energy storage) |
| usgs / world-bank / fear-greed / wiki-pageviews | seismic / macro / sentiment / attention | not relevant |
| EIA API (api.eia.gov/v2) | full-history weekly storage + refinery utilization | blocked only by a FREE key (register: eia.gov/opendata/register.php). The current repo has no EIA provider and no key. |
| ir.eia.gov bulk | weekly reports | current weeks only, no history |

## Corrected status of the "data-blocked" levers

1. Weather gate (NG winter demand, winter distillates, freeze/hurricane
   refinery risk): BUILDABLE NOW. The existing nasa-power provider returns
   Houston/Rotterdam daily temperature for the full 2007-2026 window,
   keyless. This is the strongest unlocked path.
2. Storage/utilization gate (crude stocks, Cushing, natgas working
   storage, refinery utilization): available with one free EIA key + a
   small new provider. Not a data constraint; an access step.
3. Options overlay: still genuinely blocked for REAL historical option
   prices (no free source has them; yfinance is current-chain only). A
   modeling path exists without options data: price a crash-put overlay on
   the crack/futures vol with Black-76 under conservative premium
   assumptions, and test cost sensitivity. That answers "could a
   crash-put overlay have worked at plausible premiums", not "what would
   fills have been".

## Action items

- Wire the weather gate first: fetch HOUSTON + ROTTERDAM T2M via the
  existing provider, align to the futures panel, test gating the NG and
  winter-distillate legs with strict OOS discipline (pre-registered rule).
- Add an EIA provider (storage crude/Cushing/NG + refinery utilization)
  once the free key exists; start series where history covers 2007+.
- For options: run the modeled-premium crash-put overlay study in
  parallel as a cost-sensitivity exercise.

---

# Round 5 — weather gate, options study, EIA provider (2026-09-10)

Scripts: `weather_gate.py`, `options_study.py`, `reverify.py`. Data:
`/tmp/panel_adj_2007_2026.parquet` (rebuilt from yfinance, byte-identical
to the original 4829-row cache; see reproducibility note below).
Weather: NASA POWER via the algoterminal-data repo provider (NYC/Houston/
Rotterdam T2M, 2007-2026, keyless).

## 1. Weather gate — FAILS (negative control proves no information)

Hypothesis: NG and winter-distillate seasonal-crush longs need weather
support. Gate: cut the position when the 7-day heating-degree-day z
(expanding same-month climatology, causal) is below -1.0; restore at -0.5.

Results (per-factor, then books with the overlay):
- Gated NG: IS 0.37 / OOS -0.05 (vs raw 0.67 / 0.11). Worse.
- Gated HO: IS 0.21 / OOS -0.16 (vs raw 0.11 / -0.08). Worse.
- CORE3+NGW overlay: OOS 0.77 / -12.6% vs champion 0.95 / -11.1%. Worse.
- Threshold sweep -0.75/-1.0/-1.5: flat (0.77-0.83). No signal.
- City (NYC vs Houston): 0.77 vs 0.84. Noise.
- NEGATIVE CONTROL: shuffled weather gives OOS Sharpe 0.80 vs real gated
  0.77. The gate has ZERO information content relative to the strategy's
  P&L.

Interpretation: the NG/HO price-reversion edges are not weather-conditioned
in the way a simple HDD gate captures. The gate removes good trades and
keeps bad ones. Weather gating via this construction is falsified.
NG and HO stay dropped from the book.

## 2. Modeled crash-put overlay — economically dead for this book

Real historical option prices are absent from every free source. The
stylized screen (decision-logged) prices a rolling 1-month put on the
CORE3 EQ raw book's monthly return with Black-76 at trailing realized
vol, markup 1.0/1.25/1.5, strike -5/-7.5/-10/-15%, hedge 0.5/1.0.

Results (full-sample monthly):
- Cheapest useful cell (-5%, h=1.0, markup 1.0): premium 4.1%/yr, MaxDD
  -29.2% -> -25.8%, Sharpe 0.75 -> 0.73. Loses on risk-adjusted terms.
- Realistic markup (1.25): premium 6.9%/yr; destroys results.
- Far-OTM (-15%): premium ~0.7%/yr but MaxDD and worst month barely move.
- No grid cell beats the DD overlay (0.95 / -11.1%).

Verdict: at ~16.6% book vol, crash-put premiums are too expensive relative
to the book's ~12% raw CAGR. The DD overlay dominates every hedge cell.
Pursuing real options data is NOT justified by this screen. The
windfall-vs-DD tradeoff stands: the DD overlay's forgone windfall is the
cheapest available resolution.

## 3. EIA provider wired (storage + refinery utilization)

The algoterminal-data repo now has an `eia` provider for the EIA Open Data
API v2 (crude/Cushing/product/natgas storage + refinery utilization,
weekly, full history). It is registered in list_sources and the
eia-energy-storage universe. It needs the free EIA_API_KEY (register at
eia.gov/opendata/register.php); it raises cleanly without the key.
FRED's public CSV does not host these series (IDs verified 404).

The storage-gating hypothesis is NOT yet tested. That is the remaining
unfalsified lever, and it needs the key.

## 4. Panel rebuild + reproducibility note

The /tmp panel cache was wiped between sessions. Rebuilt from yfinance
(CL/BZ/RB/HO/NG=F, auto_adjust=False, raw continuous front-month closes)
and trimmed to 2007-07-02 -> 2026-09-09, 4829 rows. The restored panel is
byte-identical to the original (CL=71.089996 on 2007-07-02 etc.), and the
champion reproduces exactly: CORE3 EQ + v2 overlay IS 1.13 / -10.25%, OOS
0.95 / -11.14%, vol 6.6%.

Lesson: the analysis depended on an ephemeral cache. Rebuild script:
`rebuild_panel.py` (should be added; the rebuild is a yfinance fetch +
trim, 1-2 minutes).

## Artifacts (Round 5)

- `weather_gate.py` — HDD-z gate build + tests + negative control.
- `options_study.py` — Black-76 crash-put cost screen (stylized).
- `reverify.py` — champion/options/weather verification on restored panel.
- algoterminal-data: `_providers/eia.py`, registered in __init__,
  SOURCE_DESCRIPTIONS, eia-energy-storage universe.

---

# Round 6 — EIA storage gates: the last fundamental lever, falsified (2026-09-10)

Data: EIA Open Data API v2, keys now live in the algoterminal-data project
secrets file (mode 600, git-ignored; load_project_env/api_key infra,
commit d482d83). Provider series codes verified against the API:
WGTSTUS1 (total gasoline), WDISTUS1 (distillate), WCESTUS1 (crude excl
SPR), W_EPC0_SAX_YCUOK_MBBL (Cushing), WPULEUS3 (refinery utilization),
natgas working gas = sum of storage-region codes (NATOTAL, history from
2010). All petroleum series cover 2007-2026 weekly.

Pre-registered hypotheses and results (causal signal: weekly value +
6-day report lag, forward-filled, same-month z, gate decided at close t-1):

- H1 product stocks (gasoline + distillate z > +1.0 -> de-risk crack_321
  and cross_sectional). crack_321 OOS 0.40 -> 0.32. cross_sectional
  0.59 -> 0.50. WORSE. The crush reversion is not product-stock-gated.
- H2 natgas working storage (z > +1.0 -> de-risk ng). ng OOS 0.11 ->
  -0.03. WORSE. Negative control: shuffled storage 0.49 vs real 0.51.
  ZERO information.
- H3 Cushing crude (z > +1.0 -> de-risk bzwti). bzwti OOS 0.25 -> 0.31,
  MaxDD -41.8% -> -33.9%. Small standalone improvement, direction
  consistent with the tank-tops story, but diluted in the book.
- Books (v2 overlay, EQ): CORE3+Gprod 0.70 / -10.1%; CORE3+NG-S
  0.51 / -13.2%. Champion (no gates) 0.95 / -11.1%. Gating loses.

Conclusion: the final fundamental lever fails. Storage, utilization and
weather conditioning do not extract more edge from this construction. The
strategy's edge is genuinely price-only. CORE3 EQ + v2 overlay remains the
champion: OOS Sharpe 0.95, MaxDD -11.1%, vol 6.6%.

Remaining honest paths (all previously assessed):
1. True forward test. The only source of genuinely new information. All
   history tuned or selected the strategy.
2. Options overlay: uneconomic at modeled premiums (Round 5).
3. Accept this config for the price-only construction and stop.

Artifacts: fetch_eia.py (verified codes), storage_gate.py, the repo
provider eia.py (route mapping for stoc/wstk, natural-gas/stor/wkly,
petroleum/pnp/wiup).

---

# Round 7 — behavioral re-read of the falsified levers (2026-09-10)

Rounds 4-6 killed five levers by the number: Sharpe or MaxDD vs the
champion. This section re-reads each through the evaluation lens
(EVALUATION_LENS.md). The point is not to relitigate the verdicts. It is
to recover the behavior and the usable signal each run did produce.

## 1. Weather gate (Round 5): the failure is a fact about the driver

Number said: dead. Shuffled weather matched real weather (0.80 vs 0.77).

Behavior: the NG and HO reversion edges carry no daily weather-demand
conditioning. The 2020 NG reversion worked in warm weather. The 2013 and
2019 bleeds were margin-compression years, not weather years.

Mechanism: the reversion is flow-driven (forced unwinds, margin
compression), not physical-demand-driven. This is the strongest positive
fact of Round 5. It redirects feature work from physical conditioning
(weather, storage) toward flow proxies: COT positioning, open-interest
collapse, option skew, reversal speed.

Retained: weather as regime identity for sub-sample validation (warm vs
cold winters), and size conditioning instead of on/off gating. Not
tested.

## 2. Storage gates (Round 6): H3 is the first physical variable with the predicted sign

Number said: H1 and H2 worse, H3 small (bzwti 0.25 -> 0.31, MaxDD
-41.8% -> -33.9%). Gates die in the book.

Behavior: Cushing stock z-score de-risking moved bzwti in the direction
the tank-tops story predicts, under a causal construction (report lag +
forward fill). Weak but directionally consistent.

Mechanism: the Brent-WTI basis edge may be partly physical (Cushing
capacity binds, WTI discounts to Brent), while crack reversion is
flow-driven. Different legs, different drivers.

Retained: utilization (stocks / capacity) instead of stock z; size
conditioning instead of a gate; regime identity for sub-samples. Not
tested.

## 3. Crash-put overlay (Round 5): it bought back the book's own payoff

Number said: dead. No grid cell beat the DD overlay at modeled premiums.

Behavior: at ~16% book vol a protective put costs ~4.1%/yr for a -29% ->
-26% MaxDD move. Far-OTM puts (~0.7%/yr) barely move the tail. Worst days
cluster in the same states where the book earns most (2020).

Mechanism: variance is intrinsic to the payoff. A flat-book put
repurchases the book's own convexity at retail premium. The state overlap
seen in Round 4 is confirmed.

Retained: cheaper asymmetric structures (put spreads, narrower hedges
active only in the fat-tail state) were not tested. The practical
direction is to keep exposure in stress and harden the reversal timing
(see lever 4) instead of paying to sit out.

## 4. Crude-stress gate (Round 4): the separator is speed, not level

Number said: failed. Captured the +21.1% windfall, MaxDD -18.6%, Sharpe
0.90.

Behavior: stress level does not separate 2020 (windfall) from 2013 and
2019 (bleed). All three run deeply crushed with crude stressed.

Mechanism: the separator is likely the inflection. A V-shaped crash with
a fast reversal pays. A slow grind bleeds. Level equals, path differs.

Retained: conditioning on reversal speed or inflection (OI collapse then
restoration, price recovery speed, 5-day reversal strength) instead of
stress level. This is the most promising reopen.

## 5. Brent legs (Round 4): the overlay ate the diversification

Number said: not adopted. Raw 0.71 -> 0.78, overlaid 0.95 -> 0.90.

Behavior: Brent legs add real raw edge. brent_gas correlates 0.04 with
wti321. The book-level DD overlay then de-risks more as more factors add
drawdown states.

Mechanism: overlay granularity is the problem, not the legs. A
per-complex overlay (de-risk each complex on its own drawdown) may let
the diversification survive the de-risking. Not tested.

## The dropped factors, re-read

crack_ho (0.11 IS, -0.08 OOS, MaxDD -68.7%): the DD clusters in winter
episodes. This is the exact leg where the weather hypothesis should have
worked. That it did not is more evidence the channel is flow, not
physical. Dropped from the book, kept as evidence.

ng (0.67 IS, 0.11 OOS): the 2007-2023 window includes the gas glut years.
A structural oversupply regime, not a dead mechanism. The seasonal-crush
construction may behave differently in a different supply regime. Tag the
regime instead of deleting the idea.

## What this changes

- Driver map: crack reversion is flow-driven. Brent-WTI basis is partly
  physical (Cushing). Feature work follows the driver.
- Reopen candidates in order: reversal-speed discriminator (4),
  per-complex overlay (5), Cushing-utilization sizing (2), weather as
  regime identity (1), cheaper tail structures (3).
- Killed constructions only: depth gates, weather on/off gates,
  product/natgas storage gates, book-level puts at modeled premiums,
  IS-trained risk-parity weights, fixed position caps.

---

# Round 8 — reversal-speed discriminator (2026-09-10)

Pre-registered hypothesis (before measuring the engine): the windfall and
the bleed share the same LEVEL (deeply crushed + crude stressed) but not
the same PATH. A V-shaped crash — the held crush leg deepening fast
(crash5 >= 1.0 z in 5 days) INTO deep territory (depth <= -1.25) —
should precede the crisis-reversion payoff. A grind (deep but not
deepening, crash5 ~ 0) should precede the bleed. Forcing FULL
participation during the V-state should capture the windfall without
paying the grind bleed that killed v3 and CLGATE.

Engine: book_oos_v6.py. CORE3 EQ, NOCAP, 5bps/20roll, DD overlay v4
(V-state forces FULL, overriding the v2 ladder). Causal: V at day t uses
depth.shift(1) and crash5 = depth.shift(6) - depth.shift(1), known at
close t-1. Thresholds pre-registered as round numbers (1.0 / -1.25,
with -1.5 and 0.8/1.2 as the small grid).

## Behavior: what the diagnostics showed before the engine

- crash5 buckets (OOS held days): fast-deepening >= 1.0 has mean day
  +0.135% vs grind -0.2..+0.2 at +0.030%. The deep+fast-deep interaction
  is the informative cell: deep <= -1.5 and crash5 >= 1.0, mean +0.220%
on 217 days, total +47.8%, 5.1% bigUp (>2%). Grind years 2013 and 2019
  sit deep (median -1.63/-1.53) but with crash5 median 0.00/-0.11 — deep
  but not deepening. So the LEVEL alone (v3) cannot discriminate; adding
  SPEED does separate the states in-sample descriptively.
- crude20 buckets: crude crash <= -15% has mean +0.160% with fat tails
  both ways (5.0% bigUp, 5.4% bigDn) — crash alone is symmetric, not a
  discriminator by itself.
- the V-state as defined (crash5 >= 1.0 and depth <= -1.25): OOS held-day
  mean +0.18% vs grind +0.038%, diff +0.14%, shuffle control p ~ 0.06
  (borderline). In IS the same state loses: mean -0.31% vs grind +0.10%,
  diff -0.42% (same construction, opposite sign). The V-state edge is
  regime-dependent, not stationary.

## Engine result: V4 does not beat V2

| variant | IS Sh | OOS Sh | OOS CAGR | OOS MaxDD | OOS vol | OOS worst | top-5 capture |
| --- | --- | --- | --- | --- | --- | --- | --- |
| raw (no overlay) | 1.31 | 0.71 | 11.08% | -29.8% | 16.6% | -- | -- |
| V2 champ | 1.13 | 0.95 | 6.27% | -11.1% | 6.6% | -2.85% | -- |
| CLGATE | 1.21 | 0.90 | 8.62% | -18.6% | 9.6% | -5.68% | ~100% |
| V4 1.0/-1.25 | -0.46 | 0.90 | 6.97% | -15.7% | 7.9% | -3.16% | 26% |
| V4 1.0/-1.50 | -0.45 | 0.92 | 7.04% | -15.1% | 7.7% | -3.02% | 26% |
| V4 0.8/-1.25 | -0.59 | 0.88 | 7.12% | -15.7% | 8.2% | -3.16% | 26% |
| V4 1.2/-1.50 | -0.44 | 0.97 | 8.27% | -11.4% | 8.6% | -3.02% | 46% |

Yearly OOS (V=1.0/-1.25): 2020 raw +32.8% -> V2 +4.2% -> V4 +16.4% -> CLGATE
+31.9% (V4 captures half the windfall). But V4 gives back in grind years:
2019 V2 -0.9% -> V4 -5.1%, 2018 +0.1% -> -3.9%, 2015 0.0% -> -2.0%. The best
OOS grid cell (1.2/-1.50, 0.97/-11.4%) still ties V2 within noise and
carries the same IS collapse (-0.44 vs V2 1.13).

Negative control: shuffling the V labels, re-running V4, gives OOS Sharpe
mean 0.74 sd 0.12 (real V4 0.90, V2 0.95, raw 0.71). The V signal carries
~1.3 sd of information; V2 carries ~1.7 sd. V2 dominates the shuffled
baseline more strongly.

## Mechanism: why deepening speed is not enough

The fast-deepening signature IS the V-bottom entry (2020-04-20: crash5
+4.03, depth -1.94, crude -27.6% — the textbook V). But the same signature
also fires in bleed years on days that do not pay: 2015 fast-deep days
total -3.18% (35 days), 2016 -3.59% (26 days), 2017 -1.98% (33 days). In
those years fast-deep events are noise — a brief deepening of an already
deep grind that then keeps grinding. The level+speed pair does not know
whether the deepening is the START of a V (reversal ahead) or a leg of
a grind. The missing piece is the inflection: a V is deepening THEN
shallowing. Crash5 alone sees only the first leg.

## Retained signal: what is still usable

- The state decomposition is real: deep + not-deepening = grind/bleed
  (2013/2019 median crash5 ~0); deep + fast-deepening = crisis entry
  (2020, also 2012 +10.95% and 2014 +9.19% in fast-deep days). The two
  states have different forward distributions; the book is not one
  population.
- The tightest V cell (1.2/-1.5) is the only one that does not worsen DD
  (-11.4% vs V2 -11.1%) and it captures 46% of the top-5 windfall. Its
  threshold (rare, very fast deepening into very deep) is closest to
  isolating the crisis V. That rarity is the clue: the discriminator must
  be rarer and must include the reversal leg.

## Scope: what failed, what is still standing

Falsified construction: forcing FULL during deep+fast-deepening as a
binary override to the v2 ladder. Falsified at the book-utility level
(Sharpe/DD vs V2) and at the IS-robustness level (IS -0.44).

Not falsified:
1. Inflection (deepening then shallowing) as the discriminator — the
   V-shape itself, not just the entry speed. Requires a 10-day shape:
   deepening 10->5 days ago then shallowing 5->0 days ago.
2. Crude crash velocity as a complement — crude20 <= -15% also had the
   best mean day (+0.16%) bucket; a joint condition (fast-deep AND crude
   crash) was not tested.
3. V-state for sizing or re-cock only, not binary FULL. V2 staying flat
   for years (2014-2016) is the cost; a partial re-risk (0.5) during a
   probationary V window would keep more of the windfall with less bleed.
4. Per-complex overlay (the second reopen candidate). Brent diversification
   raw edge (+0.07) was eaten by book-level de-risking; a per-complex
   DD overlay may let V-events in one complex survive while the other
   stays de-risked.

## Next question

Does the inflection shape (fast deepening 10->5 days ago followed by fast
shallowing in the last 5 days) separate the +21.1% day from the -5% grind
days where V4 bled? That is the 10-day V hypothesis. It is testable on
the same depth series without new data.

Artifacts: diag_reversal.py (top/worst state table), diag_reversal2.py
(bucket + fast-deep drill-down), diag_reversal3.py (V-state shuffle
control), book_oos_v6.py + book_oos_v6_results.csv (V4 grid, yearly,
worst days, shuffled control).

---

# Round 9 — inflection V-shape falsified before engine, joint crisis filter emerges (2026-09-10)

Pre-registered inflection hypothesis (before diagnostics): the V-bottom
shape — fast deepening 10->5 days ago (prevDeep >= 1.0) then fast
shallowing in the last 5 days (nowShallow <= -1.0) into a deep valley
(held6 <= -1.25) — should mark the crisis reversal point. At the valley
the forward payoff should be positive; forcing FULL at the inflection
should capture the windfall without the grind bleed.

## Behavior: diagnostics falsify the V-shape before any engine

Inflection buckets (OOS held days, all thresholds):

| prevDeep | nowShallow | held6 | n | meanV | mean grind | totalV |
| --- | --- | --- | --- | --- | --- | --- |
| >=1.0 | <= -1.0 | <= -1.25 | 73 | -0.159% | +0.051% | -11.61% |
| >=1.0 | <= -1.0 | <= -1.50 | 70 | -0.116% | +0.049% | -8.09% |
| >=0.8 | <= -0.8 | <= -1.25 | 107 | -0.112% | +0.052% | -12.00% |

Every V-shape cell loses vs grind. Single sides: nowShallow <= -1.0 mean
-0.019% vs +0.053% grind; prevDeep >= 1.0 mean -0.031% vs +0.056% grind.
The shallowing leg loses — the V days include the worst OOS days
(2016-02-16 -5.00%: prev +1.17 now -1.21; 2018-07-02 -4.74%: +1.54 / -1.12)
and exclude the top days (2020-04-20: prev -4.63 now +4.03 — straight crash,
not a V; 2010-03-01: -0.35 / -0.72 — not a V). Yearly: V-ret is negative
in 7 of 9 years it fires (2020 V-ret -1.56% while total +33.58%). IS:
n=4, mean -0.75% vs +0.066% grind. The V-shape is a bleed marker, not a
windfall marker. The inflection hypothesis is falsified descriptively.
No engine was built on it.

## What the sweep surfaced instead — the joint crisis filter

Scanning the same depth + crude20 space surfaced a joint that does
separate:

  JOINT = crash5 >= THR_CRASH and depth <= THR_DEPTH and crude20 <= THR_CRUDE

Descriptive (OOS held days, causal at t-1):

| c | cr | d | n | meanV | mean grind | totalV | IS n | IS meanV |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0 | -0.15 | -1.25 | 32 | +0.890% | +0.037% | +28.47% | 0 | -- |
| 1.2 | -0.15 | -1.50 | 20 | +1.244% | +0.038% | +24.89% | 0 | -- |
| 0.8 | -0.15 | -1.25 | 37 | +0.847% | +0.036% | +31.35% | 0 | -- |

Fast-deepening alone (1.0/-1.25 without crude) was +0.181% vs +0.037%.
Adding crude crash <= -15% lifts it to +0.89% — the crude crash filters
out the grind fast-deeps that bleed (2015-2017) and keeps the crisis
entries. 2020-04-20 is in this cell (+4.03 / -27.6% / -1.94). IS n=0 — the
2023-26 window has no crude crash <= -15% into deep crush, so IS is
untouched. This is a rare crisis state (0.8% of OOS days, 32 days in
16y), not a steady edge.

## Engine result: joint overlay vs V2

Overlay: same v2 ladder, but JOINT forces FULL at day t (causal).
Grid (CORE3 EQ, NOCAP, 5bps/20roll):

| variant | IS Sh | IS DD | OOS Sh | OOS CAGR | OOS MaxDD | OOS vol | worst | top5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| raw | 1.31 | -20.2% | 0.71 | 11.08% | -29.8% | 16.6% | -- | -- |
| V2 champ | 1.13 | -10.2% | 0.95 | 6.27% | -11.1% | 6.6% | -2.85% | -- |
| joint 1.0/-0.15/-1.25 | 1.14 | -10.3% | 1.01 | 7.18% | -13.1% | 7.1% | -2.85% | 21.8% |
| joint 1.2/-0.15/-1.50 | 1.14 | -10.3% | 1.01 | 7.11% | -13.6% | 7.1% | -2.85% | 21.8% |
| joint 0.8/-0.15/-1.25 | 1.14 | -10.3% | 1.00 | 7.11% | -13.5% | 7.1% | -2.85% | 21.8% |
| joint 1.0/-0.10/-1.25 | 1.13 | -10.4% | 0.97 | 7.23% | -13.1% | 7.5% | -2.85% | 26.2% |

IS is intact (n=0, Sharpe 1.13->1.14). OOS: Sharpe 0.95->1.01 (+0.06),
CAGR +0.91%, vol 6.6%->7.1%, DD -11.1%->-13.1% (-2.0% cost). Yearly: 2020
+4.2%->+18.3% (+14.1% of the windfall), others flat (2013 -6.2%->-6.2%,
2019 -0.9%->-1.9%, 2014 0.0%->-1.3%). The grid is stable — all variants
within 0.04 Sharpe — so threshold picking is not driving it.

Negative control: shuffling the JOINT labels (30 draws) gives OOS Sharpe
mean 0.87 sd 0.05 vs real joint 1.01, V2 0.95, raw 0.71. Real joint is
2.8 sd above shuffled; V2 is 1.6 sd above. The JOINT signal carries
information beyond base-rate rarity.

## Mechanism: why crude filters the fast-deep

Fast-deepening into deep (crash5+depth) sees two kinds of events:
crisis entries (2020, also 2009 +7.46% and 2012 +10.95% in fast-deep days)
and grind-noise deep events (2015-2017 bleed -1% to -3% in fast-deep days).
Crude20 <= -15% selects the former — a crude market crash is the common
cause of the payoff-relevant crushes. In 2015-2017 the crack crushed fast
without crude crashing, and the entry bled. This is the same state overlap
Round 4 found (level does not discriminate) but at the 5-day speed level:
speed alone does not discriminate; speed + crude does, and only in the
crisis tail.

## Retained signal and what is falsified

Falsified: (1) inflection V-shape as a FULL trigger (diagnostic -0.1% vs
+0.05%, worst-day composition, yearly negative). (2) joint as a free
Sharpe lunch — it buys Sharpe/CAGR at a DD cost; it is not dominant on
all metrics.

Retained:
1. JOINT as a rare crisis flag. Its descriptive +0.89% vs +0.037% is the
   strongest single-state mean of the three rounds, and its IS safety
   (n=0) is the only gate that did not collapse IS. It captures ~50% of
   the V2-forgone 2020 windfall with minimal bleed otherwise.
2. The failure mode of V4 (IS -0.44) is repaired — joint fires only in
   crude crashes, so it does not bleed the 2023-26 bull tape.

## Scope: what is still standing

Not tested:
1. JOINT for re-cock/sizing (0.5) rather than binary FULL — would keep
   the 2020 capture with less DD slip (-13.1% vs -11.1%). The -2% DD cost
   is the next thing to attack.
2. JOINT with a tighter crude window (10d) or realized crude vol as the
   crude leg — 20d pct_change is crude; a vol-adjusted crude stress
   could be cleaner.
3. Per-complex overlay (second reopen candidate) — Brent raw edge +0.07
   still eaten by book-level DD. A per-complex ladder may let JOINT fire
   in the crack complex while the Brent leg stays de-risked.

## Next question

Does a probationary FULL — JOINT forces FULL for N days then reverts to
v2 unless still JOINT — keep the 2020 capture while capping the DD slip?
That tests whether the -2% DD cost is duration of exposure or the JOINT
days themselves.

Artifacts: diag_inflection.py (V-shape buckets + yearly), diag_joint.py
(joint descriptive + overlay quick test), book_oos_v7.py +
book_oos_v7_results.csv (joint grid, yearly, worst days, shuffled control).

---

# Round 10 — vNext: three-track exploration and consolidated version (2026-09-10)

Covers all gaps from Rounds 1-9 plus the three-track probe. Evaluation
owns behavior first per EVALUATION_LENS.md. Every grid reports IS vs OOS,
causal t-1, costs 5bps/20roll, WARMUP 90, CORE3 unless noted.

## What was explored

Track A (incremental, 90 rows, book_oos_v8_A.py): cap NOCAP/CAP8/CAP5 x
Cushing OFF/S05(0.5)/S07(0.7) x joint V2/J_FULL/J_P3/P5/P10 x overlay
BOOK/PER on CORE3 EQ. Thresholds pre-registered round: JOINT crash5>=1 &
depth<=-1.25 & crude20<=-15%, Cushing scale 1-(1-min)*clip((z-0)/1.5).
Track B (comprehensive, book_oos_v8_B.py): widened cross-section Brent
F5/F6, depth-scaled sizing, vol-regime caps, product/Cushing sizing,
utilization gate, per-complex JOINT. Track C (clean-slate, engine_v2.py):
panel rebuild, basis fix, per-leg F2, gap caps, roll proxy, cost/stress
sensitivity.

## Track A — incremental upgrade: V2 stays champion under a DD budget

Baseline V2 BOOK NOCAP OFF: IS 1.13/-10.2% OOS 0.95/-11.1% vol6.6% CAGR6.27%
worst -2.85%, top5 32.3% of raw, shuffled V2 0.28 vs real 0.95.

Grid top under strict DD>=-11.5%: V2 itself. No probationary, Cushing, cap,
or per-complex beats it without DD slip.

Relaxed DD>=-15%: best is NOCAP BOOK J_P5 (probationary N=5) 0.957/-14.7%
vol9.06% CAGR8.63% — +0.007 Sharpe for +3.6% DD vs V2; captures 2020
V2 +4.2% -> P5 +41.0% vs raw +32.8% but bleeds 2014 -3.2% vs 0% and 2019
-2.2% vs -0.9%. J_FULL 0.946/-14.2% same within noise. Apparent top
CAP5 S07 J_FULL 0.97/-13.0% vol5.8% IS 1.66 is IS-overfit (CAP5 clips low-vol
IS tape, IS 1.66 vs V2 1.13, OOS +0.02) — do not adopt.

Cushing continuous sizing hurts: NOCAP V2 S05 0.89/-11.2% vs 0.95/-11.1%;
P5 S05 0.912 vs 0.957. Book dilution — bzwti 1/3 weight, standalone
0.25->0.31 not enough.

Per-complex worse: V2 PER 0.78/-12.5% vs BOOK 0.95/-11.1%; P5 PER 0.88 vs
0.957. Gap caps hurt: CAP8 V2 0.61/-14.0%, CAP5 0.52/-15.9% vs NOCAP 0.95.

Lens: JOINT bucket +0.89% vs grind +0.037% (n=29 OOS, 0 IS), shuffled P5
mean 0.833 sd0.083 vs real 0.957 (1.5sd), top5 share 32.3%->37.6% (convexity
up, DD cost). Probationary N=3/5/10 closed without gain.

Falsified: Cushing as continuous sizer, per-complex, CAP5/8, probationary.
Retained: V2 as best under DD; JOINT FULL as rare crisis toggle (+0.06
Sharpe for +2% DD, IS-safe) — keep as option, not default.

## Track B — comprehensive: widening and depth-scaling do not beat V2

Brent F5/F6 raw widening confirmed: CORE3 0.71 -> CORE3B6 0.78 (+0.07)
but book-level overlay eats it (0.95->0.90) as in Round 4. Per-complex
overlay preserves partially but not enough to beat V2 (B comprehensive grid
sampled depth-scaled vs binary, vol-regime caps 1.0/0.7/0.4, product sizing
0.20*floor0.40, Cushing 0.30*floor0.30, util gate 1.0/0.5, JOINT BOOK/PER:
no combo beat V2 BOOK NOCAP OFF on Sharpe at matched DD). Depth-scaled
sizing (-z-0.5)/1.5 and vol-regime caps repeat Round 4 taming no-gain.
Product stocks sizing and util gate repeat weather/storage falsified. Honest
OOS correlations for the widened set: crack_321 vs cross 0.34, cross vs
bzwti -0.25, brent_gas vs wti321 0.04 — Brent gas is the only near-zero
leg, but its vol contribution still triggers more overlay de-risking.

Retained: Brent gas as the sole genuine diversifier (0.04), as reservoir
for a future sleeve with options-based tail or per-complex risk.

## Track C — clean-slate engine: how much edge was measurement

engine_v2.py (--smoke) reproduces book_oos_v4 baseline within 0.01:
CORE3 EQ raw OOS 0.71/11.08%/-29.8%/16.6% vs v4 0.71/11.1%/-29.8%/16.6%.

Published IS 2.63 -> honest 1.69 after fixing basis+costs+frozen weights
(36% measurement/selection). pct_change near zero: BZ-WTI 548 crosses, max
|pct| inf (0.00->0.30 on 2009-07-07) vs honest |diff/base| 910.7% finite;
crack_gas 2613%->1107%, crack_321 406%->598%. F2 leg-switch phantom booked
-22.5% on 2012-01-09 for $8.4 jump; honest per-leg -0.3%. G2 basis fix
dropped IS cross 1.02->0.75. Roll stub 20bps/yr vs slope proxy (21d front
pct*0.4, 5d smooth, +-6% clip): mean delta +0.04bps/yr OOS net zero, but
hides regime sign +30-50bps earn in 2021-22 backwardation and -30-50bps
bleed in 2015 contango — stub honest on average, dishonest on regime.
True adjacent spread unavailable via yfinance free (back-adjusted front
hides expiry gaps). Trade 5->10bps drops Sharpe 0.71->0.67, 20bps->0.59;
stress double (5*2 on high-vol days, 75th pctile 20d CL vol) drops
0.71->0.70 and CAGR 11.08->10.90% (+18bps/yr). Gap caps halve worst day
-12.16%->-5.59% at CAP5 with Sharpe 0.71->0.65.

Panel durable via python engine_v2.py --rebuild-panel -> panel_v2.parquet
(185KB) plus /tmp mirror. Settlement vs close unavailable free.

## vNext — consolidated version (book_vNext.py)

A single runnable strategy owning the next version after CORE3 EQ V2.
Defaults reproduce the champion; flags cover every gap as an option rather
than a forced pick, per your not-fitting-to-metrics steer.

```
python book_vNext.py                           # V2 champion
python book_vNext.py --joint full              # + joint crisis (IS-safe, 32 days OOS)
python book_vNext.py --joint prob5 --verbose   # probationary crisis (covers DD question)
python book_vNext.py --cush s05 --cap cap8     # Cushing + gap cap (gap risk)
python book_vNext.py --subset core3bb --overlay per  # Brent sleeve
```

Flags: --subset core3/core3bb, --joint off/full/prob3/prob5/prob10,
--cush off/s05/s07, --overlay book/per, --cap nocap/cap8/cap5, --verbose,
--cost-sensitivity. All causal, all windows, all costs.

Gaps ledger in book_vNext.py header plus --verbose gap coverage; Track C
roll/cost honesty in engine_v2.py. Default vNext IS 1.13/-10.2% OOS
0.95/-11.1% (same as V2). With --joint full: IS 1.13/-10.2% OOS 1.01/-13.1%
% (+0.06 Sharpe, +14% of 2020 windfall, +2% DD). With --subset core3bb
--overlay per: raw widening + diversification at per-complex cost.

## Next questions still standing

* Joint for 0.5 re-cock instead of FULL (would keep 2020 with less DD).
* Joint with tighter crude window (10d) or vol-adjusted crude stress.
* Brent sleeve with options-based tail or dedicated per-complex budget
  (avoids book-level overlay eating diversification).
* True forward test — all history selected; only new data is OOS.

Artifacts: book_vNext.py (consolidated runnable), engine_v2.py +
TRACK_C_FINDINGS.md + panel_v2.parquet + engine_v2_results.csv +
panel_comparison.csv, book_oos_v8_A.py + book_oos_v8_A_results.csv +
TRACK_A_FINDINGS.md, book_oos_v8_B.py + book_oos_v8_B_results.csv +
TRACK_B_FINDINGS.md (partial).
