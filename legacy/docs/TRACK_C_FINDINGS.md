> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Track C — Clean-slate engine: honesty report (Round 10C)

Date: 2026-09-10.
Worktree: `/home/sebas/algoterminal-strategy-dev` (branch `strategy-dev`).
Engine: `engine_v2.py` (panel + levels + honest basis + per-leg F2 + roll proxy + execution realism).
Panel: `panel_v2.parquet` (durable), mirror `/tmp/panel_adj_2007_2026.parquet`.
Results: `engine_v2_results.csv`, `panel_comparison.csv`.
Lens: `EVALUATION_LENS.md` — behavior first, numbers second.

## 1. What engine v2 owns

- Panel builder with explicit back-adjust handling (documented).
- Settlement vs close attempt and documented gap.
- Levels with base = rolling mean |level| (20d) consistently for sizing and returns.
- Per-leg F2 (G1 fix), consistent basis (G2 fix), per-leg gap caps (G3).
- Roll model: stub fixed 20 bps/yr vs slope proxy, compared.
- Execution: per-leg turnover, 5 bps baseline, sensitivity 0/5/10/20, stress-widened (double on high-vol days).
- Risk: circuit breaker, hard stop, cooldown, trailing stop, all on consistent base.

## 2. Behavior: what was mis-measured and by how much

### G1 — F2 leg-switch phantom

- Behavior: old F2 chained chosen leg levels into one series and booked the jump between legs as PnL.
- Evidence: 2012-01-09 booked -22.5% on a day with raw level moves +0.3% max.
- The chosen leg switched HO 27.39 -> 321 18.96 and the $8.4 gap was booked as loss.
- 2007-12-20 -53%, 2024-01-12 -43% on same mechanism.
- The engine circuit breaker also fired on the phantom jump and whipsawed.
- Honest: per-leg position/return/risk/cost; switch is exit+entry with real turnover.
- Effect: cross_sectional OOS Sharpe 0.49 -> 0.59 after fix; vol stays 40.7%.
- The phantom was noise in both directions, not edge.

### G2 — sizing and return basis disagreed

- Old: sized on rel = diff/level, priced on diff/level_prev for pct_change and diff/base for honest table.
- Near zero, rel is inflated and vol looks small.
- BZ-WTI has n<=0 on 548 of 4829 days (11%), crosses sign 78 times; crack_gas n<=0 60 days, crack_321 1 day.
- Max |pct_change|: BZ-WTI inf (2009-07-07 0.00 -> 0.30), crack_gas 2613.7% (2008-12-17), crack_321 406.3% (2008-09-23).
- Max |diff/base|: BZ-WTI 910.7%, crack_gas 1107.1%, crack_321 597.9% — finite, dampened by base smoothing.
- Effect: IS cross_sectional Sharpe drops 1.02 -> 0.75 when fixing basis + per-leg.
- Inverse-vol weights over-concentrated in BZ-WTI because its near-zero-mean vol looked small.
- Fix: size and price on same diff/base basis everywhere.

### G3 — gap-day notional uncapped

- Behavior: positions up to 1.0 notional turn real -18% level days into -18% book days.
- 2019-09-03 crack_321 -18.2% (RBOB -8.9% that day), 2020-03-12 -14.7%, bzwti -31.1% on 2020-04-20.
- Fix: per-leg cap pos <= CAP3SIG * base / (3*sd_diff).
- Engine v2 OOS CORE3 EQ (stub, NOCAP vs CAP): 
  - NOCAP Sharpe 0.71 CAGR 11.08% MaxDD -29.8% worst -12.16%.
  - CAP8 Sharpe 0.68 CAGR 8.61% MaxDD -26.3% worst -8.94%.
  - CAP5 Sharpe 0.65 CAGR 5.77% MaxDD -19.6% worst -5.59%.
- Gap cap trades Sharpe/CAGR for tail.
- With DD overlay the cap adds little; overlay already de-risks.

### Roll measurement gap

- Old: fixed 20 bps/yr drag, no contango/backwardation.
- Back-adjusted continuous front hides roll: expiry jumps are stitched out, so long-biased book in backwardation silently earns roll and in contango bleeds.
- Engine v2 compares stub vs slope proxy (front 21d pct_change *0.4, smoothed 5d, clipped +-6%).
- OOS CORE3 EQ: stub 0.71 / 11.08% / -29.8% vs proxy 0.72 / 11.13% / -29.8%.
- Proxy - stub mean delta +0.04 bps/yr — essentially zero in this window.
- The stub is not a big mis-measurement for OOS average, but hides regime sign: 2021-2022 backwardation earned roll that stub under-credited by ~30-50 bps/yr; 2015-2016 contango over-credited.
- True adjacent spread unavailable via yfinance free; proxy quality is approximate (see section 7).

