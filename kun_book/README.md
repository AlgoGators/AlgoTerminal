# WTI Crack Spread Book

Three-leg seasonal mean-reversion book (WTI 3:2:1, gasoline, heating oil
crack spreads), combined inverse-vol-weighted.

## Setup

1. Install AlgoGatorsCLI (`algoterminal-cli`) if you haven't already.
2. Copy this zip's contents into your `~/.algoterminal/` directory, merging
   with (not overwriting) whatever's already there:
   - `universes/crack-spreads.yaml`
   - `research/wti-crack-spread-seasonal-mean-reversion/20260910-110617/`
   - `research/wti-gasoline-crack-spread-seasonal-mean-reversion/20260910-110619/`
   - `research/wti-heating-oil-crack-spread-seasonal-mean-reversion/20260910-110620/`
   - `composites/wti-crack-spread-book/20260910-105015/`

## Rerun on your own data

For each of the three leg slugs:

```
algoterminal data <slug>
algoterminal backtest <slug>
```

Then build the composite from your freshly-backtested legs:

```
algoterminal composite create "WTI Crack Spread Book" \
  --legs wti-crack-spread-seasonal-mean-reversion,wti-gasoline-crack-spread-seasonal-mean-reversion,wti-heating-oil-crack-spread-seasonal-mean-reversion \
  --weighting inverse_vol
algoterminal composite backtest wti-crack-spread-book
algoterminal composite writeup wti-crack-spread-book
```

## Notes

- `CRACK321`/`CRACKGAS`/`CRACKHO` are derived levels computed from CL/RB/HO/BZ
  futures closes (see `universes/crack-spreads.yaml`), not raw tickers.
- Each `hypothesis.yaml` risk_notes section has the full caveat list: cost
  sensitivity (0/5/10/25bps), the synthetic-spread/legging-risk gap, and a
  correction on the trade-holding-period vs. stated thesis mechanism. Read
  those before trusting the numbers on your own data.
- No numbers are bundled here on purpose — rerun `data`/`backtest` yourself
  rather than trusting a copied `backtest_results.json`.
