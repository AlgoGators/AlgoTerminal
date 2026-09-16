# Derived thresholds — findings

Date: this session. Harness: `derived_harness.py`. Prereg:
`research/derived_thresholds.md` (02ceccb).

## What happened

The 0.75/-0.5 entry/exit thresholds are gone. The exposure now reads
entirely from the TRAIN conditional-mean curve:
- shape w(z) = clip(E[fwd20|z,comp/norm] / max_curve, 0, 1),
- one cutoff line: the largest z where the curve's expected 20d
  return >= 5% (BAR), derived on TRAIN only.

## The derived curve (TRAIN, comp/norm days)

| z | E[fwd20] | P(win) |
| --- | ---: | ---: |
| -2.51 | +16.6% | 68% |
| -1.36 | +12.8% | 58% |
| -0.91 | +9.5% | 59% |
| -0.68 | +6.7% | 53% |
| -0.45 | +4.3% | 50% |
| +0.70 | -0.2% | 49% |
| +1.39 | -6.9% | 30% |

Zero crossing ~ z=+0.58. The 5% expected-return bar lands at
zcut ~ -0.68. The old plateau pick (0.75) is approximately where
this derived bar sits: the number is recovered from the data, not
assumed.

## Results (clean blocks)

| Variant | TRAIN t | VALIDATE t | OOS t | FULL t | neg% |
| --- | ---: | ---: | ---: | ---: | ---: |
| Curve (no bar) raw | 2.90 | 0.97 | 2.78 | 2.99 | 29% |
| Curve (no bar) + gear | 2.90 | 0.97 | 2.78 | 2.99 | 29% |
| Bar5 raw | 2.24 | 1.54 | **2.53** | **2.82** | 19% |
| Bar5 + gear | 2.24 | 1.54 | 2.53 | 2.82 | 19% |

Gear is constant scaling (Sharpe invariant). VALIDATE CIs: Bar5
90% CI [-0.04,+1.22] raw / [-0.01,+0.45] geared, both touching
zero. OOS and FULL CIs exclude zero.

## Honest verdict

1. The fully parameter-free continuous function FAILS out-of-window
   (VALIDATE t=0.97). The edge needs a signal-to-noise bar, not just
   positive expected mean.
2. With the bar derived from the curve (E >= 5%), the configuration
   holds OOS/FULL with CIs excluding zero and neg blocks ~18%, and
   is borderline on VALIDATE (t=1.54).
3. The old 0.75 parameter is recoverable as the derived bar's
   location on this sample; the exit -0.5 disappears (the shape
   winds down below the bar). No state-machine thresholds remain:
   one curve shape, one derived line.

## Ledger update

- 0.75/-0.5 thresholds: REMOVED (replaced by TRAIN-derived curve
  shape + 5% expected-return bar, zcut ~ -0.68).
- Bar5 curve exposure: HOLD on OOS/FULL; borderline VALIDATE. The
  derived construction is the current candidate, with the honest
  caveat that the fully unbarred version does not hold.

## Artifacts

- `derived_harness.py`, `results/derived_thresholds.csv`
