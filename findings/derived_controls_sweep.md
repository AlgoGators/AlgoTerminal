> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Derived-controls sweep — corrected results

Date: this session. Harness: `sweep3_harness.py` (single-builder).
Prereg: `research/derived_controls_sweep.md` (02e08ba).
Supersedes the invalid sweep records (acdd00d). The reproducibility
bar held: anchor reproduced exactly (TRAIN t = +1.11).

## The bug that was fixed

The circuit-breaker sign was double-negated in the grid builder
(cb became negative, so `-cb_thresh` was positive and every held day
fired the stop, flattening the book). One-line fix: cb = positive
level percentile, same as the verified harness.

## TRAIN-selected config (selection on TRAIN only)

t-entry 1.5 (zcut -0.45), CB quantile 0.99-0.999, per-trade budget
7.5%, trail 85th MAE percentile, cooldown 3.

| Window | t | CI excludes 0 at 90%? |
| --- | ---: | --- |
| TRAIN | +3.64 | yes |
| VALIDATE | +1.61 | borderline (touches 0) |
| OOS | +3.96 | yes |
| FULL | +3.66 | yes |

## Deep comparison: old controls vs swept-derived

| Item | Old (picked) | Swept-derived choice | Why it wins (marginals) |
| --- | --- | --- | --- |
| Entry bar | t>=2 equivalent / 5% | **t>=1.5, zcut -0.45** | entry-t marginal: 1.5 (+2.86) vs 2.0/2.5 (+1.79). Trading shallower crushes captures more reversion days with better aggregate t |
| CB quantile | 3 sigma | 99-99.9th (any) | CB marginal flat (+2.15 across): the derived CB (11-14% level) rarely fires at any tested quantile; the CB is effectively inactive at this scale |
| Per-trade budget | 20% | **7.5%** (distance ~16%) | budget marginal: 7.5% (+2.51) > 5% (+2.47) > 2% (+1.46). The old 20% was directionally right; the earlier 2% default was wrong (too tight) |
| Trailing percentile | 1.25 sigma | **85th MAE** | trail marginal: 85th (+2.28) > 75th (+2.26) > 65th (+1.90). Looser trail preserves winners |
| Cooldown | 5 days | **0-3 days** | cool marginal: 0 (+2.50) > 3 (+2.22) > 5 (+1.72). Long cooldowns destroy whipsaw-recovery |

Result versus the old-controls construction:
- OOS t 3.96 vs 2.14; FULL t 3.66 vs 2.31 (clean blocks).
- The largest lever was the entry bar (trade shallower, more days);
  the stops' old values were directionally sane as loose disaster
  caps, and the sweep confirms loose stops (7.5-16% distance, loose
  trail) beat tight ones.

## Honest caveats

- VALIDATE remains borderline (t 1.61, 90% CI touching zero) — the
  same persistent out-of-window weakness.
- Selection is TRAIN-based by the prereg rule; the top-10 plateau is
  tight (TRAIN 3.45-3.64), so the choice is not a spike.
- CB being inactive means the derived CB is not meaningfully
  binding; an explicit daily-loss-budget policy (e.g., book loss
  cap) is the cleaner design than a level-percentile CB.
- Costs still assumed 5/20; standard lookup pending.

## Ledger

- Sweep bug (CB sign) found and fixed; reproducibility bar validated.
- Swept-derived controls: HOLD on OOS/FULL (t 3.96/3.66), VALIDATE
  borderline. Chosen config: entry t=1.5, budget 7.5%, trail 85th,
  cool 0-3, CB inactive.
- Old control values replaced by data-chosen values; marginals give
  the mechanism.

## Artifacts

- `sweep3_harness.py`, `results/sweep3_grid.csv`, `results/sweep3_top10.csv`
