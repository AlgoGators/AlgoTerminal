> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Batch 2 — alpha source map, medium items (preregistered)

Rows covered: 4 (electrical load), 5 (other products), 6 (increasing
demand/supply), 8 (tightness-ending short entry), 12 (Brent-WTI
composition). All rules stated before measuring.

## Data feasibility (probed)

- Item 4: EIA weekly electricity generation 400 on probed codes.
  NYISO public CSVs 404. Fallback: degree days derived from NASA POWER
  NYC T2M (HDD, CDD). This qualifies as POWER-derived per the source
  map.
- Item 5: jet fuel stocks empty. Propane stocks WPRSTUS1 available
  1993-2026. Jet/naphtha remain data-constrained; propane is the
  testable other product.
- Item 6: weekly product supplied route not found on probed routes
  (wpsd 400, wiup/stoc empty). Fallback: the stock-change demand proxy
  (product draw) already built. Retest its flipped direction
  confirmatorily.
- Item 12: quality/composition series not freely available. Proxy:
  crude-glut conditioning with WCESTUS1 (crude excl SPR) same-month z.

## L4 — electrical load (source 4)

Mechanism: extreme heating or cooling load shapes product demand and
run rates.

- HDD = max(0, 18 - T2M), CDD = max(0, T2M - 18), NYC daily.
- Same-month expanding z (min 30 obs). Power-demand state = HDD z
  >= 1 or CDD z >= 1, evaluated at t-1.
- Tilt: scale crack_321 and cross longs 1.25 in the state, else 1.0.
- Controls: shuffled state (20), inverted state.

## L5 — other products (source 5)

Two testable halves.

- L5a distillate winter peak: HO crack longs scale 1.25 in Dec-Feb,
  else 1.0. Standalone HO leg stats vs plain.
- L5b propane supply gauge: HO longs scale 1.25 when propane same-
  month z <= -1 (low stocks), 0.75 when z >= +1. Standalone HO leg
  stats.
- One book variant: champion plus winter-tilted HO leg, 4-leg equal
  weight.
- Jet/naphtha: constrained; recorded in the map.

## L6 — demand/supply proxy confirmatory retest (source 6)

Phase 3 T2's flipped direction (scale crack longs up when product
stocks build) beat its control at book level. Confirmatory retest at
leg level, one pre-registered direction, shuffled control.

- Tilt: crack_321 and cross longs 1.25 when product-change same-month
  z >= +1 (building), 0.75 when <= -1, else 1.0.
- Adoptable only if it beats the shuffled control by >= 2 sd at book
  level and does not degrade IS.

## L8 — tightness-ending short entry (source 8)

Builds on Phase 1R S3 (expansion-regime short of the most-stretched
leg). Adds the physical confirmations that are supposed to end
tightness.

Entry (all at t-1): short crack_321 and short most-stretched cross leg
when:
- seasonal z >= +0.75 (stretched), and
- level above trailing 252-day mean (expansion regime), and
- utilization >= 90 (pinned), and
- product stock change same-month z >= +1 (rebuilding).
Exit: z <= +0.5.

Book: short legs + bzwti, equal weight. Compare vs Phase 1R S3 (book
ov 0.16). Control: shuffled confirmation labels (20).

## L12 — Brent-WTI crude-glut conditioning (source 12)

Mechanism proxy: when crude stocks are high (glut), WTI discounts
and the spread reversion is stronger.

- Tilt: scale bzwti positions 1.25 when WCESTUS1 same-month z >= +1,
  0.75 when z <= -1, else 1.0.
- Book: champion legs with the bzwti tilt. Controls: shuffled (20),
  inverted.

## Deliverables

findings/batch2_findings.md. Statuses updated in
research/alpha_source_map.md.