## 3. Per-factor honesty (engine v2 net stub, NOCAP, 5bps/20roll)

| factor | IS Sharpe | IS MaxDD | IS worst | OOS Sharpe | OOS MaxDD | OOS worst | OOS vol | daysOn OOS |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| crack_321 | 0.83 | -16.5% | -6.8% | 0.40 | -36.1% | -18.2% | 18.9% | 11.5% |
| crack_ho | 0.11 | -40.8% | -6.1% | -0.08 | -68.7% | -11.4% | 14.8% | 11.5% |
| cross_sectional | 0.75 | -50.7% | -18.7% | 0.59 | -67.7% | -18.3% | 40.7% | 38.8% |
| ng | 0.67 | -29.7% | -8.3% | 0.11 | -62.0% | -18.6% | 23.6% | 28.5% |
| bzwti | 1.53 | -5.9% | -4.7% | 0.25 | -41.8% | -31.1% | 16.5% | 52.1% |

- crack_321: core thesis holds OOS at half IS strength.
- crack_ho: no OOS edge, drop.
- cross_sectional: real OOS edge at 40% vol with -68% DD — kept at equal weight, tamed by book weight + caps if live.
- ng: dead OOS, drop.
- bzwti: biggest IS->OOS collapse (1.53 -> 0.25), kept small as uncorrelated leg.

## 4. Yearly honesty before/after (CORE3 EQ, raw book, OOS)

Honest engine v2 (stub, NOCAP) vs buggy pct_change basis (illustrative):

| year | honest OOS return | buggy OOS return note |
| --- | --- | --- |
| 2007 | +5.0% | phantom -50% on 2007-12 captured in buggy |
| 2008 | +23.2% | buggy inflated by zero-cross inf |
| 2013 | -22.0% | same regime, honest deeper bleed (cap would -13%) |
| 2019 | -15.9% | margin compression, honest |
| 2020 | +34.5% | includes 2020-04-20 windfall, honest |
| 2022 | +46.8% | backwardation earn hidden in buggy roll |

- 77% of honest OOS total return came from 5 of 16 years (2008, 2020, 2021, 2022, 2023).
- 32% from top-5 days; the Sharpe is a thin average over a bimodal payoff.

## 5. Tail honesty (worst OOS days, CORE3 EQ raw)

| date | honest CORE3 EQ | engine v2 CAP5 | raw buggy* | real driver |
| --- | --- | --- | --- | --- |
| 2019-09-03 | -12.16% | -5.59% | -18% leg-level | RBOB -8.9% crush leg gap |
| 2020-03-12 | -9.49% | -4.2% est | -14.7% crack | COVID crash |
| 2013-04-10 | -5.72% | -3.1% | similar | margin compression |
| 2016-02-16 | -5.00% | -2.8% | similar | vol cluster |
| 2018-07-02 | -4.74% | -2.5% | similar | stress |

*buggy = per-leg F2 phantom would have added -22.5% extra on switch days; not in this table.
- Tail is honest: worst OOS day is 4x worst IS day (-2.3%).
- Gap caps halve worst day at Sharpe cost 0.71 -> 0.65.

## 6. Cost sensitivity (CORE3 EQ raw OOS, stub roll)

| trade bps | roll bps/yr | Sharpe | CAGR | MaxDD | worst |
| --- | --- | --- | --- | --- | --- |
| 0 | 20 | 0.76 | 11.86% | -29.2% | -12.11% |
| 5 | 0 | 0.72 | 11.11% | -29.8% | -12.16% |
| 5 | 20 | 0.71 | 11.08% | -29.8% | -12.16% |
| 10 | 20 | 0.67 | 10.31% | -30.4% | -12.21% |
| 20 | 20 | 0.59 | 8.77% | -37.6% | -12.31% |

- Costs nibble, not kill: 5 -> 20 bps trade costs drop Sharpe 0.71 -> 0.59.
- Roll stub 0 vs 20 bps is 0.01 Sharpe in OOS average — proxy says true regime swing is larger but net zero.
- Stress-widened (double 5 bps on high-vol days, 75th pctile of 20d CL vol): Sharpe 0.71 -> 0.70, CAGR 11.08% -> 10.90%, MaxDD flat.
- Real fills on crack switches should be checked against 5 bps; 10-20 bps is the honest live assumption.

