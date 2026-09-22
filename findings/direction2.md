> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Direction 2 — close the record (findings)

Date: this session. Harness: `direction2_harness.py`. Prereg:
`research/direction2_close_record.md` (c57844b). Clean non-overlap
20d blocks; OOS window unless noted.

## A. Weather gate (Round 5 restatement)

| Leg | ann | t | 90% CI |
| --- | ---: | ---: | ---: |
| ng raw | +3.20% | +0.52 | [-0.54, +1.05]% |
| ng gated | -0.59% | -0.11 | [-0.76, +0.66]% |
| crack_ho raw | -0.77% | -0.18 | [-0.63, +0.51]% |
| crack_ho gated | +0.15% | +0.04 | [-0.50, +0.53]% |

NG gate confirmed harmful (clean). HO: null either way.

## B1. Product-stock gate H1 (Round 6 restatement)

| Leg | ann | t | 90% CI |
| --- | ---: | ---: | ---: |
| crack_321 raw | +7.90% | +1.52 | [-0.05, +1.31]% |
| crack_321 gated | **+10.15%** | **+2.08** | **[+0.17, +1.44]%** |
| cross raw | +25.49% | +2.36 | [+0.61, +3.44]% |
| cross gated | +19.41% | +2.43 | [+0.50, +2.58]% |

REVISED: on clean blocks, de-risking crack_321 when product stocks
build (z >= 1) IMPROVES the leg (significant t=2.08, CI excludes
zero, while raw CI crosses zero). The old overlap-era verdict "H1
hurts" is overturned for crack_321. Cross is roughly neutral.

## B2. Natgas storage gate H2 (Round 6 restatement, 2010+)

| Leg | ann | t |
| --- | ---: | ---: |
| ng raw | +3.87% | +0.75 |
| ng gated | +0.97% | +0.19 |

Confirmed harmful (clean), both insignificant.

## C. Crash-put screen (Round 5 restatement)

Clean monthly blocks OOS: raw mean +0.86%/m (10.3%/yr), ov mean
+0.47%/m (5.6%/yr). A 4.1%/yr modeled crash-put premium is about
40% of the raw annual mean and 73% of the overlay annual mean.
Still uneconomic as a cost screen; the verdict does not depend on
window overlap.

## D. Joint crisis state and crush (Round 9 restatement)

- JOINT state (z<=-1.25 & crash5>=1.0 & crude20<=-15%): 6 days in
  the whole sample. Unmeasurable at non-overlap. The joint filter
  claims reduce into the crush claim.
- Crush state (z <= -0.75), non-overlap: OOS n=48 fwd20 +25.35%
  t=+2.65 CI [+9.6, +41.1]%; FULL n=56 +21.35% t=+2.57. The crush
  state itself HOLDS at the block level.

## Ledger updates

- Weather gate NG: FALSIFIED (clean; gated worse).
- Weather gate HO: NULL (clean; both zero).
- H1 product-stock gate on crack_321: REVISED to HELP (clean;
  t=2.08). Old kill overturned at the leg level. Open follow-up:
  test the H1 gate inside the champion book.
- H2 natgas gate on ng: FALSIFIED (clean; gated worse).
- Crash-put overlay: FALSIFIED (cost screen; premium 40-73% of mean).
- Crush state fwd20: HOLD at block level (OOS t=2.65, n=48).
- Joint crisis filter: CONSTRAINED (6 days); reduced into crush.

## Artifacts

- `direction2_harness.py`, `results/direction2.csv`
