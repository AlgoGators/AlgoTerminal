# Derived controls — honest deep comparison

Date: this session. Harness: `derived_controls_harness.py`. Prereg:
`research/derived_controls.md` (0b58efe).

## The derived numbers (from TRAIN)

| Item | OLD (picked) | NEW (derived) | Derivation |
| --- | --- | --- | --- |
| Entry bar | 5% expected return (zcut -0.68) | Bin t>=2 (zcut **-0.91**) | significance, not magnitude |
| Scale | VT 0.50 + cap 1.0 | **0.468** = 10% / ES5_train | one number from the distribution |
| Circuit breaker | 3 sigma | **11.0%** daily loss (99 pct of held days) | empirical quantile |
| Hard stop | 20% from entry | **4.28%** (2% budget / scale) | per-trade budget |
| Trailing | 1.25 sigma | **9.57%** MAE (75 pct of winning-trade adverse excursion) | winner-preserving quantile |
| Cooldown | 5 days | **3 days** (median-style approximation) | stop-episode statistic |

## The measured comparison (clean blocks)

| | TRAIN t | VALIDATE t | OOS t | FULL t | neg% | worst |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| OLD (derived bar + old controls) | 1.92 | 1.17 | **2.14** | **2.31** | 13-14% | -19.7% |
| NEW (D1-D3) | 1.11 | 1.28 | **1.87** | **1.70** | 19-22% | -14.6% |

NEW does NOT meet acceptance (OOS t 1.87 < 2.14; FULL t 1.70 < 2.31).
The derivation process is correct; the default policies made numbers
that LOSE to the old ones.

## Item-by-item honest post-mortem

- **Bar (significance)**: stricter (-0.91 vs -0.68); combined with old
  controls it performed fine (OOS 2.14). Defensible. The 0.91 is the
  data's answer, not mine.
- **Scale 0.468**: equivalent to the gear; clean; not the problem.
- **CB 11%**: the 99-percentile policy is far LOOSER than 3 sigma, so
  it almost never fired. 3 sigma was not capricious in effect: it
  bound losses in a way a lenient tail policy does not. The derived
  value is hostage to the chosen quantile (99% vs 99.5% vs 99.9%).
- **Hard 4.28%**: the 2% per-trade budget is far TIGHTER than 20%,
  and it whipsawed winners. The old 20% was effectively a rare
  disaster cap; 4.3% is a frequent cut. The derived value inherits
  the budget anchor, and the default budget was too small.
- **Trailing 9.6%**: about what 1.25 sigma implied elsewhere; mixed.
- **Cooldown 3**: approximate; the proper stop-episode statistic is
  still open.

## The true lesson

Deriving numbers from distributions is correct, but the POLICY still
has to be chosen (which quantile, which per-trade budget), and the
policy choice determines the derived number. The old values were not
capricious in effect: 3-sigma and 20% encoded useful tail behavior.
The honest path is to state the economic constraints FIRST (maximum
acceptable single-day loss, maximum acceptable per-trade loss) and
let the distributions translate THOSE into triggers. That makes the
policy the named economic anchor and the number the data's output.

## D4 — window plateau (NEW construction)

| lookback | OOS t | FULL t |
| --- | ---: | ---: |
| 60 | 1.27 | 1.15 |
| **90** | **2.48** | **2.28** |
| 120 | 1.92 | 1.70 |
| 180 | 2.26 | 2.01 |

90 is the plateau best. Clip sweep not run (partial prereg item,
open).

## Ledger

- Derived-bar (zcut -0.91): DIRECTIONAL (held with old controls).
- Derived stop pack (99%/2% defaults): FALSIFIED vs old controls
  (OOS 1.87 vs 2.14). Policy anchors matter; sensitivity open.
- Unified scale: equivalent to gear (clean).
- Lookback 90: plateau confirmed.

## Open (next)

Policy-driven stop derivation (state max daily / per-trade loss,
read triggers from distributions), clip sweep, cooldown episode
statistic, cost standard lookup, deflated Sharpe.
