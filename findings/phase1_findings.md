> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Phase 1 findings — side structure (decision memo)

Date: this session. Harness: `phase1_harness.py`. Inputs: frozen
`engine/panel_v2.parquet`. Costs: 5bps/20roll. Preregistration:
`research/phase1_short_side.md`.

## Verdict

Kill the short-fade construction. Kill stretch-momentum. Kill the
balanced and split books. The v1 long-only design survives a direct
OOS test of its asymmetry claim.

## Results (OOS, overlay)

| Book | OOS Sharpe | OOS CAGR | OOS MaxDD | OOS vol | Worst |
| --- | ---: | ---: | ---: | ---: | ---: |
| A v1 long-only (reference) | 0.86 | 5.62% | -10.73% | 6.6% | -2.85% |
| B short-fade only | -0.08 | -0.37% | -11.23% | 3.7% | -3.81% |
| C balanced (A+B legs) | 0.31 | 1.31% | -11.69% | 4.5% | -3.20% |
| D split (left reversion + right momentum) | -0.31 | -0.92% | -16.03% | 2.8% | -6.26% |
| E right-momentum only | -0.28 | -0.65% | -11.14% | 2.2% | -4.85% |

## Behavior

- The short side is regime-conditional, in the OPPOSITE sign of the
  naive hypothesis.
- crack_short: OOS 2011-2014 (compression) -59.96%, IS 2023-2026
  (expansion) +11.48%.
- cross_short: OOS 2011-2014 -59.92%, IS 2023-2026 +12.49%.
- Stretch momentum: crack_mom lost in both windows (-31.33%, -28.74%).
  cross_mom won in 2011-2014 (+19.65%) and lost badly in 2023-2026
  (-38.42%).

## Mechanism

- The right tail does not persist under a threshold state machine, and
  it does not revert fast enough to pay after costs and stops.
- The short-fade profits exactly where long-only v1 already profits
  (2023-26 expansion). It adds return only when it is not needed, and
  bleeds twice when it is: no diversification.
- The v1 asymmetry is not an implementation artifact. The same engine,
  same sizing, same risk rules, with a symmetric short entry, produces
  a negative OOS book.

## Retained signal

- The short signal carries information: shuffled raw OOS Sharpe
  mean -0.457 sd 0.157 vs real -0.09. The construction is information-
  bearing but the information is not profitable after costs.
- A regime-conditional short (active only in expansion regimes) is the
  one untested variant. Recorded as a Phase 4 candidate, not built.

## Control

Time-shuffled short signals, 20 permutations, book B:
- Raw: mean -0.457, sd 0.157. Real -0.09.
- Overlay: mean -0.083, sd 0.168. Real -0.081. The overlay flattens
  both to zero: no edge survives.

## Scope

Falsified: short-fade on crack_321 and cross_sectional, stretch
momentum on both, balanced book, split book. All at v1-consistent
thresholds (+/-0.75 entry, +/-0.5 exit, per-leg risk, equal weight).

Not falsified: regime-conditional shorting, depth-dependent sizing of
the long side, product-level baskets (next phase), directional flow
features (phase 3), structural representation (phase 4).

## Next question

Does a multi-leg basket that holds every crushed leg at once (phase 2)
outperform the single most-crushed leg that v1 holds?

## Artifacts

- `phase1_harness.py` — side-leg builders, books A-E, regime drill,
  negative control.
- `results/phase1_results.csv` — full grid.
