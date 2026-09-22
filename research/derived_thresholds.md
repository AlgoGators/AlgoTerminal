> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Derived thresholds — remove the 0.75/-0.5 remnants (preregistered)

The 0.75/-0.5 entry/exit thresholds are v1 plateau picks. Our own
rule says constants come from shapes. This pass derives the trading
function from the data and removes the thresholds entirely.

## Method (stated before measuring)

1. TRAIN window: 2007-01-01 .. 2018-12-31.
2. On comp/norm regime days (R2, 504d median/MAD), estimate the
   smoothed conditional-mean curve E[fwd20(crack_321) | z] over
   24 z-bins in [-4.0, 1.5], rolled with a 5-bin window, TRAIN only.
3. Define the exposure function (applied everywhere, causal):
   - w(z) = clip( curve(z) / max(curve), 0, 1 ), where curve(z) <= 0
     maps to 0.
   - Position = w(z) * vol-target (VT_F1), capped 1.0, per-leg risk.
   - H1 de-risk (product stocks z >= +1) stays (storage revision).
   - Regime gate stays (comp/norm only; exit on flip).
   - ES gear 0.365 stays (mixture-derived).
4. The entry/exit thresholds and the state machine are GONE. The
   function is continuous and reads entirely from the TRAIN curve.

## Curves to report

- The derived curve (z_bin -> E[fwd20]) with the zero crossing (the
  natural entry line) and the max (the scaling base).
- Also P(fwd20 > 0 | z) to state the win probability at the line.

## Evaluation

Clean non-overlap 20d blocks: TRAIN, VALIDATE (2019-2026, never
used to derive), OOS (2007-2023), FULL. Acceptance:
- VALIDATE and FULL CIs exclude zero;
- OOS mean >= B1h-with-old-thresholds OOS mean;
- DD reported with the gear (compare vs champion overlay ~ -10.7%);
- negative block fraction reported.

## Deliverable

findings/derived_thresholds.md. Ledger update:
thresholds removed; replacement = curve-derived exposure function.
