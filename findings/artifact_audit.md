# Artifact audit — the real results on a roll-free price series

Date: 2026-09-22. Author: independent re-measurement, not the original
harness authors. Reproduce: `python scripts/fetch_spot_crack.py &&
python scripts/build_spot_panel.py && python scripts/walkforward.py &&
python scripts/walkforward_causal.py && PANEL=engine/panel_spot.parquet
PANEL_TAG=spot_fixed python scripts/walkforward.py &&
PANEL=engine/panel_spot.parquet PANEL_TAG=spot_causal
python scripts/walkforward_causal.py && python scripts/artifact_audit.py`

## What was checked

The quoted walk-forward headline runs on `engine/panel_v2.parquet`, built
from yfinance continuous front-month futures (`CL=F`, `RB=F`, `HO=F`).
Those three legs roll on different dates, so the crack series carries
scheduled level discontinuities that are not refining-margin moves.

Everything below was re-measured on `engine/panel_spot.parquet`, a
roll-free twin built from EIA daily spot (WTI Cushing, NY Harbor gasoline,
NY Harbor ULSD). Spot never rolls. The walk-forward machinery is identical;
only the panel changed.

## Finding 1 — 40% of the quoted P&L is one scheduled contract change

RBOB (the `RB=F` leg) rises on the first trading day of March in
**19 of 19 years**, mean **+9.2%**. That is the winter-grade to
summer-grade gasoline specification switch, a scheduled contract change
with no refining-margin content. The matching spot series shows
**+2.5%, 14 of 20** — no such pattern.

| series | March-1 gasoline move | positive years |
| --- | --- | --- |
| futures `RB=F` (quoted panel) | +9.20% | 19/19 |
| spot NY Harbor gasoline (roll-free) | +2.50% | 14/20 |

Those 15 sessions carry **+0.692 of the +1.722 total P&L = 40.2%** in the
fixed-control walk-forward.

### The mechanism, proved exactly

The rolled continuous series can be compared directly to the roll-free spot
series over the same 2006-2024 window. The difference is the accumulated
construction/roll gap:

| change in (rolled - spot) gap | value | years |
| --- | ---: | --- |
| March, per month | **+3.915 $/bbl** | positive **18/18** |
| every other month, per month | -0.363 $/bbl | - |
| full year, net | -0.76 $/bbl | ~zero |
| March-1 sessions alone | **+3.163 $/bbl** | positive 15/18 |

The rolled series gains +3.9 $/bbl every March and gives it all back across
the other eleven months. A position held year-round nets zero. A position
held **only across the March roll** keeps the jump for free. That is exactly
what the seasonal signal does, because the seasonal norm for March is built
from prior Marches that are already post-switch, so late-February reads as
artificially "crushed".

The book was long into March 1 in 6 of 15 years and won all 6.

## Finding 2 — the whole headline depends on a few days

Top 1% of days carry **81%** of total variance (top 5%: 89%). Removing the
top 1% of absolute days or the roll windows moves every headline number.

## Finding 3 — on roll-free prices the edge is weak

`scripts/artifact_audit.py` output, block t is on non-overlapping 20-day blocks:

| strategy / panel | exclusion | ann | Sharpe | MaxDD | block t | DSR@1e3 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| FIXED / futures (quoted) | as reported | +11.75% | 0.853 | -17.7% | +3.37 | 0.707 |
| FIXED / futures | ex March 1 | +7.05% | 0.636 | -17.7% | +2.46 | 0.207 |
| FIXED / futures | ex top 1% | +4.70% | 0.546 | -21.7% | +2.01 | 0.124 |
| CAUSAL / futures (quoted) | as reported | +9.34% | 0.704 | -23.6% | +2.79 | 0.396 |
| CAUSAL / futures | ex March 1 | +4.75% | 0.434 | -23.6% | +1.59 | 0.055 |
| FIXED / **roll-free spot** | as reported | +5.26% | 0.385 | -22.2% | **+1.44** | **0.036** |
| CAUSAL / **roll-free spot** | as reported | +7.71% | 0.601 | -21.1% | +2.33 | 0.162 |
| CAUSAL / roll-free spot | ex top 1% | +6.22% | 0.671 | -18.1% | +2.73 | 0.251 |
| CAUSAL contiguous-crush / futures | as reported | +9.89% | 0.715 | -20.3% | +2.88 | 0.439 |
| CAUSAL contiguous-crush / futures | ex March 1 | +4.86% | 0.438 | -20.2% | +1.64 | 0.056 |
| CAUSAL contiguous-crush / **roll-free spot** | as reported | +8.41% | 0.667 | -21.1% | +2.54 | 0.234 |
| CAUSAL contiguous-crush / roll-free spot | ex top 1% | +6.06% | 0.656 | -20.6% | +2.68 | 0.232 |

