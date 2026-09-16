# Next directions — batch preregistration

Order per the analysis: (7) forward readiness, (1) model risk layer,
(3) cold power, (4) gas-HO relative, (2) utilization surprise.
All methods fixed before measuring. Clean non-overlap blocks.

## P7 — v2 forward protocol for B1h (document)

B1h is the candidate. The frozen v1 protocol governs the champion.
This prereg fixes the v2 paper protocol: release manifest (engine
files, panel hash, parameter card), daily append-only log, kill
rules (daily -3%, account -15%, stale data flat, slippage pause),
acceptance gates (300 sessions / 18 months, positive net, Sharpe
>= 0.5, DD <= -15%). No discretionary overrides. Written to
research/forward_protocol_v2.md.

## P1 — model-based risk layer (ES-derived gear, no ladder)

Replace the V2 overlay with a distribution-derived exposure gear:
- gear_state = min(1.0, BUDGET / |ES5_state|), BUDGET = 10% over
  20 days (preregistered).
- ES5_state from the crush-state mixture (measured -27.4%).
  constant gear = 10 / 27.4 = 0.365 for the crush-holding book.
- Applied causally at t-1; no path-dependent drawdown machine.
Test: B1h + gear vs B1h raw vs champion-with-overlay on clean
blocks (OOS/FULL). Acceptance: CIs exclude zero; DD <= champion
overlay DD; dimension note: constant scaling keeps Sharpe, scales
DD.

## P3 — cold severity power at 5/10-day horizons

Same phenomenon (P1), smaller horizons give larger non-overlap
samples. Bucket NYC HDD z in winter; fwd5/fwd10 of crack_gas;
non-overlap steps 5 and 10. Report monotonicity, delta, shuffled
control. Adopt as a sizing tilt only if the cleaned delta holds.

## P4 — gas-HO relative spread (distillate channel)

rel_ret = ret_HO - ret_gas (engine basis). rel_z = seasonal z of
(crack_ho - crack_gas). Bucket rel_z by season; winter expectation:
low rel_z precedes positive relative forward (crushed distillate
relative reverts). Non-overlap, control. Distinct from the dead
standalone HO leg.

## P2 — utilization-surprise tilt on B1h

State surprise S_t = same-month z of weekly utilization change.
Variant: scale the crush position 1.25 when S_t <= -1 (supply
falling), else 1.0. Clean blocks vs B1h. From the maintenance
channel; Phase 3 direction was validated pre-ladder.

## Deliverables

findings/next_direction.md, research/forward_protocol_v2.md,
ledger rows.
