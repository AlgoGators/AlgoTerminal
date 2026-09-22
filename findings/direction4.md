> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Direction 4 — open new areas (findings)

Date: this session. Harness: `direction4_harness.py`. Prereg:
`research/direction4_open_areas.md` (b7cc862).

## A. COT / positioning (chain ch19)

- RBOB managed-money net fetched (CFTC 72hh-3qpy): 1057 weekly rows
  2006-2026 (effective +5 days, forward-filled).
- Crude NYMEX WTI absent from both the futures-only and futures-and-
  options public datasets (only ICE and E-mini present) ->
  CONSTRAINED.
- RBOB net z vs fwd20 crack: non-monotone, b0 -1.4% to b4 +1.6%;
  net z vs CL flat. Change z flat.
- Control: real top-bottom +2.96% vs random 20% slices mean +3.47%
  sd 0.92%. Within noise.
- Verdict: no meaningful 20-day positioning link at this granularity.
  Weak-to-absent. ch19 stays theoretical for 20d horizons.

## B. International cracks

Route `petroleum/pri/intl` returns 400 for all probed series.
CONSTRAINED. No proxies built.

## C. Named events (descriptive, 20d forward of crack_321)

Unconditional OOS fwd20 mean +3.15%.

| Event | fwd20 | | Event | fwd20 |
| --- | ---: | --- | --- | ---: |
| hurricane_ike | -40.5% | | opec_2020_mar | +43.6% |
| hurricane_isaac | -1.6% | | opec_2020_apr | -35.6% |
| hurricane_harvey | -13.0% | | opec_2022 | -21.5% |
| hurricane_ida | +2.3% | | covid_pandemic | +45.4% |
| tx_freeze | +10.3% | | neg_wti | -29.3% |
| opec_2014 | -1.0% | | opec_2016 | -5.7% |

Pattern: crisis troughs (COVID, OPEC-fail, freeze) precede big
positive crack forward moves; hurricane landfalls and post-spike
normalizations precede big negative moves. Consistent with the
crisis-reversion structure; descriptive, small n.

## D. Per-complex overlay (Round 4 reserve, now tested)

| Variant | OOS ov Sharpe | OOS ov DD | worst |
| --- | ---: | ---: | ---: |
| Champion (book overlay) | **0.862** | -10.73% | -2.85% |
| Champion + Brent, book overlay | 0.552 | -16.67% | -7.51% |
| Two-sleeve overlay (per-complex) | 0.425 | -19.49% | -5.62% |

Adding Brent legs hurts under BOTH overlay schemes. The per-complex
overlay does not rescue the reserve; it is worse. The Round 4 reopen
for Brent legs is now tested and rejected at the clean level.

## Ledger additions

- RBOB COT 20d link: FALSIFIED/weak (within noise).
- Crude COT series: CONSTRAINED.
- International cracks: CONSTRAINED.
- Named events: descriptive; crisis-trough entries consistent with
  crisis reversion (IDEA, small n).
- Per-complex overlay + Brent: FALSIFIED (0.425-0.552 vs 0.862).
- Brent legs in either overlay scheme: FALSIFIED at book.

## Artifacts

- `direction4_harness.py`, `results/direction4.csv`
- `engine/cot/raw_cot_rbob_all.csv`, `raw_cot_crude_all.csv`