The quoted deployable benchmark (fixed controls) has **block t 1.44 and
DSR 0.036** on roll-free prices. That is indistinguishable from luck.

The `ex roll-window` row for the spot panel is meaningless: a roll-free
series has no roll window, so that row only drops an arbitrary 9.6% of
days. Do not cite it.

## Finding 4 — the risk plumbing buys drawdown with the edge

Bare crush signal (long when `z <= -0.70`, crush regime, scale 1.0, no
stops, no overlay, no cooldown, no H1 gate, no ES sizing):

| panel | ann | Sharpe | MaxDD | block t |
| --- | ---: | ---: | ---: | ---: |
| futures | +37.1% | 0.743 | **-75.1%** | +3.36 |
| roll-free spot | +79.3% | 0.474 | **-74.5%** | **+1.68** |

The raw signal has a ~-75% drawdown. The risk layer cuts that to -18%,
and in doing so cuts the roll-free edge to t 1.44. The strategy is a
risk-transformation, and on real prices the residual edge is not
significant.

## Finding 5 — the causal entry rule does not implement the thesis

`scripts/walkforward_causal.py` derives the entry cut as *the largest
z-bin centre whose bin t >= 1.5*. Taking the largest qualifying bin picks
the **least-crushed** bin with a positive mean, not the crush region. It
produced `zcut = +0.70` in 2012-2014 and +0.47 in 2015 and 2023-2026.
Entry `z <= +0.70` trades almost the whole distribution, which contradicts
"long only when crushed". The binned curve (diagnostic) shows the crush
region on roll-free spot is `z < -0.7` with bin t of 4.3-7.0; the rule
ignores it in favour of a weak secondary region around `z = +0.2..+0.5`.

## Finding 4b — the roll COST model was fine; the defect is the artifact

To check whether the assumed -20 bps/yr roll drag was the problem, the
realized carry was measured directly: the total change in the spread level
of the rolled contract-1 series versus the roll-free spot series.

| measure | value |
| --- | ---: |
| period | 2006-06-14 .. 2024-04-05 (17.8y) |
| cumulative roll effect | -1.10 $/bbl total |
| per year | -0.06 $/bbl/yr = **-0.3%/yr** of the crack level |

The harness assumed -20 bps/yr. The realized figure is about -30 bps/yr.
Same sign, same order of magnitude. **The roll cost assumption was not the
problem.** The problem is the March timing artifact above: a real position
that rolls pays the premium back, so the jump is not a repeatable profit.

(An earlier analytic estimate in this audit used the instantaneous curve
slope, `(c1-c2)/c1`, and suggested a large positive carry of about +34%/yr.
That estimate was wrong and was discarded after this direct measurement.
Instantaneous slope is not realized carry.)

## Finding 5b — the entry threshold is not pinned by the data

The derived entry cut wanders across a very wide range depending on the
training window: +0.70 (2012-2014), +0.47, +0.24, -0.45, -0.68, -0.91.
That is a swing from deep-crush to no-filter at all.

The thesis-consistent alternative is implemented as `ENTRY_RULE=contiguous_crush`
(walk up from the lowest eligible z-bin while bin t stays >= 1.5). It still
wanders into positive territory with thin training data (2012: -0.10,
2013: +0.35, 2014: +0.13), because early windows are noisy and the walk can
run through the neutral zone.

Conclusion: this derivation does not pin the threshold. It behaves as a
free parameter that the training data cannot determine. Under the project's
own standard it must therefore be disclosed as a risk-preference or
significance-level selection, not presented as "derived".



The committed `results/walkforward_causal_series.csv` (commit `be66e95`)
yields **ann +5.87%, Sharpe 0.459, block t 1.54, MaxDD -29.1%**.

Running the committed code (HEAD, byte-identical to `be66e95` for this
file) on the frozen input (sha256 verified against the manifest, no env
overrides) yields **ann +9.34%, Sharpe 0.704, block t 2.79, MaxDD -23.6%**.

