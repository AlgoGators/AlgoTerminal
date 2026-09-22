> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Derived controls — replace picked numbers with data-derived ones (preregistered)

Every function stays; the arbitrary magnitudes are read from TRAIN
distributions implementing stated policies.

## D1 — significance bar (replaces 5%)

Cutoff = the largest z whose TRAIN bin t-stat (E[fwd20]/bin SE) >= 2.
The bar percentage disappears.

## D2 — unified scale (replaces VT 0.50 and MAX_LEV 1.0)

size = w(z) x relative_vol_norm x SCALE, cap = SCALE,
where SCALE = BUDGET / ES5_crush_train (= 0.10 / 0.219 ~ 0.457).
relative_vol_norm divides by trailing vol (risk equalization) with
no arbitrary target. No 0.50, no 1.0.

## D3 — stops read from TRAIN distributions

- Circuit breaker: flatten when the day's loss is worse than the
  empirical 99th percentile of the held-day book daily returns
  (TRAIN). Policy: "flatten on a day worse than 99% of crush-state
  days."
- Hard stop: exit when the level has moved against entry by
  per_trade_budget / |position|, per_trade_budget = 2% of book
  (named anchor). No 20%.
- Trailing: distance = 75th percentile of max-adverse-excursion on
  winning crush trades (TRAIN). The sigma multiple is an output.
- Cooldown: median days until the tail exits after a stop event
  (TRAIN). Whatever the data says.

## D4 — window/clip plateau

Sweep SMR_Z_LOOKBACK 60/90/120/180 and clip 6/8/10/12 on the derived
construction. Report OOS/FULL t. Pick the mid-plateau.

## Comparison

The same construction runs twice: OLD (5% bar, VT 0.50, cap 1.0, 3s/20%/1.25s/5 stops) vs NEW (D1-D3). Report TRAIN/VALIDATE/OOS/FULL blocks for both. The honest comparison table lists every item, its old value, its new value, and the measured difference.

Costs stay 5/20 (assumed; standard lookup pending).
Acceptance: NEW VALIDATE and FULL CIs exclude zero; NEW OOS t >= OLD OOS t.
