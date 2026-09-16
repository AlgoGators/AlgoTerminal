# Component audit — close the remaining leaks (preregistered)

The strategy still carries inherited assumptions. This pass fixes
the clear leaks and measures whether the rebuilt norm matters.

## 1. Gear lookahead fix (ES5 from TRAIN only)

ES5 of the crush-state fwd20 is re-estimated on TRAIN only
(2007-2018). gear_train = 10% / ES5_train. Re-run Bar5 on
TRAIN/VALIDATE/OOS/FULL and compare with the old full-sample gear.

## 2. Rebuilt norm variant (median + robust scale)

z_new = (level - same-month expanding median) / same-month robust
std, clipped. Derive the conditional-mean curve on TRAIN using z_new
(24 bins, same 5% bar), same regime gate, H1, gear.
Report TRAIN/VALIDATE/OOS/FULL clean blocks.
Decision rule: adopt z_new if its VALIDATE and FULL CIs exclude
zero and its OOS t is within 0.3 of the old-norm variant; otherwise
keep z_old with the tradeoff documented (no more "power excuse").

## 3. Audit ledger labels

Correct the record: the 5% bar and w normalization are ANCHORS (not
derived); only the curve shape, regime identity, H1 threshold, and
the TRAIN-based gear are data-derived.

## Deliverable

findings/component_audit.md. Ledger corrections.