The committed diary also records 2012 as a flat year, which the committed
code does not produce. The artifact is stale and orphaned. The claims
ledger's own "Reproducibility bar" rule ("sweeps must first reproduce the
base anchor") is failed by the base anchor.

## Finding 7 — the trial count is understated

DSR is computed with N=1000. This repo alone holds 1136 configuration
rows across 85 result CSVs and 39 harnesses, plus the v1 audit tree and
`book_oos_v2..v8`. At N=5000 the fixed-panel DSR falls 0.707 -> 0.544;
at N=20000, 0.410.

## Finding 8 — the assumed 5 bps/side cost is low by 3.2x to 4.8x

Measured from published components for one 1,000 bbl 3:2:1 crack unit
(3 CL + 2 RB + 1 HO = 6 contracts):

| component | value |
| --- | --- |
| exchange + clearing | $1.60 per contract per side (CME 2025, NYMEX energy, non-member) |
| NFA assessment | $0.02 per contract per side |
| commission | $0.00 to $2.50 per side |
| slippage | one tick round trip: CL $10.00, RB $4.20, HO $4.20 |

Round trip per crack unit = $62.04 (no commission) to $92.04
($2.50/side) = **16.2 to 24.0 bps per side**. The harness used 5 bps.

Cost sensitivity (block t, roll-free spot panel):

| series | 5bps | 10bps | 16bps | 24bps | 40bps |
| --- | ---: | ---: | ---: | ---: | ---: |
| FIXED controls | +1.44 | +1.33 | +1.20 | +1.03 | +0.69 |
| CAUSAL re-derived | +2.33 | +2.22 | +2.07 | +1.88 | +1.50 |
| CAUSAL contiguous-crush | +2.54 | +2.43 | +2.29 | +2.11 | +1.74 |

The 5 bps column reproduces the reported block t exactly, which validates
the reconstruction. At measured cost nothing on roll-free prices reaches
significance.

## Honest real result

On roll-free prices, over 2012-2026 (~15y, ~185 trades):

- **ann +4.7% to +8.4%**
- **Sharpe 0.39 to 0.67**
- **block t 1.4 to 2.5** (2.5 to 2.9 only after the entry-rule fix)
- **MaxDD -18% to -22%**
- **DSR 0.04 to 0.23** on the fixed benchmark, 0.15 to 0.23 on the causal variants

No variant reaches a conventional significance bar once the scheduled contract
change is removed. The best roll-free case (contiguous-crush rule) is block t
2.54 and DSR 0.234, and its threshold is not pinned by the data.

## What this does not prove

- The spot panel is not a drop-in substitute for a properly roll-adjusted
  futures backtest. Spot has no basis or term structure, a different
  calendar, and ULSD spot starts 2006-06. It is the best free proxy for the
  *signal* (the refining margin), which is the thing being claimed.
- The `ex roll-window` mask is calendar-heuristic because the frozen panel
  stores only continuous series with no roll calendar. The March-1 test is
  exact, and it agrees with the heuristic mask.

## Remaining work (status after this pass)

1. ~~Same-delivery-month contracts at settlement, explicit measured roll~~
   DONE. Contracts 1-4 fetched (`scripts/fetch_fut_contracts.py`, EIA
   `petroleum/pri/fut`, daily, ends 2024-04-05). Realized carry measured at
   -0.3%/yr, so the assumed -20 bps roll drag was sound. EIA's contract-1/2/3
   series do not satisfy the clean shift-by-one identity, so an exact
   same-month stitch was not built; the artifact was proved instead by
   comparing the rolled series to the roll-free spot series, which is
   sufficient and does not depend on a roll calendar.
2. Replace the assumed 5/20 bps with measured exchange, commission, and roll
   numbers. DONE. Real round trip is 16.2-24.0 bps per side (assumed 5).
   Roll realized is -0.3%/yr (assumed -0.20). At measured cost, roll-free
   block t is 1.0-2.3. Nothing reaches significance.
5. Freeze a forward test on new data. DONE as `research/forward_protocol_v3.md`.
   It uses the roll-free signal, discloses the threshold as a selection, uses
   the measured cost, and sets gates without a Sharpe target. The v2 protocol
   is marked superseded.
3. Fix the causal entry rule. DONE as `ENTRY_RULE=contiguous_crush`; result is
   that the threshold is not pinned by the data (Finding 5b).
