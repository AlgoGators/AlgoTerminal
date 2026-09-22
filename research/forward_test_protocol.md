# Frozen forward-test protocol: CORE3 EQ plus V2 overlay

## 1. Purpose and decision status

This document preregisters one paper-trading test.

It tests the corrected champion without further research or parameter selection.
A backtest or a pass here does not authorize investment.

The corrected audit reference is the CORE3 equal-weight book with V2 overlay:
OOS Sharpe 0.86, CAGR 5.6%, maximum drawdown -10.7%, annualized volatility
6.6%, and worst day about -2.85%, using 5 bps trading cost and 20 bps annual
roll drag.

The previously reported 0.95 Sharpe is not the target because later audit fixes
changed the result.

## 2. Frozen strategy

CORE3 has three equal-weight factors:

- `crack_321`
- `cross_sectional`
- `bzwti`

Use the corrected per-leg implementation in `book_oos_v4.py` and its imported
`factor_book.py`, or a byte-identical promoted copy.
The cross-sectional factor trades each selected leg separately.
A leg switch is an exit and a new entry.

Use `diff(level) / rolling_mean(abs(level))` for both returns and sizing.
Do not use `pct_change`.
Use no gap cap in the primary test.
A gap-cap shadow report may be produced only without changing orders.

Use equal factor weights.
Do not change factor membership, lookbacks, z thresholds, or sizing.

Apply the V2 overlay causally to the next session's exposure:

- Compute 20-session trailing book volatility from prior observations.
- Set volatility gear to `min(1.0, 0.10 / annualized_trailing_volatility)`.
- At experienced overlay equity drawdown of -6%, set strategy state to 0.5.
- At experienced overlay equity drawdown of -10%, set state to zero.
- On an engine equity new high, reset the state to full.
- Use only information available before the order.

Retain the corrected two-sided hard stop, circuit breaker, and five-session
cooldown from the audit engine.
The frozen engine parameters are 90-session seasonal-z history, 20-session
volatility lookback, 10% volatility target, 1.0 maximum factor leverage,
3-sigma daily circuit breaker, 20% entry-level hard stop, and five-session
cooldown.

## 3. Immutable release inputs

Before the first order, create a release manifest with a release ID and
SHA-256 hash for every item below.
Never replace an item in place.

- Strategy, overlay, and runner source files.
- Python version, dependency lock or exact package versions, and OS image.
- Instrument map: `CL=F`, `BZ=F`, `RB=F`, `HO=F`, and `NG=F`.
- The immutable historical panel used to seed rolling state.
- Every forward raw response, including provider, request parameters, retrieval
  time, timezone, and response hash.
- Exchange calendar, session labels, contract identifiers, roll dates, price
  field, adjustment method, and missing-data policy.
- Starting equity, currency, units, account permissions, and fee schedule.
- The complete parameter manifest in section 2.

Use completed daily observations only.
Do not backfill a missing close with a later observation.
Put late or revised vendor data in a quarantined correction file.
A correction cannot change a logged signal, order, or fill.
A code, data, universe, or parameter change requires a new release.

## 4. Daily operating and execution protocol

Run once after the official close and before the next session order cutoff.
Use signal state at `t-1` for exposure and fills at `t`.

Use a paper account with executable bid, ask, settlement, and fill timestamps.
Use only the approved contracts and mappings.
Do not substitute an ETF, spot series, or another continuous contract.

Submit marketable-limit or limit orders.
Record limit, quote age, latency, fill, partial fill, or rejection.
Do not trade when a required leg is stale, missing, duplicated, out of order,
or outside the configured session.
The default response is flat exposure.

No discretionary signal override is allowed.
An operator may flatten for safety, with reason and timestamp recorded.

## 5. Required append-only daily log

Write one UTC-timestamped row for every session, including no-order sessions.
Include:

- release ID, event sequence, code hashes, and data hashes;
- source IDs, input timestamps, raw closes, and freshness checks for every leg;
- constructed levels, seasonal z-scores, rolling volatility, and unscaled
  signals;
- factor weights, scaled positions, per-leg positions, gross and net leverage;
- hard-stop, circuit-breaker, cooldown, overlay state, gear, equity drawdown,
  and high-water marks;
