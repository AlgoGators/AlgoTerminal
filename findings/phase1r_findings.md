> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Phase 1R findings — mechanism-based short side (decision memo)

Date: this session. Harness: `phase1r_harness.py`. Inputs: frozen
`engine/panel_v2.parquet`. Costs: 5bps/20roll. Preregistration:
`research/phase1r_short_side_mechanics.md`. Supersedes the Phase 1
mirror test for the short side.

## Verdict

All four mechanism-based short candidates fail as standalone books.
S3 survives as a weak positive signal with control support, and is
retained only as a conditional feature for Phase 3. No short leg meets
the combination rule (independently positive and robust OOS), so the
v1 long book remains the champion.

## Results (OOS)

| Cand | Leg / Book | Sharpe | CAGR | MaxDD | Worst |
| --- | --- | ---: | ---: | ---: | ---: |
| S1 easing-fade | crack | -0.25 | -4.92% | -69.95% | — |
| S1 | cross | -0.02 | -1.71% | -60.69% | — |
| S1 | book ov | -0.00 | -0.03% | -10.14% | -3.71% |
| S2 acceleration-ride | crack | -0.31 | -11.25% | -86.18% | — |
| S2 | cross | -0.46 | -31.54% | -99.79% | — |
| S2 | book ov | -0.07 | -0.26% | -11.08% | -9.70% |
| S3 regime-conditional | crack | -0.24 | -4.90% | -60.68% | — |
| S3 | cross | +0.14 | -0.55% | -75.90% | — |
| S3 | book ov | +0.16 | +0.50% | -11.31% | -4.18% |
| S4 seasonal-top fade | crack | -0.30 | -4.50% | -64.71% | — |
| S4 | cross | +0.06 | -1.90% | -59.67% | — |
| S4 | book ov | -0.00 | -0.04% | -10.00% | -3.74% |

Reference for comparison: v1 long-only book OOS ov Sharpe 0.86.

## Behavior

- Inflection fades (S1) and seasonal-top fades (S4) are flat-to-negative.
  The stretch does not give up its level to those triggers.
- Raw momentum on the stretch (S2) is the worst construction. The
  acceleration condition latches into the deepest drawdowns (-86% to
  -99% raw leg drawdowns).
- The regime-conditional short (S3) is the only candidate with a
  positive cross leg (+0.14) and a positive book (+0.16). Its edge
  lives in the expansion regime, matching the Phase 1 drill where
  shorts paid only in 2023-26.

## Mechanism

- The easing and calendar triggers are too early. Stretched margins
  keep their level while tightness persists; they do not roll over on
  a 5-day z turn or on the calendar shoulder.
- Regime conditioning is the only addition that changes the sign. The
  tightness-easing trade needs a regime filter, not a price shape.
  This is the one retained mechanism.

## Retained signal

- S3 cross (short most-stretched leg, expansion regime): OOS Sharpe
  +0.14 standalone, book +0.16, drawdown -11.31% under overlay.
- Negative control: S3 real 0.165 vs shuffled mean -0.104 sd 0.154
  (about 1.75 sd above shuffled). Weak information, not noise, but far
  below the 0.86 champion and below the 0.50 acceptance floor.
- Direction for Phase 3: physical-data variant of the regime-
  conditioned short (utilization-pinned tops, inventory-rebuild fades)
  was preregistered there. The regime filter is the part that works.

## Control

Time-shuffled signals, 20 permutations, OOS overlaid:
- S1: real 0.000 vs mean -0.103 sd 0.182.
- S2: real -0.070 vs mean -0.219 sd 0.198.
- S3: real 0.165 vs mean -0.104 sd 0.154.
- S4: real -0.001 vs mean -0.074 sd 0.197.

Only S3 separates from its shuffled baseline.

## Scope

Falsified as standalone books: easing-fade, acceleration-ride,
seasonal-top fade, and regime-conditional short as a book.

Not falsified: regime-conditioning as a feature (S3), and the physical
data variants deferred to Phase 3.

## Next question

Can physical flow data (utilization pins, inventory rebuilds) lift the
regime-conditional short past the acceptance floor? Phase 3 tests this.

## Artifacts

- `phase1r_harness.py` — optimized harness, precomputed level stats.
- `results/phase1r_results.csv` — legs, books, controls.
