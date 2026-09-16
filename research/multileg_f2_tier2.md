# Multi-leg F2 Tier 2 construction (preregistered)

Follows M1 (reassessment_probes): depth phenomenon confirmed monotone
(fwd20 7.3% to 16.3%). The M1 light construction improved Sharpe and
CAGR but the drawdown exploded (-94.8%) because three vol-targeted
legs stacked with up to 2x depth multipliers. This build adds
exposure scaling and tests the construction in the book.

## Construction

Cross legs: crack_321, crack_gas, crack_ho.
- Leg active when seasonal z <= -0.5 (v1 threshold).
- Per-leg depth multiplier while active:
  dm = clip(1 + K * (|z| - 0.5), 1, MAX_DM).
- Multiplier applied at t-1 (shift(1)).
- Per-leg vol scale: v1 fixed_vol_scale, VT_F2 = 0.50.
- Per-leg risk: v1 circuit breaker, hard stop, cooldown
  (trailing off, as v1 cross).
- Total notional cap: on each day, if sum(|pos_leg|) > CAP, scale
  every leg by CAP / sum(|pos_leg|). Applies after leg_risk.

## Variant grid (stated before measuring)

| ID | K | MAX_DM | CAP |
| --- | --- | --- | --- |
| V0 | 0.0 | 1.0 | 1.0 |
| V1 | 0.5 | 2.0 | 1.0 |
| V2 | 0.5 | 2.0 | 0.8 |
| V3 | 0.25 | 1.5 | 1.0 |

## Tests

1. Cross-leg net OOS raw stats per variant vs v1 single-most-crushed
   (reference: Sharpe 0.589, CAGR 18.32%, MaxDD -67.71%).
2. New book = crack_321 (v1 F1) + multiF2(variant) + bzwti (v1 F4),
   equal weight, vs champion book (raw 0.635, ov 0.862).
   Report IS/OOS raw and overlay.
3. Control: shuffle the depth multiplier ordering among active days
   (20 seeds) for V1; report OOS raw book Sharpe distribution vs
   the real V1 book.

Adoption rule: a variant joins the champion book only if it
improves OOS raw or overlaid Sharpe without worsening MaxDD by more
than 1 point at the book level and clears its shuffled control by
>= 2 sd at the cross-leg level.

## Deliverable

findings/multileg_f2_tier2.md. Chain ch30 status update.
