> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Batch 1 findings — alpha source map, cheap items

Date: this session. Harness: `batch1_harness.py`. Inputs: frozen panel,
EIA weekly, NASA POWER NYC/HOUSTON T2M. Preregistration:
`research/batch1_alpha_map.md` (committed c322410, before measuring).

## Verdicts by source

| Source | Result | Status |
| --- | --- | --- |
| 1 winter maintenance | No edge as constructed | TESTED-kill-construction |
| 2 cold-weather vehicle demand | Weak positive on gasoline crack, negative on HO crack | TESTED-keep (weak, conditional-only) |
| 3 fuel blends | Real effect, negative direction: blend windows are low-edge, high-vol | TESTED-keep (as de-risk signal) |
| 7 norm drift | Large drift confirmed | ANSWERED (adaptive norm required) |
| 11 correlations | Rechecked | ANSWERED |
| 9/10 multi-crush basket + depth | Product-level basket and depth fail | TESTED-kill-construction (one variant open) |

## M1 — winter maintenance calendar

Construction: maintenance month = same-month expanding utilization mean
at least 1.0 point below the expanding annual mean; scale crack longs
1.25, else 1.0.

- Real ov 0.833 vs champion 0.862.
- Inverted 0.851. Shuffled mean 0.822, sd 0.040. Real is about 0.3 sd
  above shuffled. No information.

Verdict: killed as constructed. The ex-ante utilization calendar does
not separate maintenance supply events from what the price already
knows.

## M2 — cold-weather vehicle demand (NYC T2M)

Event study, crack forward returns after cold winter days (same-month
T2M z <= -1.0) vs other winter days:

| Leg | Horizon | Cold mean | Non-cold mean | Diff |
| --- | --- | ---: | ---: | ---: |
| crack_gas | 10d | +13.58% | +10.23% | +3.35% |
| crack_gas | 20d | +27.03% | +21.54% | +5.49% |
| crack_ho | 10d | -2.19% | +1.04% | -3.23% |
| crack_ho | 20d | -1.20% | +1.90% | -3.10% |

Control (crack_gas fwd10): real +13.58% vs shuffled +10.90% sd 1.95%.
Real is about 1.4 sd above shuffled. Weak but directionally consistent
with the captain's mechanism: cold weather supports gasoline demand.
The HO leg moves the opposite way, which creates a relative signal.

Verdict: keep as a weak conditional feature. Natural next variant: a
relative tilt (gasoline up, distillate down) after cold spells. Not
adopted alone.

## M3 — fuel blend windows

Blend windows (spring Mar 20-Apr 15, fall Sep 1-30):

| Bucket | n | z mean | fwd20 | realized vol |
| --- | ---: | ---: | ---: | ---: |
| In-window | 738 | +0.229 | +1.79% | 229.8% |
| Out-window | 4057 | +0.098 | +6.82% | 144.7% |

Control (in-window fwd20): real +1.79% vs shuffled +6.30% sd 1.31%.
Real is about 3.4 sd BELOW shuffled. The blend windows are genuinely
lower-edge, higher-volatility periods.

Verdict: real effect, negative direction. The blend transition is a
period to reduce reversion exposure, not to add it. If used, it is a
de-risk window, requiring one preregistered confirmation.

## M7 — norm drift

crack_321 monthly means rose roughly +4 to +8 dollars per barrel from
2007-2015 to 2016-2026 (e.g., January 15.85 to 18.77, July 19.52 to
27.71, October 14.08 to 20.53). Utilization mean rose 87.24 to 89.38.
Seasonal std also widened in summer months.

Verdict: the stable-seasonal-norm assumption is false in level. The
same-month expanding mean lags a structural upward drift. Adaptive or
drift-corrected normalization is a Phase 4 requirement, not an option.

## M11 — correlations (corrected net returns)

| Pair | IS | OOS |
| --- | ---: | ---: |
| crack_321 vs cross_sectional | 0.301 | 0.338 |
| cross_sectional vs crack_ho | 0.344 | 0.308 |
| crack_321 vs crack_ho | 0.181 | 0.183 |
| crack_321 vs bzwti | 0.040 | 0.028 |
| cross_sectional vs bzwti | 0.154 | -0.312 |
| ng vs others | -0.045..0.175 | -0.059..0.078 |

Verdict: the book is two bets. crack_321 and cross_sectional are the
crack-complex bet (0.34 OOS). bzwti is the diversifier, most useful
against cross (-0.31 OOS). The mattrice confirm the Round 3 honest
correlations and the v2 driver map.

## M9 — multi-crush basket + depth

| Book | OOS raw Sh | OOS raw DD | OOS ov Sh | IS ov Sh |
| --- | ---: | ---: | ---: | ---: |
| Champion (crack_321 + cross + bzwti) | 0.635 | -29.79% | 0.862 | 1.126 |
| Basket flat (crack_gas + crack_ho + bzwti) | 0.140 | -43.49% | 0.007 | 0.942 |
| Basket depth (clipped depth sizing) | 0.110 | -45.93% | -0.010 | 0.973 |

Depth control: real ov -0.010 vs shuffled 0.017 sd 0.035. No depth
information in this construction.

Verdict: product-level legs are much worse than the 3:2:1 + cross
structure. The captain's instinct (multiple crushes concurrently) is
partly covered already: the champion holds F1 (crack_321) and F2
(cross_sectional) at the same time. The untested variant is a
multi-leg F2 (hold all crushed cross legs by depth) inside the
existing structure, not a product-level replacement.

## Retained for later phases

1. Cold-weather relative tilt (gas up, HO down after cold spells).
2. Blend-window de-risk (needs one confirmation run).
3. Adaptive seasonal norm (Phase 4 requirement).
4. Multi-leg F2 with depth weighting (variant of source 9/10).

## Artifacts

- `batch1_harness.py`
- `results/batch1_correlations_IS.csv`, `batch1_correlations_OOS.csv`
- `results/batch1_cold.csv`, `results/batch1_drift.csv`
- Statuses updated in `research/alpha_source_map.md`
