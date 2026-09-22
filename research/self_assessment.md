> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Self-assessment — what was done wrong, and the corrected method

Written after the captain's deep critique. This document owns the
failure list, the assumption decomposition, the demand/supply/tech
decomposition, and the grounded-constants procedure.

## The sin list (ungrounded constants in our own code)

| Constant | Where | Grounded? |
| --- | --- | --- |
| entry -0.75 / exit -0.5 | seasonal z state machine | picked mid-plateau; never read from the conditional-mean curve |
| z lookback 90 | seasonal z | plateau pick |
| tilt 1.25 / 0.75 | phase 3, batches | picked "reasonable" |
| fullness 0.85 | Cushing | picked |
| depth clip(1+0.5*(|z|-0.5),1,2) | multi-leg F2 | picked coefficients |
| overlay -6% / -10%, vol 10% | V2 | sweep plateau, not equity-loss distribution |
| z standardization itself | everywhere | the "Gaussianize" the captain rejected |

None of these can answer "why this number, why not another". That is
the defect. A constant is valid only when it is read from the shape of
the thing being modeled.

## The seasonal-norm assumptions (decomposed)

1. Time-invariance. Measured FALSE (M7: norm +4..+8 pts since 2016).
2. Calendar month is the season's carrier, not temperature, holidays,
   blend dates, daylight.
3. Mean is the right statistic, not median/mode/distribution.
4. Intra-month homogeneity (early vs late month).
5. Stable variance. Measured FALSE (summer std widened).
6. Additive seasonality in level, not multiplicative.
7. No regime interaction (crush behaves same in expansion and
   compression). Measured FALSE (P5).
8. Gaussian residuals (z quantiles meaningful as Gaussian).
9. Equal weighting of years (2019 weighs like 2024).
10. No interaction with weather, storage, blending forces.

Each of 2,3,4,6,8,9,10 is untested and likely false. The audit run
starts measuring them.

## Demand/supply/technology decomposition (first pass)

Demand:
- Gasoline: population x GDP x fleet x vehicle-km x
  consumption-per-km(weather) x (1 - EV share) x elasticity, minus
  blend-wall effects.
- Distillate: goods movement + heating + marine (IMO2020) + jet.
- Each term has a sign and a data proxy.

Supply:
- Crude: OPEC+ policy, shale growth, non-OPEC.
- Refining: utilization, closures, RD conversions, new builds.
- Product trade: exports, imports, pipelines.
- Storage: the buffer (B_t).

Technology:
- EV share, efficiency: flatten gasoline seasonality.
- RD/SAF: remove gasoline-making capacity.
- IMO2020: permanently lifted distillate demand 2020.
- Technology shifts both the norm trend and the seasonal SHAPE.

## Seasons as regimes

A season is not an adjustment; it is a regime. Sub-regime axes:
1. Calendar phase (peak/shoulder/trough per product).
2. Weather state (cold severity z; hurricane/freeze events).
3. Blend state (RVP window: pre-switch, switch, post-switch).
4. Inventory state (injection, winter fill, normal).
5. Margin state (crush / normal / stretched) x regime
   (expansion / compression / crisis).

For each sub-regime: distribution of daily margin returns, conditional
forward means, transitions, volatility. That IS the deep model.

## Grounded-constants procedure (the replacement for tuning)

1. Estimate conditional distributions: P(fwd > 0 | state),
   E[fwd | state], var[fwd | state], from the data directly.
2. Entry = state quantile where the smoothed conditional-mean curve
   turns strongly positive. Exit = where it returns to zero.
3. Multipliers = the fitted shape, normalized, not step picks.
4. Caps = quantiles of the position/risk distribution at target loss.
5. Any remaining constant must cite the empirical curve it came from.
6. Optimization over grids is banned; parameters come from shapes.
