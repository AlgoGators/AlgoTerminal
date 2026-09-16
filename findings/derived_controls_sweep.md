# Derived-controls sweep — INVALID (reproducibility failure)

Date: this session. Harness: `sweep_controls_harness.py`,
`sweep2_harness.py`. Prereg: `research/derived_controls_sweep.md`
(02e08ba).

## What happened

The sweep could not reproduce its own anchor configuration. The
verified base harness produced TRAIN t = +1.11 for
(t=2.0, cb=.99, budget=.02, trail=.75, cool=3). The sweep harness,
with nominally identical settings, produced TRAIN t = +0.00 (flat
book). When a parameter sweep cannot reproduce the base result for
the same configuration, every ranking it produces is untrustworthy.

## Result

- 243-config grid and the earlier 2000-config grid are recorded as
  INVALID. Do not use their rankings.
- The partial CSV files are kept only as evidence of the failure.
- No selection, no marginals, no findings were taken from them.

## Likely causes (candidates, not confirmed)

- The grid builder recomputes the curve, w, CB base, and MAE with
  small differences from the verified harness (h1 shift timing,
  relnorm median normalization, entry list construction).
- The derived_risk custom loop is stateful and sensitive to the
  exact input series; a difference that leaves the book flat on
  TRAIN for the anchor indicates a real discrepancy, not a ranking
  artifact.

## The reproducibility bar (rule added)

Any parameter sweep must FIRST reproduce the base harness result for
its anchor configuration. If the anchor t differs materially, the
sweep is invalid and must be fixed before any ranking is reported.
This failure is now part of the ledger as a methodological rule.

## Next step (correct order)

1. Extract the position/risk builder from the verified harness into
   one shared function used by BOTH the base run and the sweep.
2. Reproduce the anchor (TRAIN t ~ 1.11).
3. Re-run the grid only after the anchor reproduces.
4. Rank on TRAIN, confirm on VALIDATE/OOS/FULL, report marginals.

## Artifacts

- `sweep_controls_harness.py`, `sweep2_harness.py`
- `results/sweep_grid.csv`, `results/sweep2_grid.csv` (invalid,
  kept as evidence)
