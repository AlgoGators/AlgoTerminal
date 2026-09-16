# Phase 3 findings — flow modeling with EIA (decision memo)

Date: this session. Harness: `phase3_harness.py`, `phase3_legs.py`.
Inputs: frozen panel + EIA weekly series (`engine/eia/raw_*.csv`,
fetched with the project API key, stored as v2 inputs).
Preregistration: `research/phase3_flow_model.md` (concrete rules
committed before measuring, f0fbb76).

## Verdict

No tilt is adoptable into the book as-is. One directional result
survives: utilization direction (T1) mildly conditions the crack legs
OOS (book ov Sharpe 0.86 to 0.91) with direction validated by the
controls, but the same interaction collapses IS (1.13 to -0.26).
That split makes T1 non-stationary in its book interaction and
untrustworthy as built. Product-draw tilt (T2) is anti-directional.
Cushing fullness (T3) never fires at book level. Combined (T4) is
dead.

## Results (overlay, OOS; A = frozen champion)

| Book | IS ov Sh | OOS ov Sh | OOS ov CAGR | OOS ov DD | OOS ov vol | worst |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A baseline | 1.13 | 0.86 | 5.62% | -10.74% | 6.6% | -2.85% |
| T1 utilization | -0.26 | 0.91 | 6.04% | -10.78% | 6.7% | -2.85% |
| T2 product draw | 0.65 | 0.64 | 3.73% | -13.68% | 6.0% | -2.85% |
| T3 Cushing fullness | 1.13 | 0.86 | 5.60% | -11.03% | 6.6% | -2.85% |
| T4 combined | 0.02 | 0.68 | 4.07% | -13.59% | 6.2% | -2.85% |

Raw book (OOS): A 0.64 / 9.46% / -29.80%; T1 0.64 / 9.89% / -27.55%.
Baseline A reproduces the champion within 2e-4.

## Leg-level attribution (the important part)

| Leg | Tilt | IS Sh | OOS Sh | OOS CAGR | OOS DD | OOS vol |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| crack_321 | A | 0.83 | 0.40 | 5.91% | -36.10% | 18.9% |
| crack_321 | T1 | 0.85 | 0.39 | 5.78% | -33.83% | 18.8% |
| cross | A | 0.75 | 0.59 | 18.32% | -67.71% | 40.7% |
| cross | T1 | 0.75 | 0.58 | 19.41% | -66.59% | 44.2% |
| crack_321 | T2 flip | 0.85 | 0.42 | 6.23% | -39.30% | 18.5% |
| cross | T2 flip | 0.73 | 0.59 | 20.07% | -67.82% | 44.1% |

The legs barely move. The book-level OOS gain to 0.91 is mostly
overlay-state interaction (a different equity path reaches different
overlay states), and the IS collapse is the same interaction in the
opposite direction. The headlined 0.91 is fragile.

Note: the corrected bzwti leg OOS Sharpe is -0.03 (the 0.25 in the
pre-wiring tables was stale). The tilt tests did not change it.

## Mechanism notes

- Utilization direction (T1): consistent with the flow thesis
  (capacity exit precedes reversion). Direction validated: real 0.909
  above flip 0.684 and above shuffled 0.761 (sd 0.092, ~1.6 sd).
  Magnitude small; overlay interaction unstable IS vs OOS. Kept only
  as a candidate for overlay-independent application.
- Product draw (T2): the hypothesized direction is wrong as
  constructed. The sign flip beats the real tilt at book level
  (0.868 vs 0.637), but legs barely change either way. Killed.
- Cushing fullness (T3): fullness >= 0.85 is too rare to act at book
  level. Book unchanged; control flat (0.860 vs 0.862, sd 0.010).
  Killed as a book feature. The Cushing story remains leg-level only
  (Round 6 H3 stands for bzwti direction).

## Controls (OOS overlaid book Sharpe)

| Tilt | Real | Flip | Shuffled mean | Shuffled sd |
| --- | ---: | ---: | ---: | ---: |
| T1 | 0.909 | 0.684 | 0.761 | 0.092 |
| T2 | 0.637 | 0.868 | 0.753 | 0.086 |
| T3 | 0.860 | 0.867 | 0.862 | 0.010 |
| T4 | 0.679 | 0.669 | 0.718 | 0.109 |

Only T1 separates from its controls in the preregistered direction.

## v2 driver map

- Crack legs: flow-driven, confirmed. Utilization direction is the
  only fundamental variable with the predicted sign and control
  support at book level. Magnitude small; interaction unstable.
- Demand proxy (product draws): not a driver in this construction.
  Null to anti-directional.
- Brent-WTI: physical story directionally real (Cushing) but too rare
  at book level. Keep Cushing as leg-level conditioning only.
- Everything else from v1 and this phase (weather gates, storage
  gates, product gates, tilts): no extractable book-level edge.

## Retained

1. T1 utilization tilt as a weak directional signal, for one
   specific retest: overlay keyed on the base book (so the tilt
   cannot change overlay states). This isolates signal from
   interaction.
2. The T2-flip observation (stock accumulation scaling up the long
   reversion) is worth one confirmatory leg-level run before final
   discard. It beat the control at book level.

## Next question

Does the utilization tilt's OOS gain survive when the overlay is keyed
on the base book? If yes, utilization tilt plus per-complex overlay
becomes the Phase 4 candidate. If no, the gain was overlay luck.

## Artifacts

- `phase3_harness.py` — tilt machinery, books, controls.
- `phase3_legs.py` — leg-level attribution.
- `results/phase3_results.csv`, `results/phase3_legs.csv`.
- `engine/eia/raw_*.csv` + `fetch_eia_phase3.py` — frozen EIA inputs.
