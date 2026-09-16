# Champion restatement — non-overlap blocks

Harness: `honesty_harness.py`. Method: non-overlapping 20-trading-day
block sums, 90% confidence intervals, per-window (OOS/IS/FULL).
Overlay series are path-dependent (flagged below).

## Results

| Window | Series | n blocks | mean/block | ann | t | 90% CI | neg blocks | worst |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| OOS | raw | 198 | +0.82% | +10.29% | +2.41 | [+0.26, +1.37]% | 40% | -14.58% |
| OOS | ov | 198 | +0.45% | +5.63% | +3.06 | [+0.21, +0.69]% | 21% | -4.29% |
| IS | raw | 33 | +1.36% | +17.20% | +1.61 | [-0.03, +2.76]% | 30% | -10.49% |
| IS | ov | 33 | +0.44% | +5.49% | +1.59 | [-0.01, +0.89]% | 30% | -2.28% |
| FULL | raw | 236 | +0.87% | +10.95% | +2.83 | [+0.36, +1.37]% | 39% | -14.58% |
| FULL | ov | 236 | +0.43% | +5.37% | +3.30 | [+0.21, +0.64]% | 22% | -4.29% |

## Interpretation

- The champion's OOS and FULL mean returns are statistically
  significant at 90% with non-overlapping windows (t = 2.4 to 3.3;
  CIs exclude zero). The claim "the v1 book has a positive edge" is
  now supported by cleaned statistics, stronger than the L-rule cell
  alone (which had n=15).
- The IS window (33 blocks) has CIs crossing zero. The tuning window
  was also the smallest sample.
- Negative blocks: raw book negative in about 40% of 20-day blocks;
  the overlay cuts that to 21-22%. The overlay is real at the block
  level but remains path-dependent: blocks are not iid for the
  overlaid series.
- Post-selection honesty: CORE3 membership and overlay thresholds
  were chosen on this same sample. Selection inflates what a fresh
  replication would show. The honest post-selection expectation stays
  below the headline (roughly 0.7-0.8 in Sharpe terms from Round 3).

## EIA-scaled verdict redo (non-overlap, FULL)

| Series | n blocks | mean/block | ann | t | 90% CI | neg |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| baseline | 236 | +0.86% | +10.86% | +2.80 | [+0.36, +1.37]% | 41% |
| scaled | 236 | +0.28% | +3.55% | +1.63 | [-0.00, +0.57]% | 42% |

The old verdict holds cleanly: the EIA scaling destroys the edge. The
baseline mean is significant and about 3x the scaled mean; the scaled
CI includes zero.

## What is queued for the same treatment

- Weather-gate and storage-gate kills: their constructions need a
  rebuilt run in v2 before clean restatement. Recorded as queued in
  the claims ledger, not restated here.
