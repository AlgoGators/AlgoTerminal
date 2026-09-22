# Superseded result artifacts

Every summary CSV listed here was produced BEFORE the 2026-09-22 artifact
audit. Their Sharpe / return statistics are FALSIFIED and must not be cited.

Reasons: the price panel is yfinance raw front-month (NOT back-adjusted), so
the March contract-roll artifact alone was 40.2% of the measured P&L; the H1
gate used current-vintage instead of as-published storage data; the
fixed-control walk-forward was in-sample for its controls across 2012-2018;
and the assumed 5 bps/side cost is 3.2-4.8x too low.

Authoritative, current artifacts:
- `results/walkforward_series.csv`, `walkforward_causal_series.csv`
- `results/spot_fixed_series.csv`, `spot_causal_series.csv`
- `results/wf_crush_futures_series.csv`, `wf_crush_spot_series.csv`
- comparison table: `python scripts/artifact_audit.py`

Record: `findings/artifact_audit.md`, `findings/claims_ledger.md`.

## Superseded summary files

- `results/comparison_drawdown_measures.csv`  (4 rows)
- `results/direction1.csv`  (12 rows)
- `results/direction4.csv`  (19 rows)
- `results/final_strategy.csv`  (20 rows)
- `results/metrics_final.csv`  (4 rows)
- `results/multileg_f2_tier2.csv`  (5 rows)
- `results/next_direction.csv`  (9 rows)
- `results/phase1_results.csv`  (26 rows)
- `results/phase1r_results.csv`  (20 rows)
- `results/phase3_results.csv`  (28 rows)
