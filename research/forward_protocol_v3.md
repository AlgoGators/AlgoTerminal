# Forward protocol v3 — roll-free crush, measured cost

Supersedes `forward_protocol_v2.md`. v2 is void because it froze the
artifact-contaminated setup: instruments `CL=F, RB=F, HO=F`, assumed
costs `5/20`, entry `-0.75`, and the `panel_v2` hash. See
`findings/artifact_audit.md` for why those are unusable.

## Why this exists

The rolled continuous-futures panel carries a scheduled construction
artifact. The 3:2:1 crack built from `CL=F/RB=F/HO=F` gains
**+3.915 $/bbl every March for 18 of 18 years** and repays it across the
other months. Those sessions were 40.2% of the reported P&L. The signal
also inherits the distortion, because the March seasonal norm is built
from prior Marches that are already post-switch.

A forward test on the old panel would test the artifact, not the edge.

## Candidate

One frozen rule. No alternatives run in parallel.

- Signal: crush z on the **roll-free** 3:2:1 crack
  (`(2*gasoline + distillate)/3 * 42 - WTI`, EIA daily spot).
- Entry: `z <= cut`, crush regime only (`comp` or `norm`).
- `cut` from `ENTRY_RULE=contiguous_crush` (walk up from the lowest
  eligible z-bin while bin t >= 1.5), fit on prior data only.
- Exit, stops, cooldown, circuit breaker, trail: unchanged from
  `scripts/walkforward_causal.py`.
- Sizing: 10% per-trade loss budget, ES5-derived gear.

### Disclosures (must be stated in every report)

1. The entry threshold is a **selection**, not a derivation. It wanders
   from +0.70 to -0.91 across training windows and is not pinned by the
   data. It is frozen here and must not be re-tuned.
2. The architecture (single crack sleeve, regime gate, drawdown layer)
   was chosen on the full 2007-2026 sample.
3. Honest backtest expectation on roll-free prices: ann +4.7% to +8.4%,
   Sharpe 0.39 to 0.67, block t 1.4 to 2.5. No variant is significant.

## Cost model (measured, not assumed)

One 3:2:1 crack unit = 3 CL + 2 RB + 1 HO = 1,000 bbl of spread.

| component | value | source |
| --- | --- | --- |
| exchange + clearing | $1.60 per contract per side | CME 2025 non-member, NYMEX energy |
| NFA assessment | $0.02 per contract per side | NFA |
| commission | $0.00 to $2.50 per side | retail band |
| slippage | one tick round trip | CL $10.00, RB $4.20, HO $4.20 |

Round trip per crack unit: **$62.04** (no commission) to **$92.04**
($2.50/side) = **16.2 to 24.0 bps per side** of the crack level.

The harness assumed 5 bps per side. That is low by a factor of 3.2 to
4.8. At 16-24 bps the roll-free block t falls to 1.9-2.3 on the causal
variants and 1.0-1.2 on the fixed benchmark.

The roll drag is separately measured: realized carry is about
-0.3%/yr (harness assumed -20 bps/yr). Same order, kept as is.

## Daily log (append-only)

One row per session: date, spot legs, roll-free crack level, z, regime
state, H1 state, target position, gear, per-side cost applied, gross
return, net return, equity, realized slippage, kill alerts, notes.
Every input timestamped and hashed. Late data quarantined, never
backfilled.

## Kill rules

- daily net loss -3%, or single mark-to-market -5%: flatten, review
- account drawdown -15%: kill
- stale or non-finite input: flat
- realized cost above 30 bps per side, or fill below 80%, for 5
  sessions: pause
- no discretionary signal override; operator may flatten for safety
  with a reason

## Acceptance gates

Stage 1: 20 sessions operational (inputs on time, signal reproduces,
reconciliation clean).

Stage 2: 300 sessions / 18 months. Required: positive net return, median
63-day return positive, realized cost at or below 30 bps per side,
independent ledger recomputation matches, worst day at or better than
-5%, drawdown within -15%.

No Sharpe gate is used. The backtest cannot support one: on roll-free
prices the edge is not statistically significant, so a forward Sharpe
target would be a claim the evidence does not support.

A pass supports a small staged allocation only. It does not confirm the
historical backtest, and it does not scale from it.

## Reference

- Audit memo: `findings/artifact_audit.md`
- Claims ledger: `findings/claims_ledger.md`
- Cost model and sensitivity: `scripts/artifact_audit.py`
- Harness: `scripts/walkforward_causal.py` (`ENTRY_RULE=contiguous_crush`)
