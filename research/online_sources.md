# Online research: EIA, options, and reusable execution engines

- Work packet: `online-research-eia-options-engines`
- Access date: 2026-09-15
- Scope: assess reusable futures and options-engine capabilities, EIA data access, and the evidence needed for a realistic CL/RB/HO tail-hedge study.
- Source policy: this report uses only the eight official URLs listed in the task.

## Executive conclusion

LEAN is a practical candidate for futures-universe selection because its documentation models a futures subscription as a universe of dated contracts.
NautilusTrader is a stronger candidate when explicit roll metadata, synthetic instruments, and configurable execution assumptions matter.
Neither source proves that a vendor's default continuous series is suitable for this strategy without an audit of roll dates, adjustment, contract identity, and settlement conventions.

EIA provides relevant weekly petroleum supply tables and a documented REST API.
The EIA weekly page exposes downloadable CSV, XLS, and PDF tables, but it also records that its NYMEX futures-price table was discontinued after April 5, 2024.
EIA data can therefore support physical-state features and release-timed tests, but it is not a replacement for exchange futures or options market data.

CME's three official contract pages are the authoritative places to confirm the CL, RB, and HO option contract terms before sizing a hedge.
The pages did not render reliably during this retrieval, so exact current contract fields remain an explicit verification gap below.

## Confirmed facts from the official sources

### QuantConnect / LEAN futures universes

Source: https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures

- The page defines a Futures universe as a basket of contracts for one Future.
- LEAN models a Future subscription as a universe of Future contracts.
- The documented model separates the canonical Future from the individual dated contracts selected from its chain.
- The page documents filtering of the futures chain, including contract-selection rules such as expiry-related filtering.
- The page describes continuous futures as a way to work with a continuing future while the underlying tradable instrument is a dated contract.

These facts support using LEAN's chain and contract-selection machinery rather than treating one continuous price series as a directly tradable symbol.
The page does not establish that its default roll rule, price mapping, or data entitlement matches CME execution for this project.

### NautilusTrader continuous futures

Source: https://nautilustrader.io/docs/latest/concepts/continuous_futures/

- A continuous future is a derived series that splices consecutive futures contracts into one adjusted price stream.
- Each underlying contract expires, so the series rolls to the next contract at a transition point.
- Nautilus requires the caller to supply transition metadata.
- A transition contains a time, pre-instrument ID, post-instrument ID, pre-price, and post-price.
- The engine supports backward or forward adjustment and additive spread or multiplicative ratio adjustment.
- The default adjustment mode is `BACKWARD_SPREAD`.
- The continuous root is synthetic. Raw source data comes from the real contract for each segment.
- Transition times must be non-negative and strictly increasing.
- The contract chain must be continuous, and every instrument ID must use the target venue.
- Ratio adjustments require positive prices.
- The engine does not discover rolls, choose contracts, or infer roll prices. The caller owns that metadata.
- Internally aggregated continuous bars are supported. Externally aggregated bars cannot be continuous targets, though they can be segment sources.
- If a roll occurs during an in-progress target bar, the builder keeps the existing OHLC state and applies the new adjustment only to later updates.

This is a useful explicit contract for a research audit because roll decisions and adjustment prices can be versioned as input data.
It also means a Nautilus implementation is not turnkey: the project must build and validate the transition table.

### NautilusTrader fill models

Source: https://nautilustrader.io/docs/nightly/concepts/backtesting/fill-models/

- Historical data cannot show how a simulated order interacted with other market participants.
- A fill model controls assumptions about limit-order eligibility, one-tick slippage, and optional synthetic liquidity.
- With L2 or L3 data, the recorded book supplies price levels and sizes, and the matching engine walks those levels.
- With L1 data, `prob_fill_on_limit` controls whether a touched limit fills, while `prob_slippage` can add one adverse tick.
- The default model uses `prob_fill_on_limit=1.0` and `prob_slippage=0.0`.
- Historical order-book data remains immutable after a fill.
- `liquidity_consumption=True` tracks consumed displayed size until fresh data arrives.
- The documentation lists built-in models including default, best-price, one-tick-slippage, probabilistic, tiered, size-aware, competition-aware, volume-sensitive, and market-hours models.
- A reproducible run can set `random_seed` for probabilistic draws.
- The nightly documentation says that high-level venue configuration accepts built-in fill models, while low-level `BacktestEngine.add_venue()` accepts a custom Python object with the documented methods.
- The page warns that tier sizes are instrument-quantity units and must be checked against instrument scale.

For this project, a close-only backtest cannot claim realistic option or futures fills.
A credible engine comparison must report the chosen book type, fill model, slippage, liquidity consumption, order timing, and seed.

### EIA Weekly Petroleum Status Report

Source: https://www.eia.gov/petroleum/supply/weekly/index.php

- The page publishes the Weekly Petroleum Status Report data and links to downloadable CSV, XLS, and PDF files.
- The listed tables cover petroleum supply measures, stocks, imports and exports, spot prices, and retail prices.
- The page links a table for spot prices of crude oil, motor gasoline, and heating oil.
- The page identifies a table for U.S. and PAD District weekly estimates.
- The page provides an official release schedule link, methodology links, explanatory notes, sources, and errata.
- The page states that the NYMEX futures-price table for crude oil, motor gasoline, and No. 2 heating oil was discontinued after April 5, 2024.

The release schedule and publication files are essential for a no-look-ahead test.
A feature must be timestamped when it became public, not when the covered week ended.

### EIA Open Data API

Source: https://www.eia.gov/opendata/documentation.php

