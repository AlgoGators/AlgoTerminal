> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Forward protocol v2 — B1h (paper test)

Candidate: B1h = regime-gated seasonal crush (comp/norm only, exit on
flip to expansion) with H1 product-stock de-risk, sized by the ES
gear (preregistered 10% / ES5 27.4%). No V2 ladder.

## Release manifest (before first order)

- Engine: engine/engine_v2x.py + factor_book.py (hashes), panel_v2
  parquet hash, inputs manifest hash.
- Parameter card: entry -0.75, exit -0.5, regime band median/MAD
  504d, H1 z threshold +1, vol target VT_F1, cap 1.0, gear 0.365,
  costs 5/20.
- Instruments: CL=F, BZ=F, RB=F, HO=F, NG=F.

## Daily log (append-only, one UTC row per session)

signal z, regime state, H1 state, position, gear, costs, gross/net
return, equity, kill alerts, operator notes. Every input timestamped
and hashed; late data quarantined, never backfilled.

## Kill rules

- Daily net loss -3% or single mark-to-market -5%: flatten and
  review.
- Account drawdown -15%: kill.
- Stale/missing/non-finite input: flat.
- Slippage > 25 bps/side or fill < 80% for 5 sessions: pause.
- No discretionary signal override; operator may flat for safety
  with a reason.

## Acceptance gates

20 sessions operational (inputs on time, signals reproduce,
reconciliation clean). Then 300 sessions / 18 months: positive net,
median 63d return positive, Sharpe >= 0.5, vol <= 12%, DD >= -15%,
worst day >= -5% (exceptions documented), realized cost <= 25
bps/side, independent ledger recomputation matches, no single year
> 50% of net profit without a regime explanation.

A pass supports a small staged allocation only. It does not scale
from the historical Sharpe.

## SUPERSEDED

This protocol froze the artifact-contaminated panel (CL=F/RB=F/HO=F)
and assumed costs (5/20 bps). The March contract-roll artifact alone
was 40.2% of the tested P&L. Use `forward_protocol_v3.md`.
See `findings/artifact_audit.md`.
