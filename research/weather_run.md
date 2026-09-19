# Weather experiment

## Scope and preregistered rule

The pre-registered hypothesis was that unusually warm weather weakens the demand driver for NG and winter-distillate crack longs.
The gate uses seven-day mean HDD, with HDD equal to `max(0, 18 C - T2M)`.
Each value is compared with prior same-month observations after at least 12 observations.
The score is clipped to `[-8, 8]`.
Exposure turns off below z `-1.0` and re-enters at z `-0.5`.
The state is applied on the next day.

The corrected local engine is `engine_v2.build_v2`.
The fixed CORE3 is `crack_321, cross_sectional, bzwti` with equal one-third weights.
The run uses 5 bps trade costs, 20 bps annual roll drag, a 90-day warmup, and the fixed v2 overlay.
No strategy parameter was fitted in this run.

## Inputs

The price panel has 4829 rows from 2007-07-02 through 2026-09-09.
The cached NASA POWER `NYC` file has 7182 usable rows from 2007-01-01 through 2026-08-30.
The cache has no usable `NYC` T2M for the final 10 calendar days of the panel; the last known gate state is carried forward on those dates.
The cached NASA POWER `HOUSTON` file has 7182 usable rows from 2007-01-01 through 2026-08-30.
The cache has no usable `HOUSTON` T2M for the final 10 calendar days of the panel; the last known gate state is carried forward on those dates.
The requested cached files are present.
The final cache tail is a documented input gap for the last 10 panel calendar days and does not affect the OOS window.

## Book results

| Variant | IS Sharpe | OOS Sharpe | OOS CAGR | OOS max drawdown | OOS volatility | Worst day |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CORE3 | 1.1260 | 0.8625 | 5.6249% | -10.7311% | 6.5930% | -2.8486% |
| CORE3+NGW | 1.0941 | 0.7364 | 4.1776% | -11.2023% | 5.7824% | -2.3341% |
| CORE3+HOW | -0.3423 | 0.6037 | 3.1372% | -11.1686% | 5.3514% | -4.3637% |
| CORE3+NGW+HOW | 0.7898 | 0.3776 | 1.6224% | -12.0854% | 4.5322% | -3.1486% |

## Weather-factor results

| Factor | City | IS Sharpe | OOS Sharpe | OOS CAGR | OOS max drawdown | OOS exposure days |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `ng` | raw | 0.6695 | 0.1134 | -0.0762% | -61.9909% | n/a |
| `ng` | NYC gate | 0.4699 | -0.0254 | -2.7232% | -67.0942% | 1003 |
| `ng` | HOUSTON gate | 0.7927 | 0.1161 | 0.1577% | -48.7034% | 1059 |
| `crack_ho` | raw | 0.1088 | -0.0798 | -2.2593% | -68.7105% | n/a |
| `crack_ho` | NYC gate | 0.0510 | -0.1426 | -2.7023% | -63.0124% | 424 |
| `crack_ho` | HOUSTON gate | 0.0919 | -0.0433 | -1.5553% | -63.0575% | 462 |

## Threshold plateau check

| NYC NG gate threshold | OOS Sharpe | OOS CAGR | OOS max drawdown |
| ---: | ---: | ---: | ---: |
| -0.75 | 0.7453 | 4.2502% | -12.3637% |
| -1.0 | 0.7364 | 4.1776% | -11.2023% |
| -1.5 | 0.7429 | 4.1680% | -12.3997% |

## City robustness

| City | CORE3+NGW OOS Sharpe | CORE3+HOW OOS Sharpe | NGW OOS CAGR | HOW OOS CAGR |
| --- | ---: | ---: | ---: | ---: |
| NYC | 0.7364 | 0.6037 | 4.1776% | 3.1372% |
| HOUSTON | 0.7008 | 0.5341 | 4.1111% | 2.7004% |

## Seeded shuffled controls

The control shuffles the NYC z-score values with seed sequence `11..22` while retaining dates.

| Statistic | Value |
| --- | ---: |
| Real NYC CORE3+NGW OOS Sharpe | 0.7364 |
| Shuffled mean Sharpe | 0.6813 |
| Shuffled Sharpe standard deviation | 0.1100 |
| Shuffled minimum Sharpe | 0.5057 |
| Shuffled maximum Sharpe | 0.8744 |

## Interpretation and blockers

The exact result is the comparison in the tables above.
A weather construction is not supported as an enhancer when its gated OOS result does not beat the fixed price-only comparison and its real result is not separated from the shuffled controls.
The cached weather input is available and causal, so this run has no requested data blocker.
The remaining data limitation is the local panel's documented yfinance continuous front-month prices and proxy roll model, not the weather files.
