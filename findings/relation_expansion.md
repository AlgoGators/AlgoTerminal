> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Relation map expansion — full decomposition pass

Date: this session. Store: `research/graph/{nodes,edges,chains}.csv`,
queried with `graph_web.py`.

## What was added

- Nodes: 46 -> 146. Concepts, data series, evidence, chains.
- Edges: 44 -> 183, each tagged with relation, chain, evidence,
  status, and data source.
- Chains: 11 -> 25.

## Methodology applied

Every idea from the captain's breakdown was decomposed into
structure, each piece tagged with what it indicates, and connected
piece -> piece -> market. Edges carry truth state:
confirmed / weak / inferred / absent / constrained / proposed, and
untested / confirmed / tested-killed / evidence-partial.

New chain families by captain source:

| Chains | Sources covered |
| --- | --- |
| ch12 seasonal demand | calendar, holidays, shoulder, winter distillate |
| ch13 refinery ops, ch14 capacity | maintenance (killed tilt, decomposed structure), capacity, technology |
| ch15 crude flows, ch16 product trade | supply/demand, technology |
| ch17 storage cycle | storage buffer, injection, winter fill |
| ch18 pipelines | logistics, regional |
| ch19 flow-positioning | COT, OI, curve, carry, reversal speed |
| ch20 structural events | IMO2020, COVID, sanctions, EV, efficiency |
| ch21 market structure | participants and instruments |
| ch22 crude quality detailed | Brent-WTI composition |
| ch23 weather regime | cold, hurricanes, freeze |
| ch24 demand structure | subgrades, octane, ethanol, travel |
| ch25 model components | Phase 4: m = norm + D + S + B + R, regime gate |

## Honest ledger (what is still untested)

Evidence-confirmed: ch2, ch3, ch4, ch7, ch8 (P2, P1, M7, P5).
Evidence-partial: ch1, ch12, ch13, ch17, ch19, ch20, ch23.
Tested-killed: ch9, ch10, ch11.
Constrained: ch5, ch22.
Proposed (model assembly): ch25.
Untested links remain tagged untested. Nothing is promoted without a
Tier 1 test.

## Hubs after expansion

- gas-crack: degree 21, spanning 15 chains. The market junction of
  the whole web.
- gas-demand: degree 13.
- cold, reversion, crude-mix, season: the next tier of junction
  concepts.
- r_t (residual model component): degree 7, the Phase 4 crux.

Cross-chain path example (machine-found): blend-cost -> gas-crack ->
carry -> r_t -> reversion. Blend economics connect to the flow
residual through the futures curve.

## Next step

The curated graph is the truth layer and now holds the full web.
The graphify auto-build over research/ and findings/ is the agreed
discovery layer on top, to run next.
