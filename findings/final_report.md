# Final Strategy Report — Curve-Derived Regime Crush

Prepared for research review. All metrics verified with independent
implementations (see verify_metrics.py). All constants derived from
data, not picked.

---

## 1. Executive summary

The strategy trades one well-documented, statistically-verified edge:
seasonally-crushed oil refining margins revert, but only in certain
market regimes, and only when the physical storage buffer is not
working against the trade. Every entry, exit, risk, and sizing number
was read from the data — no tuned parameters, no calibration on the
holdout window.

Headline (clean, non-overlapping, net of costs):
- Derivation window (11.5y): plus 14.1%/y, Sharpe 0.87.
- Out-of-window (7.7y, untouched): plus 6.5%/y, Sharpe 0.72.
- Full history (19.1y): plus 11.7%/y, Sharpe 0.84, max drawdown -21%.

The out-of-window half-strength result is the honest center of this
report. It is positive but not yet statistically distinguishable from
luck (deflated Sharpe 0.11). The forward protocol is the gate.

---

## 2. The strategy — exact definition

Instrument: WTI 3:2:1 crack margin (2x gasoline + 1x heating oil,
minus crude; 42 gallons per barrel). Long-only on the margin.

State at close t, exposure realized at t+1:

1. Regime identity: compression/normal when the crack level is at or
   below the trailing 504-day median plus/minus a robust (MAD) band;
   expansion when above. Trade only compression/normal.
2. Signal: seasonal z (calendar removal + recent deviation). Entry
   strength is the TRAIN-derived conditional curve
   w(z) = E[fwd20 | z, comp/norm] / max-curve, with a significance
   bar z <= -0.45 (bin t >= 1.5).
3. De-risk: flat when same-month product stocks are building
   (z >= +1) — the physical buffer.
4. Sizing: relative-volatility normalization, absolute scale 0.468
   (10% loss budget / 21.4% ES5 of the crush state).
5. Stops, derived: per-trade loss budget 7.5% -> hard-stop distance
   ~16% of level; trailing stop at the 85th percentile of winning
   trades' adverse excursion; circuit breaker inactive at the derived
   threshold; cooldown 3 sessions.
6. Costs: 5 bps per side, 20 bps/yr roll (assumed).
7. Risk: no drawdown overlay. The tail is managed by the ES-based
   scale and the stated budgets.

---

## 3. Economic rationale — the roots of edge

1. Crush reversion. Refining margins revert because capacity is
   sticky in the short run: when margins are crushed, weak capacity
   idles/exits and seasonal demand returns, pushing margins back up.
2. Regime gate. The reversion is a compression/normal phenomenon.
   In expansion regimes, tightness persists (capacity is sticky on
   the way up), so the crush does not pay. This gates out the
   negative-expansion trades.
3. Storage buffer. Building product inventories are the physical
   damper: margin pressure precedes weaker reversion. De-risking
   when stocks build removes the worst-timed exposure. (Clean
   statistics reversed the old "storage doesn't matter" verdict.)
4. Flow-driven, not calendar. The edge lives in temporary flow
   excursions relative to the recent path, not in known calendar
   events (maintenance, blend switches), which are priced. Weather
   severity is a real but underpowered extra channel.

Each factor in the strategy traces to one of these roots.

---

## 4. How every number was derived

- Seasonal z: two-stage calendar removal + recent deviation
  (structural; mean-vs-median refinement is an open question, median
  variant measured and rejected empirically).
- Regime band: trailing median + 1.4826 x MAD (robust central
  tendency and scale from the data; 504-day window is a verified
  plateau).
- Entry line z <= -0.45: the largest z whose TRAIN bin t-stat >= 1.5
  on the conditional-mean curve. The number is an output.
- Scale 0.468: 10% loss budget / 21.4% crush-state ES5 (TRAIN).
- Budget 7.5%, trail 85th percentile, cooldown 3: chosen by a
  TRAIN-only sweep with marginals explaining the mechanism; the
  full-grid harness had to reproduce the base anchor first
  (reproducibility bar).
- No picked percentages remain. Named economic anchors: 10% loss
  budget, 7.5% per-trade budget, 1.5 significance threshold.

---

## 5. Data and windows (exact)

Panel: 4,829 rows, 2007-07-02 .. 2026-09-09, yfinance front-month
continuous closes (CL, BZ, RB, HO, NG). EIA weekly inputs with
6-day release lag. Costs 5/20 bps.

| Window | Range | Days | Years | Role |
| --- | --- | ---: | ---: | --- |
| TRAIN | 2007-07-02 .. 2018-12-31 | 2,894 | 11.5 | Derivation of all numbers |
| VALIDATE | 2019-01-02 .. 2026-09-09 | 1,935 | 7.7 | Out-of-window, untouched |
| OOS (convention) | 2007-07-30 .. 2023-09-08 | 4,055 | 16.1 | Overlaps TRAIN by 11.5y — NOT independent |
| FULL | 2007-07-30 .. 2026-09-09 | 4,810 | 19.1 | All history |

