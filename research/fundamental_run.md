# EIA Fundamental Experiment

## Source and row counts

- The price panel is `panel_v2.parquet` with 4,829 rows across CL, BZ, RB, HO, and NG.
- The panel runs from 2007-07-02 through 2026-09-09.
- The fetched gasoline series `WGTSTUS1.csv` has 1,027 rows from 2007-01-05 through 2026-09-04.
- The fetched distillate series `WDISTUS1.csv` has 1,027 rows from 2007-01-05 through 2026-09-04.
- The fetched utilization series `WPULEUS3.csv` has 1,027 rows from 2007-01-05 through 2026-09-04.
- The feature output has 882 rows and 12 columns, indexed from 2009-03-05 through 2026-09-10.
- The daily state output has 4,829 rows and 12 columns, indexed from 2007-07-02 through 2026-09-09.
- The run processed 882 releases, confirmed 140 entries, and affected 3,481 days.

## Causal settings

- The experiment used `engine_v2.build_v2` with no fitted strategy parameters.
- It used the fixed CORE3 factors `crack_321`, `cross_sectional`, and `bzwti` at equal one-third weights.
- EIA observations were applied with a six-day release lag.
- The physical score cutoff was 1.0.
- The product score cutoff was 0.5.
- Same-month factor statistics required at least 12 observations.
- The run used a 90-day warmup, 5.0 trade-cost basis points, and 20.0 annual roll basis points.
- The overlay was enabled.
- The negative control used 20 permutations with seed 23.

## Baseline versus scaled variant

| Variant | CAGR | Sharpe | Max drawdown | Volatility | Worst day | Trades | Exposure days |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 5.2772% | 0.8297 | -10.7311% | 6.4454% | -3.2814% | 256 | 2,909 |
| EIA scaled | 1.1652% | 0.3250 | -12.9930% | 3.7781% | -2.8484% | 283 | 2,181 |

The scaled variant reduced exposure and volatility, but it also reduced CAGR and Sharpe and produced a deeper maximum drawdown.

## Factor statistics

### Baseline

| Factor | CAGR | Sharpe | Max drawdown | Volatility | Worst day | Trades | Exposure days |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `crack_321` | 6.3435% | 0.4290 | -36.1045% | 18.1230% | -18.2108% | 105 | 518 |
| `cross_sectional` | 19.3237% | 0.6154 | -65.4375% | 40.3702% | -18.6090% | 231 | 1,888 |
| `bzwti` | -0.1319% | 0.0595 | -54.8342% | 12.8923% | -31.0924% | 222 | 1,722 |

### EIA scaled

| Factor | CAGR | Sharpe | Max drawdown | Volatility | Worst day | Trades | Exposure days |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `crack_321` | 2.5542% | 0.3090 | -31.6328% | 9.7342% | -18.2108% | 64 | 193 |
| `cross_sectional` | 5.3853% | 0.3634 | -52.8036% | 19.4880% | -18.1629% | 168 | 743 |
| `bzwti` | -0.1319% | 0.0595 | -54.8342% | 12.8923% | -31.0924% | 222 | 1,722 |

The EIA scaling changed `crack_321` and `cross_sectional` activity, while `bzwti` was unchanged.

## Permutation negative control

Across 20 seeded permutations, the mean Sharpe was 0.3785 with a standard deviation of 0.1254.

| Statistic | Mean | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| CAGR | 1.6990% | 0.8480% | 3.2264% |
| Sharpe | 0.3785 | 0.2015 | 0.6229 |
| Max drawdown | -12.6371% | -18.4002% | -10.0271% |
| Volatility | 4.5997% | 3.8335% | 5.6712% |
| Worst day | -3.0645% | -4.2816% | -2.8484% |
| Trades | 287.1 | 273 | 309 |
| Exposure days | 2,239.1 | 2,191 | 2,305 |

The observed EIA-scaled Sharpe of 0.3250 is below the permutation mean of 0.3785 and within the permutation range of 0.2015 to 0.6229.