4. Regenerate every quoted artifact from committed code and verify
   reproducibility. DONE for the fixed-control artifact (byte-identical) and
   the causal artifact (now regenerated). See Finding 6.

---

# Pass 5 — the three parked defects, fixed

These were parked as "modeling choices". They were not. Two produced wrong
numbers and one was a wrong implementation. All three are now fixed.

## F9 — the H1 storage gate used current-vintage data (fixed)

`raw_WGTSTUS1.csv` / `raw_WDISTUS1.csv` are the current vintage. EIA revises
weekly stocks, so historical dates held numbers not public at the time.

Fix: rebuilt the gate from the **as-published** EIA WPSR archive
(`scripts/fetch_wpsr_vintage.py`, 788 releases, 2011-08-03 to 2026-09-16,
zero misses, `engine/eia/raw_wpsr_vintage_gs.csv`). Release date is the
availability date, so no separate lag is needed.

Revision size measured: only **4 of 788** releases differ from the current
vintage by more than 0.01%; median revision is exactly 0; mean |revision| is
0.005% of level. Consecutive releases carry identical prior-week values.
So the *revision* content is negligible.

But **availability alignment** matters a lot. As-published is now the default:

| variant | revised H1 | as-published H1 |
| --- | ---: | ---: |
| fixed / futures | Sh 0.853 | **Sh 0.701** |
| causal / futures | Sh 0.704 | **Sh 0.595** |
| fixed / spot | Sh 0.385 | **Sh 0.464** |
| causal / spot | Sh 0.601 | **Sh 0.572** |

The revised series was indexed by week-ending date plus six days; the
archive is indexed by actual release date. That timing was worth up to 0.15
of Sharpe. `H1_SOURCE=revised` restores the old behaviour for comparison.

## F10 — the fixed-control walk-forward was in-sample for 2012-2018 (demoted)

The four fixed controls were selected on 2007-2018, and the evaluation then
started in 2012. So seven of fifteen evaluation years used controls fitted
partly on themselves. That is a straight selection error.

The causal variant is unaffected: it re-derives every control per year on
prior data only, so it is the honest headline.

Clean, post-selection segment (2019 onward):

| panel | 2012-2026 (overlap) | 2019-2026 (clean) |
| --- | ---: | ---: |
| futures | Sh 0.701, t +2.83 | **Sh 0.758, t +1.68** |
| roll-free spot | Sh 0.464, t +1.80 | **Sh 0.453, t +1.21** |

Nothing is significant on the clean segment.

## F11 — a missing price leg silently contributed zero (measured, bounded)

`DataFrame.sum(axis=1)` skips NaN, so a leg with a missing price contributed a
0 return instead of being handled explicitly. Measured impact on the frozen
panel: `crack_321` has **2** NaN days (0.04%), `bzwti` has **73** (1.51%),
`ng` none. The quoted walk-forward results use `crack_321` only, so they are
essentially unaffected. The effect is confined to multi-factor aggregation in
the superseded CORE3 book, where it understates exposure slightly on about
1.5% of days for one of three factors. It does not create phantom profit.

The tool backtester drops missing rows explicitly (`prices.dropna()`), so the
production path does not have the problem. Recorded as a bounded limitation
rather than changed, because changing the frozen engine would change its
manifest hash and the superseded numbers it produced are already bannered.

## Honest results after pass 5 (availability-correct H1, roll-free where noted)

| strategy / panel | ann | Sharpe | MaxDD | block t | DSR |
| --- | ---: | ---: | ---: | ---: | ---: |
| FIXED / futures | +10.03% | 0.701 | -18.3% | +2.83 | 0.386 |
| FIXED / roll-free spot | +6.77% | 0.464 | -22.2% | +1.80 | 0.071 |
| CAUSAL / futures | +8.24% | 0.595 | -23.6% | +2.55 | 0.210 |
| CAUSAL / roll-free spot | +7.95% | 0.572 | -20.3% | +2.23 | 0.146 |
| CRUSH / futures | +8.07% | 0.558 | -21.8% | +2.41 | 0.174 |
| CRUSH / roll-free spot | +8.59% | 0.628 | -20.4% | +2.40 | 0.205 |

Excluding March 1 on the futures panel: fixed Sharpe 0.453 (t 1.77), causal
0.314 (t 1.20), crush 0.256 (t 0.99). On roll-free spot the March exclusion
barely moves anything, as it should.

At measured cost (16-24 bps per side) and on the clean post-selection segment,
nothing reaches significance.
