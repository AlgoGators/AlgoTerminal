# Direction 3 — the deep model (preregistered)

Sub-items, methods fixed before measuring. All forward evaluation is
causal at state date; regime identity fit uses the full sample as a
research construct and is flagged as such (trading would re-fit
causally).

## A. HMM regime identity

Custom 3-state Gaussian HMM (EM, kmeans init via sklearn) on the
standardized deseasonalized crack_321 level. Decode via Viterbi.
Name states by mean obs (comp/norm/exp). Report:
- state occupation,
- E[fwd20] by (HMM state x margin state), non-overlap 20d blocks,
- compare the long-crush rule under HMM vs R2 regime definition
  (same rule card: crush in comp/norm): n, t, 90% CI on OOS.

## B. Rebuilt seasonal norm

Replace the flawed norm:
- level norm = same-month EXPANDING MEDIAN (robust to drift and
  skew), 
- scale = trailing 2y robust std by month,
- z_new = (level - month_median) / month_robust_std, clipped,
- temperature co-carrier: residual correlation with NYC T2M z, and
  the cold-severity cell under the new z.
Report: crush/stretch counts under new vs old z; E[fwd20] in the
crush state under new z (non-overlap, t, CI on OOS); change vs old.

## C. Demand/supply/tech estimates (first numbers)

- Utilization 10-year drift (slope per decade).
- Seasonal amplitude trend of crack_321 (per-year std of same-month
  deviations; slope) as the EV/efficiency dilution proxy.
- Product stock mean drift (gasoline+distillate trend).
- Temperature demand link already measured (P1); report the
  coefficient of cold z in the margin residual regression.

## D. Mixture forward model

2-component Gaussian mixture on the fwd20 distribution in the crush
state: weights, means, stds; P(fwd20 > +10%); expected shortfall
at 5%. Same for the normal state. Sizing inputs come from these
shapes.

## Deliverable

findings/direction3.md. Ledger additions.
