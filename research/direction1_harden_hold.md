> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Direction 1 — harden the hold (preregistered)

Four sub-items that harden the one HOLD claim (v1 champion positive
edge OOS/FULL, clean blocks). All methods fixed before measuring.

## 1a. Deflated Sharpe

Selection inflation quantified. The champion's OOS Sharpe was
selected from many evaluations. Compute the deflated Sharpe
(Bailey-Lopez de Prado 2014):

- SR0 = sqrt(V[SR]) * ((1-g)*Phi^-1(1 - 1/N) + g*Phi^-1(1 - 1/(N e)))
  with g = 0.5772 (Euler-Mascheroni).
- V[SR] = (1 - skew*sr + (kurt-1)/4 sr^2) / (T-1).
- DSR = Phi[(sr - SR0) sqrt(T-1) / sqrt(1 - skew*sr +
  (kurt-1)/4 sr^2)].

Inputs: OOS daily raw and overlay returns (skew, kurtosis, T).
Trials N: 10, 100, 1000 (sensitivity). Report DSR (= probability
that the observed Sharpe is not luck from N trials).

## 1b. Cost robustness of the HOLD claim

Rebuild the champion EQ book net returns with cost sets:
(5,20) baseline, (10,20), (20,40), (10,40) bps trade/roll.
Rerun non-overlapping 20-day block stats (OOS and FULL): mean/block,
annualized, t, 90% CI. The HOLD claim survives if the OOS and FULL
CIs exclude zero at (10,20) and (20,40).

## 1c. Overlay cost ledger (clean blocks)

On OOS non-overlap blocks, raw vs overlay:
- total cumulative raw vs overlay (forgone total),
- top-10 raw blocks: how many the overlay captured positive vs sat
  out (block sum == 0), and the sum forgone on them,
- the flat era (2014-2016): raw vs overlay block sums,
- forgone = sum(raw_block - ov_block) over blocks with raw_block
  > 0.

## 1d. EIA settlement measurement upgrade

Probe EIA weekly NYMEX settlement/spot price series for
CL/RB/HO/NG/BZ. If a series spans 2007-2026, fetch it into
engine/eia/. Compare weekly settlement closes vs yfinance weekly
closes: correlation and mean absolute relative difference. Report
measurement risk. If no settlement series is available, use the
closest EIA spot series and state the proxy honestly.

## Deliverable

findings/direction1.md, ledger updates.
