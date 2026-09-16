# Hold validation — remove overlap, lookahead, overfitting

The regime rules are claims. This pass fixes the three leaks and
tests whether the rules hold in a window not used to choose them.

## Leaks fixed

1. Overlap: all claims use non-overlapping 20-day forward windows
   (sample every 20th date). No overlapping cells.
2. Lookahead: the GMM regime identity is dropped (full-sample fit).
   Only the causal R2 identity (trailing 504d median/MAD, data up to
   t-1) and causal margin states (seasonal z uses prior observations)
   are used. State at close t decides the t..t+20 window.
3. Overfitting: constants and rule membership are frozen in this
   preregistration BEFORE the validation window is measured. The
   validation window is 2019-01-01 .. 2026-09-09. The training
   window is 2007-01 .. 2018-12.

## Frozen rule card

State definitions (all causal at t):
- R2(t): compression if level < trailing 504d median - 1.4826*MAD,
  expansion if above + band, else normal.
- margin(t): crush if seasonal z <= -0.75, stretch if >= +0.75,
  else normal.
- weather(t): cold if NYC T2M same-month z <= -1.
- blend(t): switch if within 21 days of Apr 1 or Sep 15.

Rules (entry at close t, forward 20 days):
- L (long crush): R2 in {comp, norm} AND margin crush.
- S (short stretch): R2 in {norm, exp} AND margin stretch.
- C (cold tilt): report L entries split by cold vs not cold (the
  expectation from the shapes: cold crush forward higher).
- B (blend suppression): report L entries inside the blend switch
  window separately (expectation: suppressed entries had low or
  negative forward).

## Statistical bar

Per rule, per window (TRAIN, VALIDATE), non-overlapping entries:
- n, mean fwd20, std, t-stat, 90% confidence interval.
- Yearly sign consistency on the validation window.
- A rule HOLDS if: the validation mean has the same sign as the
  training mean, the 90% CI excludes zero in both windows, and the
  yearly positive (or negative) fraction supports the sign, with
  n >= 20 in validation.

No iteration. No tuning on validation. This pass is a single shot.

## Deliverable

findings/hold_validation.md. If a rule holds on validation, it is the
first claim in the project with cleaned statistics. The remaining
true test stays the frozen forward protocol.
