# Model book — from-scratch strategy from mechanism findings

Date: this session. Harness: `model_book_harness.py`. Prereg:
`research/model_book.md` (e1d19cd). No overlay. Clean non-overlap
20d blocks. Factor rule: drop any factor whose OOS CI includes zero.

## Per-factor clean blocks (OOS/FULL)

| Factor | OOS ann (t) | OOS CI | FULL ann (t) | Neg% | Verdict |
| --- | ---: | --- | ---: | ---: | --- |
| F1 regime-gated crush (crack_321) | +8.92% (1.73) | [+0.03, +1.38] | +8.98% (1.98) | 17% | keep |
| F2 multi-leg breadth (gas, HO) | +3.14% (0.57) | crosses 0 | +4.55% (0.86) | 29% | DROP |
| F3 Brent-WTI reversion | -0.47% (-0.14) | crosses 0 | +0.78% (0.26) | 40% | DROP |

## Books (no overlay)

| Book | OOS ann (t) | CI | FULL ann (t) | neg% | worst | raw Sh | DD | CAGR |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 (F1+F3) | +4.22% (1.29) | incl 0 | +4.88% (1.70) | 41% | -16.2% | 0.358 | -31.2% | 3.6% |
| B2 (+F2) | +3.86% (1.15) | incl 0 | +4.77% (1.58) | 43% | -11.9% | 0.314 | -39.3% | 3.2% |
| B3 (+H1 on all) | +8.52% (2.37) | excl 0 | +8.87% (2.78) | 40% | -10.8% | 0.614 | -31.5% | 7.9% |
| **B1h = F1 + H1 (compliant)** | **+15.55% (2.93)** | **[+0.54,+1.93]** | **+15.46% (3.33)** | **16%** | -18.9% | **0.754** | -28.5% | **14.5%** |
| B1h3 (adds F3) | +7.54% (2.27) | excl 0 | +8.12% (2.82) | 39% | -16.2% | 0.607 | -28.2% | 7.0% |
| Champ_raw (reference) | +10.29% (2.41) | excl 0 | +10.95% (2.83) | 40% | -14.6% | 0.635 | -29.8% | 9.5% |

## The winner

B1h: buy the seasonal 3:2:1 crush only in compression/normal regimes,
exit immediately when the regime flips to expansion, and go flat
(de-risk) whenever same-month product stocks are building (z >= 1).
No drawdown ladder. Sized by the vol target with the 1.0 cap.

- Holds cleanly: OOS t=2.93, FULL t=3.33; CIs exclude zero.
- Neg blocks 16% vs champion raw 40%. Worst block -18.9%.
- OOS raw Sharpe 0.754 vs champion raw 0.635; CAGR 14.5% vs 9.5%;
  max DD -28.5% vs -29.8%.
- Single-sleeve: the breadth leg (F2) and the Brent-WTI diversifier
  (F3) were tested and DROPPED by the per-factor rule; including
  either lowers the book. The "two-bet book" idea is not confirmed
  in this architecture.

## Why this is a new construction, not a rerun

- Built from mechanisms: crush reversion gated by regime (capacity
  exit + demand return), storage buffer as physical de-risk (H1,
  clean-revised), sizing from vol target with the mixture-ES
  context (crush state mean +11.7%, ES5 -27%).
- No V2 overlay by design: the ladder is the recurring constraint
  on clean improvements.
- The champion is a reference for honesty, not a component.

## Caveats

- No overlay means the raw -28.5% drawdown is the real tail; the
  mixture ES says crush-state 20d ES5 ~ -27%. Real-money sizing
  still needs a loss budget decision.
- Selection caveat persists (this construction was chosen after
  examining data), though every constant is either structural
  (0.75/-0.5 z thresholds from v1 plateau, regime band from
  median/MAD, H1 z>=1 from clean revision) or read from shapes.
- The definitive test remains the forward protocol; B1h is the
  candidate to carry into it.

## Artifacts

- `model_book_harness.py`, `results/model_book.csv`