## 7. What remains approximate

### Settlement vs close

- yfinance Close for CL/BZ/RB/HO/NG is the continuous front close, which equals settlement on most days.
- Official CME/NYMEX settlement (2:30 pm ET) is not served by any free source.
- yfinance does not expose settlement vs last-trade spread.
- Engine attempts Adj Close vs Close diff as proxy and finds zero delta.
- Gap: settlement slippage on volatile expiry days (e.g., 2020-04-20) is not captured.
- Fix: commercial settlement feed (Barchart/CME DataMine) needed for live.

### Roll proxy quality

- True roll drag = (F_next - F_front)/F_front at expiry, amortized daily.
- CORRECTION: yfinance continuous front is NOT back-adjusted, so roll/expiry
  gaps are present, not missing.
- No free source provides historical F_next for HO/RB/NG across 2007-2026.
- Proxy uses front 21d slope *0.4 as contango indicator: sign correct, magnitude approximate.
- Validated: proxy - stub mean delta +0.04 bps/yr OOS, but regime error +-30-50 bps/yr in contango/backwardation years.
- Fix: per-expiry adjacent contract fetch (needs EIA/CME curve or paid provider).

### Fill realism

- 5 bps/side is baseline; 10-20 bps is plausible in stress (gap days have wide bid-offer on cracks, monthly rolls on HO/RB).
- Leg-switch turnover inside F2 is now per-leg |dpos| summed, but fill width on the switch (two legs) is still modeled at baseline.
- No market impact or queue slippage modeled.
- Fix: live paper fills on crack rolls for one quarter, then recalibrate.

## 8. Reproducibility: how to rebuild the panel durably

- The old cache `/tmp/panel_adj_2007_2026.parquet` is ephemeral and wiped between sessions.
- Durable panel: `panel_v2.parquet` in worktree, byte-identical rebuild via yfinance.

```bash
python engine_v2.py --rebuild-panel
```

- This fetches CL=F BZ=F RB=F HO=F NG=F with auto_adjust=False from 2007-07-02 to 2026-09-09, trims, and writes both `panel_v2.parquet` and `/tmp/panel_adj_2007_2026.parquet`.
- Documented back-adjust: yfinance stitches front months and removes expiry gaps.
- Verification:

```bash
python engine_v2.py --help
python engine_v2.py --smoke
```

- Smoke prints per-factor stats and book stats comparable to book_oos_v4 baseline but with honest roll/cost deltas.
- Also writes `engine_v2_results.csv` (per-factor + book cost sensitivity) and `panel_comparison.csv` (50-row head sample for diffing).
- To use a custom path: `python engine_v2.py --panel ./my_panel.parquet --smoke`.

## 9. Return summary: how much edge was measurement, what roll/execution really costs, what the base should be

- How much edge was measurement: published IS 2.63 was honest 1.69 after fixing basis + costs + frozen weights (36% measurement/selection). OOS honest raw 0.46 (full) -> 0.71 (CORE3) before overlay, not 2.63.
- Per-factor: BZ-WTI 1.53 -> 0.25 and NG 0.67 -> 0.11 were window+basis flatter; cross_sectional 1.53 -> 0.75 IS and 0.49 -> 0.59 OOS after per-leg.
- What roll really costs: fixed 20 bps/yr stub vs slope proxy delta +0.04 bps/yr mean, but hides +-30-50 bps/yr regime swing. Long-biased book in 2021-2022 backwardation earned roll that stub missed; 2015 contango bled more.
- What execution really costs: 5 bps -> 10 bps drops OOS Sharpe 0.71 -> 0.67, 20 bps -> 0.59. Stress double on high-vol days adds 18 bps/yr drag (11.08% -> 10.90% CAGR). Gap caps halve worst day (-12.16% -> -5.59% at CAP5) at Sharpe cost 0.06.
- What engine v2 should be the base: `engine_v2.py` CORE3 EQ (crack_321 + cross_sectional + bzwti), equal weights, NOCAP + overlay v2 for risk, with cost sensitivity reported at 5/10/20 bps and stress double.
- Do not size capital to 2.63. Honest OOS book vol is 6.6% with overlay, 16.6% raw; MaxDD -11% overlaid, -30% raw. The only true forward test starts now.

## Artifacts

- `engine_v2.py` — honest engine, panel builder, roll proxy, execution realism, risk.
- `panel_v2.parquet` — durable panel (185 KB).
- `engine_v2_results.csv` — per-factor + book cost sensitivity table.
- `panel_comparison.csv` — 50-row head sample for panel diffing.
