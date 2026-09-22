> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Relation map — decompose, connect, then apply

The unit of work is the breakdown of each idea into its structure,
the connections between pieces, and the chains that end in some
observable market behavior. Strategy construction waits for a chain
that is supported end to end.

Method per idea:
1. Decompose: list the dimensions and constituents.
2. Indicate: for each piece, what can it tell us? (performance,
   conditions, cost, timing, participants)
3. Connect: build chains piece -> piece -> ... -> market (price,
   volatility, inventories, participation).
4. Test links: one simple evidence test per link, no strategy.
5. Apply: only a complete, supported chain becomes a position rule.

## Worked example: fuel blends

Composition: butane, alkylate, reformate, isomerate, ethanol; RVP and
octane specs; regional grades (RFG, CARB, conventional).

Seasonal constraint: summer RVP cap (~7.8 psi) forces butane out;
winter allowance (13.5-15 psi) pulls butane in. Blending is an
economic decision with a regulatory calendar.

Chains:
- RVP calendar -> butane in/out of gasoline -> propane/NGL surplus
  (summer) and draw (winter) -> blend cost -> crack seasonality.
  Testable: propane stocks WPRSTUS1 by season vs crack behavior.
- Spring deadline -> blend switch + maintenance + summer-grade
  injection -> coordinated supply event -> margin compression, vol
  jump, weak reversion in April (measured P2).
- RB futures are the blendstock for oxygenate blending; blend
  economics are inside the RB crack (panel already).

Evidence status: P2 (drop in reversion edge, vol jump) confirmed.
Butane/propane link untested.

## Worked example: cold weather

Decomposition: cold start enrichment, warmup time, air density drag,
tire pressure, cabin heating, cold battery/EV effects, diesel cold
flow (gelling), propane rural heating.

Chains:
- T2M z -> per-mile fuel consumption -> gasoline demand -> crack_gas
  forward strength. Evidence: P1 winter-monotone, NYC severity.
- Cold -> distillate heating plus propane heating -> HO/propane
  seasonality. Evidence: HO forward after cold is negative (P1),
  opposite of gasoline: relative signal.
- AV: long-run dilution by EV fleet (item 7 drift).

## Worked example: Brent-WTI

Decomposition: grade quality (API, sulfur), logistics (Cushing
storage), export capacity, pipeline flows, contract mechanics
(physical vs cash), benchmark composition (North Sea grades).

Chains:
- Quality differential -> refinery value -> WTI discount.
- Logistics: Cushing fullness -> WTI discount.
- Export regime: pre-2016 trapped onshore, post-2016 globalized
  -> spread level regime change.
Evidence: Cushing H3 direction real but rare (Phase 3 / Round 6);
glut bucket proxy-poor (P7); quality series constrained.

## Remaining decompositions to write

- Maintenance turnaround calendar (item 1): what it is, when, why.
- Distillate and other products (item 5): heating season, jet, diesel
  gelling, propane.
- Electrical load (item 4): weather-driven load, run rates.
- Technological change (item 7): EV share, efficiency, closures.
- Storage buffer (items 6, 10): inventory regimes and margin response.
- Flow and positioning (item 14): open interest, COT, reversal speed.

## Working status

Each link gets a row: chain id, source node, target node, data used,
evidence (positive/negative/weak), status (untested/in-progress).
Strategy construction is gated on this map.
