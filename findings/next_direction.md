> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Next directions — findings

Date: this session. Harness: `next_harness.py`. Prereg:
`research/proceed2_next.md` (8e6078d). Forward protocol v2:
`research/forward_protocol_v2.md`.

## P1 — ES-derived risk layer (the unlock)

| Variant | OOS ann (t) | FULL ann (t) | DD | worst | neg% |
| --- | ---: | ---: | ---: | ---: | ---: |
| B1h raw | +15.55% (2.93) | +15.46% (3.33) | -28.46% | -18.9% | 16% |
| **B1h + ES gear (0.365)** | **+5.67% (2.93)** | **+5.64% (3.33)** | **-11.03%** | -6.9% | 16% |
| Champ overlay (reference) | +5.63% (3.06) | +5.37% (3.30) | -10.73% | -4.3% | 21% |

The distribution-derived gear (10% budget / 27.4% ES5) replaces the
V2 ladder with a constant, pre-registered exposure. Result:
- Holds cleanly (CIs exclude zero, same t as raw: constant scaling
  keeps Sharpe).
- Drawdown -11.03% vs champion overlay -10.73% (within 0.3 pt;
  passes the 1-pt bar).
- Fewer negative blocks (16% vs 21%) and a principled ES budget
  instead of a path-dependent state machine.
P1 PASSES: the model-based risk layer is the designed replacement for
the overlay.

## P3 — cold severity at 5/10d

Non-monotone at both horizons (fwd5: 5.4/4.1/2.2/4.3/4.4; fwd10:
10.3/9.1/6.3/8.2/7.1). Control delta ~0 vs random slice. The 20-day
severity monotonicity does not exist at 5/10d. P3: NOT adoptable.
Cold severity remains open (20d-only, underpowered, needs more data).

## P4 — gas-HO relative spread (new structure)

Winter rel_z buckets vs fwd20 of the gas-HO relative:
- Winter: b0 -3.4% to b4 -12.9% (the stretched HO-relative reverts
  down; the crushed HO-relative does NOT pay long in winter).
- Summer: b0 +7.1% to b4 +0.3% (crushed HO-relative reverts up).

Findings:
- The distillate-winter-long idea specifically fails (winter low
  rel_z forward is still negative).
- A seasonal conditional structure exists: long the HO-relative in
  summer when crushed (+7.1%); short the HO-relative in winter when
  stretched (-12.9%). Directional buckets, large cells, needs clean
  non-overlap + control before adoption. Recorded as a live lead.

## P2 — utilization-surprise tilt

B1h + util tilt: OOS +15.80% vs B1h +15.55%; Sharpe 0.748 vs 0.754.
Null. P2: no adoption.

## Ledger additions

- ES-derived risk layer: HOLD (replaces ladder, DD -11.0%, t 2.93).
- Cold severity 5/10d: FALSIFIED at those horizons.
- Gas-HO relative seasonal structure: DIRECTIONAL lead (clean test
  pending).
- Utilization-surprise tilt: NULL.
- Forward protocol v2 for B1h: WRITTEN (research/forward_protocol_v2.md).

## Artifacts

- `next_harness.py`, `results/next_direction.csv`
