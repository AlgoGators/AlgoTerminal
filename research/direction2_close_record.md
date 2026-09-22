> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Direction 2 — close the record (preregistered)

Restate the QUEUED kills and the Round 8/9 claims with clean,
non-overlapping statistics. Methods fixed before measuring.

## A. Weather gate (Round 5 claim)

Hysteresis HDD-z gate on NG and crack_ho legs (cut position when NYC
HDD seasonal z <= -1.0, restore at >= -0.5). Compare gated vs
ungated leg returns with non-overlap 20d blocks, OOS window: mean,
t, 90% CI. Claim survives only if the gate improves or matches the
ungated mean.

## B. Storage gates (Round 6 claims)

- H1: de-risk crack_321 and cross when product-change same-month z
  >= +1 (multiplier 0). Clean blocks, OOS.
- H2: de-risk ng when natgas working gas z >= +1. Requires the
  natgas storage series; if unavailable, mark CONSTRAINED.

## C. Crash-put cost screen (Round 5 claim)

Cost argument, not a window-dependent backtest. Restate with clean
champion monthly (non-overlap) blocks: realized monthly vol, average
monthly return, and the modeled premium (trailing vol based, 1.0x
markup, -5% strike) as a fraction of the average positive month.
Verdict: uneconomic if premium >= the average clean monthly excess.

## D. Round 8/9 claims

- V4 reversal-speed and inflection: original runs failed robustness
  (V4 IS -0.46; inflection descriptively falsified). Add to ledger as
  FALSIFIED (original runs) with no clean rebuild planned.
- Joint crisis filter (crash5 + depth + crude20 crash): rebuild the
  STATE cleanly. JOINT(t) = seasonal z <= -1.25 and 5d z change
  >= 1.0 and CL 20d return <= -15%. Non-overlap blocks on OOS and
  FULL: E[fwd20 of crack_321] when JOINT on at t, with n, t, 90% CI.
  Compare to the undirected crush blocks.

## Deliverable

findings/direction2.md. Ledger rows for every claim touched.
