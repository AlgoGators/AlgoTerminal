> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Derived-controls sweep (preregistered)

Test the alternative values for every derived control to find the
best working setup and understand WHY it wins. Selection rule:
choose on TRAIN only, never on VALIDATE or OOS/FULL. All windows are
reported for transparency, but the choice is TRAIN-based to avoid
selection on the holdout.

## Grid

| Control | Values |
| --- | --- |
| Entry bar (bin t-stat) | 1.0, 1.5, 2.0, 2.5, 3.0 |
| CB quantile (daily-loss pct) | 98.5, 99.0, 99.5, 99.9 |
| Per-trade budget (hard stop) | 1%, 2%, 3%, 5%, 7.5% |
| Trailing MAE percentile | 50, 65, 75, 85 |
| Cooldown (sessions) | 0, 2, 3, 5, 8 |

Scale stays BUDGET(10%) / ES5_train. Costs 5/20.

2000 configurations. Each config's numbers are derived on TRAIN
(curve per entry-t, quantiles per policy, MAE per entry-t), applied
everywhere.

## Selection and reporting

1. Compute TRAIN block t for every config.
2. Choose the config with the highest TRAIN t, subject to a plateau
   check: the top set must sit within 5% of the best TRAIN t (report
   the plateau).
3. Run VALIDATE, OOS, FULL for the chosen config (and the top-10 for
   context).
4. Mechanism analysis: why the chosen values win. Report per-control
   marginal effect by averaging TRAIN t over the other controls
   (entry-t marginal, CB marginal, budget marginal, trail marginal,
   cooldown marginal).

Acceptance for the chosen config: VALIDATE and FULL CIs exclude
zero; OOS t >= the OLD-controls OOS t (2.14). If the TRAIN-best
config fails out-of-window, report that honestly: it means the best
TRAIN setup did not generalize.

## Deliverable

findings/derived_controls_sweep.md. Ledger rows; all numbers
committed.
