> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Final strategy — statistically-rooted integration (preregistered)

Build the final construction only from HOLD/DIRECTIONAL ledger claims.
Acceptance is against the champion on clean non-overlap blocks.

## Supported inputs (from the ledger)

1. Champion EQ book OOS/FULL edge HOLDS (clean blocks t 2.4-3.3).
2. Long-crush state on crack_321: fwd20 +21.4%/+25.4% non-overlap
   (t 2.57-2.65); compression/normal regimes +21.1%/+10.2%; HMM
   comp+norm +23.7% (t 2.12). Deep-crush in EXPANSION is negative
   (shape pass) -> the regime gate is supported.
3. H1 product-stock de-risk on crack_321 REVISED to help at the leg
   level (gated +10.15% t 2.08 vs raw CI crossing zero). No book
   test yet -> this integration test is the first.
4. Depth sizing, cold tilt, blend de-risk, multi-leg F2: not adopted
   (no clean book support at this power).
5. V2 overlay HOLDS at the book level (cuts negative blocks 40->21%).

## Construction

Sleeves (all causal):
- Crack sleeve: seasonal-z state machine (enter z <= -0.75, exit
  z >= -0.5) gated by regime R2 (trailing 504d median/MAD):
  entries only when R2 in {comp, norm}; immediate exit when R2 flips
  to exp. v1 vol scale VT_F1, per-leg risk (trailing True), 1.0 cap.
- Cross sleeve: champion cross_sectional leg unchanged.
- Brent-WTI sleeve: champion bzwti leg unchanged.
- H1 variant: crack position multiplied by 0 when product-change
  same-month z >= +1 at t-1 (de-risk), else 1.

Book: equal weight (1/3 each), costs 5/20 (10/20 sensitivity), V2
overlay.

## Variants

- V_Champ: champion (reproduce reference).
- V3: champion + H1 de-risk on crack (isolates H1).
- V1: champion + regime gate on crack (isolates regime gate).
- V2: champion + regime gate + H1 (the integrated candidate).

## Acceptance (clean 20d blocks, OOS and FULL)

- Candidate's OOS and FULL raw mean blocks: CI excludes zero.
- Candidate's OOS mean >= champion OOS mean, and overlaid DD no worse
  than champion's OOS ov DD by more than 1 point (path-dependent
  flagged).
- Negative-block fraction no worse for the overlay.
- If V2 fails, the champion remains; the integration is recorded as
  rejected with the failed level.

## Deliverable

findings/final_strategy.md. Ledger rows.
