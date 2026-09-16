# Shape pass — seasonal-norm audit and conditional-mean curves

Date: this session. Harness: `shape_harness.py`.
Method: research/self_assessment.md. Constants are read from the
empirical shape, not picked.

## Assumption audit (crack_321)

| Assumption | Result | Verdict |
| --- | --- | --- |
| A3 mean is the right statistic | mean-median gap up to +3.63 (3 months) | FALSE-ish |
| A4 intra-month homogeneity | early vs late delta +0.41 | mild |
| A5 stable variance | std 3.40 -> 6.75 -> 4.29 -> 12.41 across decades | FALSE |
| A6 additive seasonality | corr(monthly mean, std) = +0.448 | MULTIPLICATIVE component |
| A8 Gaussian residuals | skew +1.61, kurtosis 3.30 | FALSE |
| A2 calendar is the carrier | calendar months spread 19.4% vs temperature deciles 15.7% on fwd20 | CALENDAR + WEATHER are comparable carriers |

The seasonal norm's assumptions do not hold. The same-month expanding
mean with std normalization is a rough summary, not a model.

## The regime-conditional z-shape (the main finding)

E[fwd20 of crack_321 | seasonal-z bucket] split by regime:

Expansion:
- deep crush [-8,-1.5): -10.4% (n=24), [-1.5,-0.75): -1.4% (n=172)
- normal [-0.25,0.25): +3.9%
- stretched [0.75,1.5): -2.2%, [1.5,8): -6.0%

Compression:
- deep crush [-8,-1.5): +14.8% (n=491), [-1.5,-0.75): +14.4% (n=503)
- normal [-0.25,0.25): -1.4%
- stretched [0.75,1.5): +3.8%, [1.5,8): +2.9%

Consequences:
- The LONG-crush edge is primarily a compression-regime phenomenon
  (+14.4..+14.8% in compression; flat-to-negative in expansion).
- The SHORT-stretch edge is an expansion-regime phenomenon
  (-2.2..-6.0% in expansion; positive in compression) — P5 extended.
- The asymmetry is regime-conditional on BOTH sides. Each regime has
  its own tradeable side. This is the seasons-as-regimes structure
  the captain asked for, in its first data pass.
- Caveats: regime definition is trailing 252-day mean (a construct);
  deep-crush expansion cell is small (n=24). Regime estimation from
  data is the next step.

## Other shapes

Season curve (E[fwd20 | month]): strong structure, Feb +27.5%,
Aug -13.5%, winter months strongly positive. The calendar component
is real and not flat within months.

Depth curve (E[fwd20 | crush depth], z <= -0.5): rising with depth
with spikes (d4 +18.0%, d9 +19.0%; d0 +7.6%). Confirms M1 monotone
depth and gives the curve to read sizing from.

## Constants now readable from data

- Long entry: compression regime, z where E[fwd20|z,compression]
  turns strongly positive (about z <= -0.75 in this data).
- Long entry should NOT be used in expansion deep crush (sign flips).
- Short entry: expansion regime, z >= +0.75 where
  E[fwd20|z,expansion] turns negative.
- Seasonal norm: replace with regime-conditional shapes; test median
  and multiplicative forms.
- Carrier: temperature deciles carry nearly as much as calendar
  months; cold severity belongs inside the seasonal component.

## Artifacts

- `shape_harness.py`, `results/shape_pass.csv`
- `research/self_assessment.md`, `research/regime_model.md`
