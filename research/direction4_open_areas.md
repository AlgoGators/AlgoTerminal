# Direction 4 — open new areas (preregistered)

## A. COT / positioning (chain ch19)

Fetch CFTC disaggregated futures-only COT for crude oil and RBOB
(via Socrata public API). Map weekly positions (report Tuesday,
released ~3 days later; effective with a further lag, forwarded onto
the daily panel). Tier-1 link test:
- COT managed-money net z (level and 4-week change) buckets vs
  fwd20 of crack_321 and CL.
- Control: shuffled COT labels (20 seeds) on the headline bucket.

## B. International cracks

Probe EIA weekly international spot prices (Rotterdam, Singapore).
If available, build Rotterdam gasoline crack (Rotterdam gasoline -
Brent) and Singapore gasoil crack (Singapore gasoil - Brent).
Report correlation with crack_321 and fwd behavior. If the route is
empty, mark CONSTRAINED.

## C. Named-event studies

Labeled windows (20d from event): hurricanes Ike/Isaac/Harvey/Ida,
2021 TX freeze, OPEC meetings (2014-11-27, 2016-11-30, 2020-03-06,
2020-04-12, 2022-10-05), COVID/negative WTI (2020-03-11,
2020-04-20).
Report per event: crack_321 20d forward from event and the champion
20d block return; a summary table vs unconditional mean. Descriptive,
labeled, small n.

## D. Per-complex overlay (Brent reserve)

Build Brent legs F5 (brent321 seasonal crush) and F6 (brent cross
most-crushed) from the panel. Two sleeves:
- WTI sleeve = champion legs (crack_321, cross_sectional, bzwti).
- Brent sleeve = brent321, brent_xs.
Apply the V2 overlay separately to each sleeve, then combine 50/50.
Compare vs: champion (book-level overlay) and champion+Brent with
book-level overlay. Metrics: OOS raw/ov Sharpe, DD, CAGR, worst day;
non-overlap blocks for the overlaid series with the path-dependence
flag.

## Deliverable

findings/direction4.md. Ledger additions.
