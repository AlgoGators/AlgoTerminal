# Research Report: Physical Refinery-Margin Branch

## Proposal

Test a physical operating-flow signal rather than another high-inventory gate.
The branch asks whether refiners' run decisions and product-flow balance identify when a crushed crack is likely to recover.

The existing price strategy buys a seasonally crushed WTI crack, using `(2*RB + HO)/3 * 42 - CL` and a long-only hysteresis signal.
The branch keeps that price signal as the frozen trading baseline.
Fundamentals may change exposure only after an observable EIA release.

The economic mechanism is operational.
A low margin should eventually reduce refinery inputs or runs.
If product supply then tightens relative to demand, gasoline or distillate inventories should draw and the margin should recover.
This differs from the rejected storage gate, which treated a high inventory level as a direct de-risk trigger.

## Falsifiable hypotheses

- **H1, run-cut confirmation:** after a seasonally crushed gasoline or heating crack, a falling refinery utilization signal predicts a stronger positive crack return over 5, 10, and 20 trading days than the same price entries without confirmation.
- **H2, product-flow pressure:** a product inventory draw, measured as the latest weekly change relative to its calendar-month history, predicts stronger forward crack recovery after a crush.
- **H3, operational mismatch:** the strongest recovery occurs when refinery utilization is falling while product stocks are drawing, or when utilization remains low while product stocks draw.
- **H4, false confirmation:** a product inventory build while utilization is rising predicts weaker recovery or continued compression after a crushed-crack entry.
- **H5, incremental value:** a pre-registered fundamental score improves OOS expectancy or drawdown versus the frozen baseline after costs, without relying on a new threshold selected from the holdout.

The primary test is a conditional-return test.
The secondary test is a position scale of 0, 0.5, or 1.0 from a score defined before the result is inspected.
No short crack position is introduced.

## Available data and connectors

The existing `algoterminal-data` EIA provider is the primary connector.
It routes petroleum storage requests through `petroleum/stoc/wstk` and refinery utilization through `petroleum/pnp/wiup`.
It reads `EIA_API_KEY` from the environment or project secrets and caches `close` values by observation date.

Confirmed EIA series already used by `fetch_eia.py` are:

- `WPULEUS3`: U.S. refinery operable utilization rate.
- `WGTSTUS1`: U.S. total gasoline ending stocks.
- `WDISTUS1`: U.S. distillate fuel oil ending stocks.
- `WCESTUS1`: U.S. crude ending stocks excluding SPR.
- `W_EPC0_SAX_YCUOK_MBBL`: Cushing crude stocks.
- `NW2_EPG0_SWO_R31`, `R32`, `R33`, `R34`, `R35`, and `R48`: regional natural-gas working storage, which can be summed but is not required for this refinery branch.

The first pass uses only utilization, gasoline stocks, and distillate stocks.
Crude and Cushing stocks are controls, not primary features, because prior Cushing scaling was useful only for the standalone Brent-WTI factor and hurt the book.

The existing FRED connector is keyless and whitelist-based.
Useful controls include `GASREGW`, `CPIENGSL`, `DCOILWTICO`, `INDPRO`, and `VIXCLS`.
FRED does not provide the required weekly EIA storage or utilization history in this project.
Do not substitute a FRED series for an unavailable physical series.

Market inputs come from the existing panel and `factor_book.py` construction.
The durable audit panel covers CL, BZ, RB, HO, and NG from 2007 onward, with the documented continuous-contract and roll limitations.

Potential extensions such as refinery inputs, finished-product production, imports, exports, and regional PADD series require EIA facet discovery before use.
They are not part of the minimum result unless `discover_eia.py` identifies stable codes and the codes are recorded with their units and route.

## Feature construction

Use weekly observations as reported, not as if they were daily observations.
For each series, compute the week-over-week change and a same-calendar-month expanding z-score using only prior observations.
Require at least 12 prior same-month observations and clip z-scores to `[-8, 8]`, matching the existing storage work.

Define:

- `util_change_z`: z-score of the weekly change in `WPULEUS3`.
- `gas_draw_z`: negative of the weekly gasoline-stock change z-score, so a draw is positive.
- `dist_draw_z`: negative of the weekly distillate-stock change z-score.
- `product_draw_z`: z-score of the combined gasoline-plus-distillate weekly change, with the sign reversed.
- `physical_score`: `product_draw_z - util_change_z`, with a positive value meaning product tightening alongside falling utilization.