- EIA provides free and open data through an API, Excel add-in, bulk files, and widgets.
- The page documents API v2 and links the current API specification.
- API responses default to JSON, with XML available through an output parameter.
- API requests support data fields, facets, frequency, date range, sorting, and pagination.
- The documentation describes walking the API tree and inspecting metadata before requesting values.
- The page says API registration and compliance with the API Terms of Service help EIA monitor usage and service availability.
- The documentation states that XML output is limited to 300 rows per response and can be paginated.

The metadata-first workflow is suitable for recording series IDs, units, frequency, geography, and revisions before model use.
An API key and rate-limit handling belong in the data adapter, not in strategy logic.

### CME option contract pages

Sources:

- https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.contractSpecs.options.html
- https://www.cmegroup.com/markets/energy/refined-products/rbob-gasoline.contractSpecs.options.html
- https://www.cmegroup.com/markets/energy/refined-products/heating-oil.contractSpecs.options.html

Confirmed from the source identities: CME publishes separate official contract-specification pages for options on Light Sweet Crude, RBOB Gasoline, and Heating Oil.
These are the correct primary sources for underlying contract, quote convention, contract size, minimum price fluctuation, exercise style, settlement, listing cycle, and termination details.

The rendered CME pages timed out in this retrieval, so this report does not treat any unobserved contract field as confirmed.
Do not hard-code contract multipliers or exercise rules from memory.

## Project inference

- The engine problem has two separate layers: a research price/roll layer and a tradable contract/execution layer.
- LEAN can reduce implementation work for futures-chain discovery and selection, but its documented page does not by itself prove roll transparency or option-spread execution fidelity.
- Nautilus can represent the required explicit transition table and can expose the fill assumptions needed for sensitivity analysis.
- For a frozen CL/RB/HO study, the safest common design is to retain dated contract IDs, use a separately versioned continuous research series, and record every roll decision.
- EIA stocks, refinery utilization, imports, and spot-price tables are plausible explanatory or risk-state inputs. They are released weekly and must be lagged to their public release time.
- The discontinued EIA NYMEX futures table means futures returns must come from an exchange or market-data source, not be reconstructed from that EIA table after April 2024.
- CME contract pages can define the legal instrument geometry, but they do not supply historical option quotes, bid/ask spreads, implied volatility, or executable fills.
- A modeled Black-76 option screen can test cost plausibility. It cannot establish historical tradability without historical option quotes and a fill rule.
- Existing project evidence already finds the modeled crash-put overlay uneconomic and rejects EIA/weather gating as an edge enhancer. This online research therefore supports auditability and implementation planning, not a claim that a new overlay is profitable.

## Gaps and risks

- CME page fields were not machine-confirmed in this run because the pages timed out.
- The supplied sources do not provide historical CL, RB, or HO option chains, bid/ask quotes, implied volatility, open interest, or trade timestamps.
- The supplied engine pages do not document the project's required CME data entitlement, adapter availability, broker routing, or production operational cost.
- Roll timing, first/last usable bars, expiry notices, delivery risk, and settlement-price conventions remain project decisions.
- Continuous-series adjustment can change spread levels and signals. A ratio or spread adjustment must not be mixed with option strikes without a clear mapping to the dated underlying.
- Bar data does not reveal intrabar order sequence. Fill results from OHLC alone require conservative assumptions and sensitivity checks.
- EIA revisions, preliminary values, missing observations, and release timing can create look-ahead bias.
- A weekly EIA observation cannot be treated as available at the end of its covered week unless the release timestamp proves that timing.

## Practical next actions

1. Capture the three CME pages manually or through an allowed browser and record every current contract field with an access date.
2. Obtain historical dated CL, RB, and HO futures and option quotes from an entitled source, including bid, ask, trade, volume, open interest, and timestamps.
3. Build a versioned roll table with contract IDs, roll timestamp, pre/post prices, rule, and source evidence.
4. Re-run the frozen strategy on dated contracts in either LEAN or Nautilus, then compare it with the existing continuous-series result.
5. If using Nautilus, start with L1 or better data and test `DefaultFillModel`, probabilistic fills, adverse one-tick slippage, and liquidity consumption under fixed seeds.
6. If using LEAN, log the selected chain members and mapped tradable symbol at every decision so the universe abstraction cannot hide roll behavior.
7. Register EIA series through API metadata first. Store series ID, unit, frequency, facet, observation period, release time, retrieval time, and revision status.
8. Join EIA observations only after their public release timestamp. Add a publication-lag test and a negative-control permutation test.
9. Verify CME option exercise, settlement, multiplier, tick, and expiration rules before sizing any spread or translating payoff into futures-equivalent exposure.
10. Keep the modeled option-cost result labeled as a plausibility screen until historical executable option data is available.

## Source list

1. QuantConnect, Futures universes: https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures
2. NautilusTrader, Continuous Futures: https://nautilustrader.io/docs/latest/concepts/continuous_futures/
3. NautilusTrader, Fill Models: https://nautilustrader.io/docs/nightly/concepts/backtesting/fill-models/
4. U.S. EIA, Weekly Petroleum Status Report: https://www.eia.gov/petroleum/supply/weekly/index.php
5. U.S. EIA, Open Data API documentation: https://www.eia.gov/opendata/documentation.php
6. CME Group, Light Sweet Crude options specifications: https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.contractSpecs.options.html
7. CME Group, RBOB Gasoline options specifications: https://www.cmegroup.com/markets/energy/refined-products/rbob-gasoline.contractSpecs.options.html
8. CME Group, Heating Oil options specifications: https://www.cmegroup.com/markets/energy/refined-products/heating-oil.contractSpecs.options.html
