# Reassessment probes — findings

Date: this session. Harness: `reassess_harness.py`. Prereg:
`research/reassessment_probes.md` (645de04). Bucket tests position-
free; M1 adds one light construction with costs, no book, no overlay.

## N1 — propane/NGL winter (ch27)

- Winter, propane z vs fwd20 crack_gas: non-monotone (+17.4, +17.1,
  +20.9, +15.9, +15.6). Top-minus-bottom -1.85%. No conditioning.
- Summer: all buckets negative (-5.7 to -8.5). Gas forward negative
  in summer broadly; propane adds nothing.
- Winter, propane z vs fwd20 NG: monotone NEGATIVE (-2.7 to -6.2
  across rising propane z; equivalently tight/low propane precedes
  NG up ~+2.7%). Direction matches a tight-NGL co-movement story.

Verdict: gas-crack link ABSENT. NG winter link weak-to-moderate,
descriptive only. Retained as a Phase 4 NG-conditional candidate,
not a trade.

## C1 — Cushing utilization ratio (ch29)

- Fullness quintiles vs fwd20 bzwti: b0 +4.5, b1 +7.1, b2 +1.9,
  b3 +25.6, b4 +8.8. Not monotone. High-default days do NOT show
  the hypothesized narrowing (negative forward).
- Combined (fullness >= 0.85 and draw): +5.5% vs other +9.6%.
  Control: shuffled mean +11.4%, sd 9.6. Within noise; n=135.

Verdict: phenomenon ABSENT as specified. Cushing ratio does not time
the spread narrowing at 20 days. Chain ch29 killed at Tier 1.

## M1 — multi-leg F2 depth (ch30)

- Depth buckets (pooled crushed cross legs):
  - fwd10: +4.9, +5.2, +6.0, +5.3, +7.3.
  - fwd20: +7.3, +9.3, +9.8, +11.4, +16.3.
  Monotone rising with crush depth. The deepest quintile reverts
  about 2.2x the shallowest. Phenomenon PRESENT.
- Light construction (multi-leg all-crushed legs, depth multiplier):
  OOS raw Sharpe 0.670, CAGR 25.45%, MaxDD -94.83%.
  v1 single-most-crushed: Sharpe 0.589, CAGR 18.32%, MaxDD -67.71%.
  Depth + multi-leg improves Sharpe and CAGR and destroys the
  drawdown: three vol-targeted legs stacked with up to 2x depth
  multipliers over-commit exposure.

Verdict: depth phenomenon PRESENT and monotone (the captain's
"deeper crush, stronger reversion" is real). The construction as
built is not adoptable until exposure is scaled (cap total cross
notional or normalize by leg count). That is a Tier 2 fix, recorded.

## Chain status updates

- ch27 (ngl-propane-winter): tier1-pending -> evidence-partial
  (NG-side link only; gas-crack side absent).
- ch29 (cushing-ratio): tier1-pending -> tested-killed.
- ch30 (multi-leg-f2): tier1-pending -> evidence-confirmed
  (phenomenon monotone; construction open).

## Artifacts

- `reassess_harness.py`
- `results/reassessment_probes.csv`
- Statuses in `research/graph/chains.csv`
