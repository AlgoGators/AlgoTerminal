# Model book — from-scratch strategy from mechanism findings (preregistered)

The champion was built on the incomplete base and is a remnant. This
book is built from the ledger's clean findings and their mechanisms,
not from the old construction. Factors are tested individually and
kept only if they hold with clean non-overlap statistics.

## Factors (each with its mechanism anchor)

F1 regime-gated crush (crack_321):
- Entry seasonal z <= -0.75 only when R2 regime in {comp, norm};
  exit z >= -0.5 or immediate exit when regime flips to exp.
- Mechanism: crushed margins revert via capacity exit and seasonal
  demand return, which are compression/normal behaviors. Expansion
  crush does not pay (shape pass; clean raw t 2.94).
- Sizing VT_F1, per-leg risk (trailing), 1.0 cap.

F2 multi-leg breadth (product legs crack_gas, crack_ho):
- Hold every leg with seasonal z <= -0.75; per-leg risk; depth
  multiplier NOT used (redundant after caps); total cap 0.8.
- Mechanism: concurrent crushes carry simultaneous reversion; depth
  monotone (M1) but redundant after notional caps (Tier2).
- Sizing VT_F1 per leg, cap total 0.8.

F3 Brent-WTI reversion (bzwti):
- v1 F4 two-sided reversion.
- Mechanism: Cushing logistics weaken/revert the basis. Weak alone,
  held as the book diversifier (2-bet book; clean correlation).

F4 storage buffer tilt (variant):
- Inside F1/F2, position multiplier 0 when product-change same-month
  z >= +1 at t-1 (H1 gate, clean leg-level revision).
- Mechanism: building inventories are the physical damper; margin
  pressure precedes weaker reversion.

## Construction

No V2 ladder. Risk comes from the mixture shapes:
- crush-state forward mean ~+11.7% / std ~27% / ES5 ~-27% (traded
  at the vol-targeted size, caps at 1.0).
- Reporting must state raw drawdown honestly; the overlay is not a
  component.
Costs 5/20 (10/20 sensitivity). Equal-weight three sleeves:
base = F1 + F2 + F3.

## Variants and evaluation

Per-Factor clean blocks (OOS/FULL): mean, t, 90% CI. Drop factors
whose OOS CI includes zero.
Books:
- B1 = F1 + F3 (no breadth)
- B2 = F1 + F2 + F3 (breadth)  [candidate]
- B3 = B2 + F4 (storage tilt)
Acceptance: candidate OOS and FULL raw block CIs exclude zero; OOS
mean >= F1-alone mean; report raw DD, worst block, neg-block
fraction, and the mixture-ES context. No overlay comparisons: this
book replaces the ladder by design.

## Deliverable

findings/model_book.md. Ledger rows.