- intended orders, quantities, prices, bid/ask, latency, fills, rejects,
  fees, slippage, and roll activity;
- gross return, each cost component, net return, equity, drawdown, and turnover;
- data, execution, reconciliation, and kill-rule alerts;
- operator acknowledgement and any safety flattening.

Reconcile positions, cash, fills, and mark-to-market independently each day.
Export a signed weekly snapshot.
Retain raw vendor responses, order records, and all log versions.

## 6. Risk limits and kill rules

These limits apply during paper testing and remain hard limits before capital:

- Gross exposure must not exceed 1.0 account notional.
- Each factor and underlying leg must remain within its frozen engine limit.
- The 10% volatility target cannot override leverage limits.
- Overlay drawdown of -10% forces zero strategy exposure.
- Account drawdown of -15% kills the program.
- A daily net loss of -3% or a single mark-to-market loss of -5% forces a
  flatten and review.
- Any stale, missing, non-finite, unbounded, or contradictory input forces a
  flatten.
- Any look-ahead, return-basis, sign, short-stop, or position-reconciliation
  defect kills the release and invalidates the affected period.
- Aggregate slippage above 25 bps per side for five sessions, or fill rate
  below 80% for five sessions, pauses the test for execution review.
- A market gap remains a breach even when no order could have prevented it.

After a kill, resume only under a new release with a written root-cause review.
Do not restart a changed release.

## 7. Acceptance gates

The test is valid only when the manifest, append-only logs, raw archive,
reconciliation, and incident trail are complete.

### Operational gate: 20 completed sessions

Require all of the following:

- At least 95% of required inputs arrived on time.
- Every signal reproduces from the stored inputs.
- Every position, fill, fee, and cash balance reconciles.
- No code, parameter, universe, or discretionary signal change occurred.

A failure pauses the test and requires a new release or written remediation.

### Performance gate: at least 300 completed sessions and 18 calendar months

Use net returns after observed fees, slippage, and roll costs.
Require every condition:

- Positive total net return.
- Positive median rolling 63-session return.
- Annualized Sharpe at least 0.50.
- Annualized volatility no more than 12%.
- Maximum drawdown no worse than -15% and no account kill.
- Worst day no worse than -5%, with any exception documented as a correctly
  modeled bounded market gap and with risk controls firing.
- Realized average cost no more than 25 bps per side.
- Independent ledger recomputation has no material difference from the report.
- No single day or calendar year contributes more than 50% of total net profit
  without a written regime explanation.

This is a decision gate, not a statistical significance claim.
Three hundred sessions cannot prove a durable edge.

## 8. Evidence required before investment

Investment remains rejected until an independent reviewer receives:

1. Signed release manifest with all source, dependency, calendar, instrument,
   and data hashes.
2. Complete append-only daily log, raw response archive, order records, and
   weekly signed snapshots.
3. Independent recomputation of signals, positions, P&L, costs, equity, and
   drawdown from archived inputs.
4. Execution analysis by instrument and direction, including liquidity,
   slippage, rejects, partial fills, and rolls.
5. Monthly and quarterly returns, rolling Sharpe, drawdowns, exposure, turnover,
   factor and leg attribution, and top-day and top-year profit concentration.
6. Regime and stress analysis for calm, volatile, drawdown, and gap sessions,
   including return lost while the V2 overlay was reduced or off.
7. Incident register covering every stale-data event, alert, pause, flatten,
   limit breach, kill, and recovery decision.
8. A signed investment memo naming allocation cap, expected loss budget, kill
   authority, monitoring owner, and review date.

A pass supports only a small staged allocation with a fresh hard loss budget.
It does not authorize scaling from the historical Sharpe.

## SUPERSEDED (2026-09-22 audit)

This protocol and the machinery it describes are superseded and refused at
run time. It froze panel_v2.parquet (yfinance raw front-month, NOT
back-adjusted), whose roll gaps inflated the measured P&L by 40.2%, and it
assumed 5 bps/side against a measured real cost of 16.2-24.0 bps/side.
The quoted OOS Sharpe 0.86 is falsified.
Use `algoterminal-strategy-v2/research/forward_protocol_v3.md`.
Full record: `algoterminal-strategy-v2/findings/artifact_audit.md`.
