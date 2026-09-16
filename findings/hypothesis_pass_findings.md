# Hypothesis pass — Tier 1 phenomenon evidence

Date: this session. Harness: `hypothesis_harness.py` (buckets, no
positions, no costs, no overlay). Rule: `research/hypothesis_first.md`.

## Verdicts

| Test | Phenomenon | Shape | Tier 1 verdict |
| --- | --- | --- | --- |
| P1 cold severity (NYC HDD) | Present, winter-monotone | Coldest winter quintile +26.6% fwd20 vs warmest winter quintile +15.2% | PRESENT (representation, not phenomenon, was weak) |
| P2 blend switch distance | Present, negative | dist<=7 +1.7%, 8..21 -3.1%, >21 +8.3%; vol 16/12/9% | PRESENT (de-risk window is real, extends ~3 weeks) |
| P3 product change z (crush state) | Absent | Non-monotone; builds +9.7% vs draws +10.1% | ABSENT (Tier 1 closes the building tilt) |
| P4 utilization seasonal position | Absent | Non-monotone | ABSENT at this granularity |
| P5 stretched margins by regime | Present, strong | Expansion -4.09% fwd20, compression +3.52%; control delta 4.7 sd | PRESENT STRONG (Phase 1R killed a representation, not the idea) |
| P6 CDD z | Absent | Non-monotone, negative | ABSENT / proxy-poor |
| P7 crude glut vs bzwti | Proxy-poor | U-shaped extremes | PROXY-POOR (extremes mean-revert; not glut-specific) |

## Detail

### P1 — cold severity (source 2)

Winter-forward gasoline-crack returns are monotone in NYC HDD z:
- warmest winter quintile +15.2%, coldest quintile +26.6% (fwd20).
- The all-days shape is U-shaped; the winter-only shape is monotone.
- HDD 5-day onset is weakly monotone (+19.9% to +25.1%).
- Houston HDD is U-shaped, not monotone. Demand-center geography
  (NYC) is the right measurement.
- Control (top-minus-bottom vs random slices): +11.4% vs +6.68%,
  sd 1.32%.

The Batch 1 binary cold test understated this. The conditional value
is cold SEVERITY within winter at the demand center. Phase 4 feature.

### P2 — blend switches (source 3)

Within 7 days of a switch, fwd20 drops to +1.7% with 16% vol. Days
8-21 after are -3.1%. Outside, +8.3% with 9% vol. The reversion edge
is suppressed for about three weeks around each switch. This confirms
and extends the Batch 1 de-risk finding: the window is real and
measurable.

### P3 — product stock changes (sources 6/10)

In the crush state, forward returns are high at BOTH extremes
(draws +10.1%, builds +9.7%) and lower mid-range. No monotone
relationship. The building tilt is now killed at Tier 1. The Batch 2
book effect was overlay interaction, as suspected.

### P5 — stretched margins by regime (source 8)

The most important finding of the pass:
- Stretched margins in EXPANSION decline -2.35% (fwd10) and -4.09%
  (fwd20).
- Stretched margins in COMPRESSION RISE +0.13% and +3.52%.
- Control: expansion-minus-compression delta -7.62% vs shuffled
  -0.48%, sd 1.53%. About 4.7 standard deviations.

Phase 1R's S3 was directionally right and numerically weak (0.16)
because the representation was wrong, not the idea. The phenomenon is
one of the strongest in the whole study. A 10-20 day hold with the
regime gate is the Phase 4 construction.

### P6 — cooling degree days (source 4)

Non-monotone, mostly negative. The load proxy shows no margin
conditioning. Killed at Tier 1.

### P7 — crude glut (source 12)

Both crude-stock extremes show large positive fwd20 changes in the
spread (+17.4%, +17.7%). That is generic basis mean reversion at the
extremes, not glut-specific monotone conditioning. Proxy-poor; the
composition question stays constrained.

## Revisions to earlier verdicts

- Item 2 cold weather: weak -> phenomenon PRESENT, winter severity
  monotone. Machine understated it.
- Item 8 short side: weak -> phenomenon PRESENT STRONG (4.7 sd).
  The regime-conditional short is back on the Phase 4 table with a
  proper representation.
- Item 6 building tilt: weak-retained -> ABSENT at Tier 1. Closed.
- Item 1 maintenance: killed -> confirmed absent at Tier 1.
- Item 4 load: killed -> confirmed absent at Tier 1.
- Item 12 glut proxy: killed -> proxy-poor, extremes mean-revert.

## Outcome

The hypothesis-first method changed verdicts in one pass. The short
side has the strongest phenomenon in the study. That is exactly the
kind of finding the previous pipeline would have reported as "no
edge."

## Artifacts

- `hypothesis_harness.py`
- `results/hypothesis_pass.csv`
- Domain rule: `research/hypothesis_first.md`
