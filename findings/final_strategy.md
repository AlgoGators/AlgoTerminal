# Final strategy — statistically-rooted integration (findings)

Date: this session. Harness: `final_harness.py`. Prereg:
`research/final_strategy.md` (caab518). Acceptance on clean 20d
blocks; overlay flagged path-dependent.

## Results

| Variant | OOS raw ann (t) | FULL raw ann (t) | OOS ov ann (t) | ov Sharpe | ov DD | ov neg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| V_Champ | +10.29% (2.41) | +10.95% (2.83) | +5.63% (3.06) | **0.862** | **-10.73%** | 21% |
| V3_H1 | +12.61% (2.87) | +13.42% (3.36) | +5.60% (2.91) | 0.801 | -12.54% | 29% |
| V1_regime | **+13.09% (2.94)** | **+13.82% (3.43)** | +5.69% (2.92) | 0.816 | -12.52% | 29% |
| V2_both | identical to V1_regime | | | | | |

## Verdict

REJECTED at the preregistered bar, exactly at the overlay-interaction
level. The gates genuinely improve the RAW book: OOS mean up 10.3% ->
13.1%, raw t 2.41 -> 2.94 (FULL 2.83 -> 3.43), raw negative blocks
40% -> 39%. Every candidate's raw CI excludes zero. But the V2
overlay interaction flips: overlaid t drops below the champion's,
overlaid Sharpe 0.862 -> 0.801-0.816, overlaid DD -10.73% ->
-12.52% (worse by about 1.8 points, above the 1-point bar), and
overlaid negative blocks 21% -> 29%.

The overlay sits off more often when the crack sleeve is gated,
because the gated equity path enters the -6%/-10% ladder differently.
This is the same failed level as multi-leg F2; the overlay is the
recurring constraint on every honest raw improvement.

## Secondary findings

- V2 (regime + H1) is identical to V1 (regime only): the H1 gate adds
  nothing once the regime gate is active. H1's leg-level help (clean
  direction-2) does not survive in the book under the regime gate.
- The regime gate is the stronger of the two: it removes the negative
  deep-crush-in-expansion trades and raises raw t to 2.94 cleanly.

## Ledger additions

- Regime gate on crack (raw): DIRECTIONAL-clean improvement (raw
  t 2.94/3.43), rejected at the book-overlay level.
- H1 in the book under regime gate: NULL (redundant).
- Final integration (regime + H1, V2): REJECTED; failed level =
  overlay interaction. Champion remains the deployable benchmark.

## Retained for the model-first path

The raw improvement is real and clean; the blocker is the overlay.
The model-first phase (HMM + mixture-based risk publication) is the
designed replacement for the V2 ladder. Champion stands until then;
the forward protocol supplies the data.
