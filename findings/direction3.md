> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Direction 3 — the deep model (findings)

Date: this session. Harness: `deep_model_harness.py` (custom
3-state Gaussian HMM, sklearn kmeans init). Prereg:
`research/direction3_deep_model.md` (e896122).

## A. HMM regime identity (causal conditioning, full-sample identity)

- Occupation: comp 2216, norm 1173, exp 1078.
- Transitions sticky: comp->comp 0.990, norm->norm 0.991,
  exp->exp 0.975.
- Long-crush rule under HMM (non-overlap OOS blocks):
  - HMM comp x crush: n=28, fwd20 +30.20%, t=1.93,
    CI [+4.5%, +55.9%].
  - HMM comp+norm x crush: n=40, fwd20 +23.71%, t=2.12,
    CI [+5.3%, +42.1%].
- Comparable to the R2-based L rule; the HMM comp cell has a higher
  mean and fewer days. Clean support under both identities.

## B. Rebuilt seasonal norm (median + robust scale)

- Crush days old 1193 -> new 494; stretch 1488 -> 2082. The
  median-based norm is stricter about what counts as crushed, looser
  about stretched.
- Crush under the new norm: OOS n=17, fwd20 +35.58%, t=1.38 (wide
  CI) vs old norm n=56, +21.35%, t=2.57. The rebuilt norm confirms
  the edge direction but at far less power; the old norm holds
  statistically better with its larger cell.
- Temperature co-carrier in the level residual: corr +0.107 with NYC
  T2M z. Small, positive, consistent with P1.

## C. Supply/demand/tech first numbers

- Utilization slope +0.25 pts/yr (last decade +2.66): refining
  supply ratcheting up.
- Seasonal amplitude slope +0.257 pts/yr: seasonality has INCREASED
  over the sample (recent high-margin volatile era dominates), not
  declining as an EV-dilution story would predict. Needs the longer
  lens.
- Product stocks drift +9,769 over 2007-2026: modest storage growth.

## D. Mixture forward model (fwd20 distribution shapes)

Crush state (new norm):
- 2 components: w [0.03, 0.97], means [+188%, +11.7%], stds
  [122%, 27%].
- P(fwd20 > +10%) = 49%. ES5 = -27.4%.
- Shape: a large moderate-positive component (mean +11.7% over 20d)
  plus a rare blowout component (+188%). Nearly a coin flip for a
  double-digit 20-day move in the crush state; the downside tail is
  about -27% at the 5% level.

Normal state: w [0.78, 0.22], means [-0.1%, +11.2%], P(>10%) = 31%,
ES5 = -29%.

These shapes are the sizing inputs (probability-weighted, not
threshold rules).

## Caveats

- HMM identity is a full-sample research construct; trading would
  re-fit causally.
- The rebuilt-norm cells are small; the improved point estimate is
  not statistically stronger than the old norm.
- Seasonal amplitude rising is partly driven by the 2021-2026
  volatility era; a decade lens is needed before interpreting it as
  a demand-technology signal.

## Artifacts

- `deep_model_harness.py`, `results/direction3.csv`