The primary pre-registered score is:

`confirmed = (physical_score >= 1.0) and (product_draw_z >= 0.5)`.

The score is only evaluated for a currently active long seasonal-crush position.
The baseline is the unconditioned frozen CORE3 configuration, not a price signal re-fit on the fundamental subset.

## Event time and release lag

The EIA observation date is the week-ending period, not the time at which the market learned the value.
The WPSR weekly release is generally published on Wednesday afternoon or Thursday around holidays.
The fetch connector currently returns observation dates and does not preserve a publication timestamp or vintage.

For the minimum causal backtest, assign each Friday week-ending observation an availability date of the following Thursday, six calendar days later.
If the period or release calendar is ambiguous, use the later of the documented release date and period plus seven calendar days.
Do not use a newly fetched revised value to stand in for the originally published value.

Forward-fill a released feature onto the daily market index only from its availability date.
A position decision at close `t` can use a feature released before that close.
The return for day `t` must use the feature state known at close `t-1`, matching the existing `storage_gate.py` convention.
A release arriving after the futures settlement is usable on the next trading session, not retroactively on the release date.

FRED observations need extra caution because the CSV connector supplies observations without ALFRED vintages or release timestamps.
Use FRED only as a lagged monthly control with a conservative 30-day delay, or report it descriptively.
Do not use revised FRED values in a claimed real-time signal.

## Minimum baseline and experiment

The minimum runnable comparison has three rows:

1. Frozen CORE3 equal-weight book with its existing v2 overlay and documented 5 bps trade plus 20 bps annual roll assumptions.
2. The same book with the fundamental scale applied only to the crack legs, using the pre-registered `confirmed` rule.
3. A negative-control version with the weekly feature values permuted within the historical date index before release lagging.

Report per-factor and book results for the existing IS/OOS split.
Use the existing 90-day warm-up and fixed weights chosen from the in-sample window.
Report Sharpe, CAGR, maximum drawdown, annualized volatility, worst day, trade count, exposure days, and conditional forward returns.
Also report the number of fundamental releases, confirmed entries, and days affected.

Run a small robustness table without selecting a winner:

- score cutoffs 0.75, 1.0, and 1.25;
- availability delay 6 and 7 calendar days;
- gasoline and distillate separately versus the combined product series;
- crack 3:2:1 and heating crack separately.

The robustness table is descriptive.
The primary conclusion remains tied to the 1.0 score and conservative lag specified above.

## Failure criteria

Reject the branch as an edge enhancer if any of these conditions holds:

- OOS Sharpe for the fundamental version is below the frozen baseline by at least 0.10.
- OOS maximum drawdown is worse by at least 2 percentage points without a compensating 0.10 Sharpe gain.
- The sign of H1, H2, or H3 reverses across the 5-, 10-, and 20-day horizons, with no stable horizon declared in advance.
- The real feature does not beat the mean shuffled-control result by at least one standard deviation across 20 permutations.
- The result depends on the six-day lag, one product, one city-style threshold, or a single calendar regime.
- Fewer than 20 independent confirmed events exist across the OOS history, making the conditional result too sparse to support a claim.
- Any feature uses a period date before its release, revised history without vintage control, or a feature calculated with current-sample future observations.

A failed branch can still produce a useful descriptive result.
If it fails these criteria, retain physical variables as monitoring diagnostics and do not add them to the trading book.
This is the likely outcome given that prior level-based storage, natgas, weather, and book-level Cushing gates were falsified.

## Expected decision and next implementation step

The distinct test is whether *changes in operating state* explain recovery better than *inventory level*.
The prior negative results do not falsify this flow mechanism, but they set a low prior and a strict control requirement.

Implement the experiment in a new audit script only after this report is accepted.
Reuse `fetch_eia.py`, `storage_gate.py` timing helpers, `factor_book.py`, and `engine_v2.py` rather than changing the production strategy.
The report is complete only when the script records raw release dates, lagged feature values, event counts, shuffled-control results, and the full baseline comparison.