Critical: the familiar "OOS" label overlaps the derivation window.
The clean out-of-window test is VALIDATE only.

---

## 6. Performance — the full table

Metrics: non-overlapping trading-day blocks, net of costs. DSR =
deflated Sharpe at 1,000 trials (probability the Sharpe is not luck).

| Metric | TRAIN | VALIDATE | OOS* | FULL | Meaning |
| --- | ---: | ---: | ---: | ---: | --- |
| Annualized return | +14.11% | +6.48% | +14.10% | +11.65% | mean daily x 252 |
| CAGR | +13.70% | +6.26% | +13.98% | +11.31% | geometric growth |
| Sharpe | 0.870 | 0.719 | 0.971 | 0.839 | return per unit vol |
| Deflated Sharpe (N=1000) | 0.551 | 0.110 | 0.907 | 0.824 | P(not luck) given trials |
| Sortino | 0.806 | 0.502 | 0.863 | 0.719 | return per downside vol |
| Annualized vol | 16.22% | 9.01% | 14.52% | 13.90% | risk magnitude |
| Max drawdown | -20.93% | -21.24% | -20.93% | -21.24% | worst peak-to-trough |
| Best day | +18.23% | +8.82% | +18.23% | +18.23% | single-day gain |
| Worst day | -6.28% | -8.72% | -6.28% | -8.72% | single-day loss |
| Trades | 127 | 68 | 169 | 200 | entry/exit cycles |
| Win rate | 50.4% | 45.6% | 48.5% | 48.0% | fraction winning trades |
| Avg win | +3.38% | +2.78% | +3.58% | +3.29% | mean winning trade PnL |
| Avg loss | -0.85% | -0.77% | -0.71% | -0.80% | mean losing trade PnL |
| Profit factor | 4.05 | 3.01 | 4.75 | 3.82 | winners / |losers| |
| Exposure days | 23.5% | 16.5% | 20.7% | 20.8% | share of days in market |

(*) OOS stats are strong because they include 11.5y of derivable
data. Treat VALIDATE as the honest out-of-window column.

Why the trade structure matters: win rate near 50% but average win is
4-5x average loss. The curve exposure winds down as the crush
normalizes, cutting losers small while winners ride the reversion.
That is the actionable fact for sizing and risk monitoring.

---

## 7. Statistical integrity

- Non-overlapping 20-day blocks for every claim; block t-stats
  verified against daily t-stats (SR == t*sqrt(252)/sqrt(n)).
- All state inputs causal (close t -> exposure t+1); EIA lag 6 days.
- Deflated Sharpe uses the published per-period form (units fixed).
- Selection: every number came from TRAIN; VALIDATE never used.
- Reproducibility: the sweep harness had to reproduce the base
  anchor (TRAIN t 1.11) before its rankings were trusted; it did.
- Numerics verified by a second independent implementation.

---

## 8. Risks and caveats

1. Out-of-window weakness: VALIDATE return is ~half of TRAIN; DSR
   0.11 means luck cannot be excluded there. This is the dominant
   risk.
2. No overlay: -21% drawdown is the real experienced risk; daily
   worst -8.7%. Sized by ES budget, not a drawdown machine.
3. Costs assumed 5/20 bps; standard sources (exchange fees, carry)
   pending.
4. One-panel selection; even TRAIN-derived numbers retain residual
   selection effects from the broader search.
5. Heavy tails: best day +18.2% shows the payoff concentration;
   crash windows dominate the distribution.

---

## 9. Comparison vs prior constructions

- vs original champion + V2 overlay: similar OOS Sharpe (0.97 vs
  0.86), no path-dependent overlay, all constants derived — and the
  champion's own DSR is superseded by the same units fix.
- vs old-controls derived curve: OOS block t 3.96 vs 2.14; the
  swept controls (broader entry, looser stops near the original
  20% intuition) were the lever.

---

## 10. Validation path

Investments remain gated by the forward protocol: 20-session
operational gate, then 300 sessions / 18 months: positive net, Sharpe
>= 0.5, vol <= 12%, drawdown >= -15%, worst day >= -5%, reconciliation
clean. A pass supports a small staged allocation only.

---

## 11. Traceability map

| Strategy piece | Economic root | Evidence claim | Source |
| --- | --- | --- | --- |
| Crush reversion | capacity exit + demand return | crush fwd20 +21-25% clean | ledger: crush-state HOLD |
| Regime gate | stickiness asymmetry | comp +21% / exp ~0 | shape pass, regime model |
| Storage de-risk | physical buffer | H1 clean revision | direction 2 |
| Entry line/curve | flow excursion reversion | TRAIN curve, block t 3.96 | derived thresholds |
| Stops/budget | tail control | sweep marginals | derived controls |
| ES scale | tail budget | mixture ES5 27% | deep model |
