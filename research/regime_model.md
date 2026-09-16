# Regime model — seasons as regimes

The captain's critique: seasonality must be modeled as a regime
system, not an adjustment. Sub-regime axes:

1. Calendar phase: peak / shoulder / trough, per product.
2. Weather state: cold severity z, hurricane / freeze events.
3. Blend state: RVP window pre-switch / switch / post-switch.
4. Inventory state: injection, winter fill, normal draw/build.
5. Margin state: crush / normal / stretched, crossed with regime
   (expansion / compression / crisis).

Per sub-regime, estimate from data:
- Distribution of daily margin returns (PDF, quantiles).
- Conditional forward expectations E[fwd | state].
- Transition frequencies between sub-regimes.
- Volatility.

First data pass (findings/shape_pass.md) shows the structure:
- Long-crush edge lives in compression.
- Short-stretch edge lives in expansion.
- Season curve is strongly shaped (Feb vs Aug).
- Variance not stable; multiplicative component present.

Next steps:
- Estimate regime identity from the data (mixture or state-space on
  margin levels), not a fixed 252-day mean.
- Build per-sub-regime distributions and transition matrix.
- Read all construction constants from those shapes.
- Then, and only then, derive position functions.
