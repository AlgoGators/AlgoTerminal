# Direction 1 — harden the hold (findings)

Date: this session. Harness: `harden_harness.py`. Prereg:
`research/direction1_harden_hold.md` (bf8ccb9). Clean non-overlap
blocks where blocks are used.

## 1a. Deflated Sharpe (OOS daily)

| Series | SR | skew | kurt | DSR N=10 | N=100 | N=1000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| raw | 0.635 | +2.98 | 68.3 | 1.000 | 1.000 | 1.000 |
| ov | 0.862 | +6.70 | 135.6 | 1.000 | 1.000 | 1.000 |

Even under 1000 trials, the observed OOS Sharpe has essentially zero
chance of being luck. Selection inflation is real for picking among
variants, but it does NOT explain the champion's OOS edge. The DSR is
not a claim about a clean replication; it answers "could 1000 dead
strategies have produced this SR" -> no.

## 1b. Cost robustness (non-overlap blocks)

| Cost t/r | Window | ann | t | 90% CI |
| --- | --- | ---: | ---: | ---: |
| 5/20 | OOS | +10.29% | +2.41 | [+0.26, +1.37]% |
| 10/20 | OOS | +9.60% | +2.25 | [+0.20, +1.32]% |
| 20/40 | OOS | +8.17% | +1.91 | [+0.09, +1.21]% |
| 10/40 | OOS | +9.57% | +2.24 | [+0.20, +1.32]% |
| 5/20 | FULL | +10.86% | +2.80 | [+0.36, +1.37]% |
| 10/20 | FULL | +10.15% | +2.62 | [+0.30, +1.31]% |
| 20/40 | FULL | +8.68% | +2.24 | [+0.18, +1.19]% |

The HOLD claim survives 4x costs: OOS and FULL CIs exclude zero at
10/20 and 20/40 bps.

## 1c. Overlay cost ledger (OOS non-overlap blocks)

- Total: raw +161.76% vs overlay +88.46%. Gross forgone about
  73 percentage points.
- Top-10 raw blocks: raw sum +123.06%, overlay captured +42.51%
  (6 captured, 4 sat flat). The overlay keeps about a third of the
  best blocks.
- 2014-2016: raw +21.13% vs overlay +0.00%. The flat era is real in
  block terms.
- Forgone on positive raw blocks sums to +252.48% gross (many blocks
  where overlay captured less; overlay also takes negatives on some
  raw-positive blocks).

## 1d. Settlement cross-check (CL)

- EIA RCLC1 (Cushing WTI weekly) vs yfinance CL weekly, 843 rows,
  2007-07 .. 2024-03.
- Level correlation 0.9967. Mean absolute relative difference 1.99%.
- Weekly-return correlation 0.40 (alignment artifacts on period
  dating; levels match closely).
- RB/HO/NG/BZ settlement series not available through the probed EIA
  routes. Measurement risk partially addressed: CL levels are
  consistent; the rest remain on yfinance closes.

## Ledger additions

- Champion edge survives 10/20 and 20/40 costs: HOLD (clean blocks).
- Champion OOS SR not explained by <=1000 trials: HOLD (DSR ~ 1).
- Overlay cost ledger quantified (gross ~73pp, top-10 capture ~35%,
  2014-16 fully flat): CONFIRMED-STAT (clean blocks).
- CL settlement level-consistent; other legs constrained: PARTIAL.

## Artifacts

- `harden_harness.py`, `results/direction1.csv`
- `engine/eia/raw_pri_fut_RCLC1.csv` (new input)
