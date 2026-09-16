# Multi-leg F2 Tier 2 — findings

Date: this session. Harness: `multileg_harness.py`. Prereg:
`research/multileg_f2_tier2.md` (a9313d1).

## Verdict

Not adoptable as built. The multi-leg + cap construction genuinely
improves the cross factor at the raw level, including drawdown for
V2. The depth multiplier adds nothing once the cap is in place. The
book-level overlay kills the whole construction: the fatter cross
drawdowns trip the overlay more often and collapse overlaid Sharpe.

## Cross-leg results (OOS raw, net 5bps/20roll)

| Variant | Sharpe | CAGR | MaxDD | Vol |
| --- | ---: | ---: | ---: | ---: |
| v1 single-most-crushed | 0.589 | 18.32% | -67.71% | 40.7% |
| V0 flat multi, cap 1.0 | 0.700 | 22.62% | -67.81% | 40.6% |
| V1 depth 0.5/2.0, cap 1.0 | 0.686 | 23.40% | -72.32% | 45.5% |
| V2 depth 0.5/2.0, cap 0.8 | **0.735** | 23.64% | **-64.75%** | 39.1% |
| V3 depth 0.25/1.5, cap 1.0 | 0.687 | 22.88% | -71.09% | 43.6% |

The multi-leg structure (V0) improves Sharpe 0.589 -> 0.700 with the
same drawdown. Adding the tighter cap (V2) improves further, to
0.735, and drawdown improves against v1. The depth multiplier alone
(V1 vs V0) does not beat flat multi-leg at the leg level.

## Book results (crack_321 + cross + bzwti, equal weight)

| Book | OOS raw Sh | OOS raw DD | OOS ov Sh | OOS ov DD | IS ov Sh |
| --- | ---: | ---: | ---: | ---: | ---: |
| Champion (v1 cross) | 0.635 | -29.79% | **0.862** | -10.73% | 1.126 |
| V0 | 0.630 | -37.28% | 0.614 | -11.21% | 1.222 |
| V1 | 0.629 | -41.80% | 0.579 | -12.51% | 1.622 |
| V2 | 0.656 | -37.50% | 0.582 | -13.52% | 1.690 |
| V3 | 0.625 | -41.01% | 0.590 | -11.88% | 1.616 |

Raw book: V2 slightly beats the champion (0.656 vs 0.635). Overlaid:
every multi-leg variant collapses (0.58-0.61 vs 0.862) with worse
drawdown. The overlay is the failed level for the book.

## Control (V1 depth shuffled, 20 seeds)

Real V1 book raw OOS 0.629. Shuffled mean 0.647, sd 0.016. Real is
BELOW the shuffled mean. The depth ordering itself adds no value once
exposure is capped; the gains come from multi-leg breadth plus the
notional cap, not from depth sizing.

## Mechanism

- Multi-leg breadth is real: holding simultaneous crushes raises raw
  factor Sharpe (0.589 -> 0.700+).
- The cap converts breadth into risk control: V2's tighter cap
  lowers both drawdown and vol while keeping the higher mean.
- Depth sizing is redundant after the cap: the deep-crush edge is
  already captured by being long, and the cap trims the tails that
  depth would enlarge.
- The overlay interaction is the book killer: a fatter cross sleeve
  falls into the -6% / -10% ladder more often, so the overlay sits
  flat in more of the good periods.

## Adoption rule result

Fails: overlaid Sharpe worsens (0.862 -> ~0.58-0.61), book raw
drawdown worsens (-29.8% -> -37%+), and the depth control is not
cleared.

## Retained

The V2 leg-level construction (multi-leg all-crushed, cap 0.8,
depth multiplier kept but proven redundant) is a genuinely stronger
raw cross factor: Sharpe 0.735, MaxDD -64.75% versus 0.589 /
-67.71% for v1. It is a Phase 4 candidate for the model-first build,
where the overlay is replaced by model-based risk (B_t/R_t state
sleeves) instead of a book-wide ladder.

## Chain status

ch30: evidence-confirmed (phenomenon) -> tested at book; retained
leg-level V2. Status: tested-kill-at-book, retained-leg-level.

## Artifacts

- `multileg_harness.py`
- `results/multileg_f2_tier2.csv`
