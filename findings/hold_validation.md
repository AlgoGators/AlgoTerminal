# Hold validation — cleaned statistics verdict

Date: this session. Harness: `hold_harness.py`. Prereg:
`research/hold_validation.md` (d375566). Non-overlapping 20-day
windows, causal states only (GMM dropped), rule card frozen before
the validation window was measured.

## Results

| Rule | Window | n | mean fwd20 | t | 90% CI | pos frac |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| L long crush | TRAIN | 35 | **+18.41%** | +3.81 | [+10.5, +26.4] | 69% |
| L long crush | VALIDATE | 15 | **+37.07%** | +1.28 | [-10.6, +84.8] | 73% |
| S short stretch | TRAIN | 34 | **-6.86%** | -1.58 | [-14.0, +0.3] | 38% |
| S short stretch | VALIDATE | 36 | **+2.60%** | +0.84 | [-2.5, +7.7] | 47% |
| L + cold | both | 3 / 1 | — | — | — | — |
| L + blend switch | both | 7 / 6 | +8.7% / +66.9% | — | — | 57% / 50% |

## Verdict per the frozen bar

The bar: same sign in both windows, 90% CI excluding zero in both,
yearly fraction supports the sign, n >= 20 in validation.

- L long crush: sign consistent (+18.4% train, +37.1% validate),
  train holds at 90% (t=3.81), validation n=15 and the CI includes
  zero because one 2020 window returned +229%. YEARLY: positive in 4
  of 5 validation years with entries. DIRECTIONAL HOLD; does not meet
  the full statistical bar on validation.
- S short stretch: FAILS. Sign flips on validation (+2.6% vs -6.9%)
  and yearly outcomes alternate every year (2019 -9.0, 2020 +11.3,
  2021 +4.7, 2022 +13.5, 2023 -13.0, ...). Not held.
- C cold tilt: UNMEASURABLE with non-overlap (n=3 / 1). No claim.
- B blend suppression: UNMEASURABLE (n=7 / 6) and the train direction
  was the opposite of the suppression expectation (+8.7%). No claim.

## The lessons

1. Overlap inflated the shape-pass cells. The earlier short stretch
   figure (-4.4% in the normal regime) does not survive cleaned,
   non-overlapping statistics. The short side is NOT confirmed.
2. The revived short build (ch26) loses its primary statistical
   support. It remains an idea, not a held result.
3. The long-crush edge is the only directional survivor. Its
   training evidence is solid (t=3.81, non-overlapping) and the
   validation direction agrees; the validation CI is limited by
   sample size and one extreme year.
4. Cold-tilt and blend-suppression are still untested at the
   statistical level; earlier cell numbers were overlap-inflated.

## What we can now say we know

- Non-overlapping, causal, out-of-window evidence: long crush in
  compression/normal has a positive forward mean in both windows,
  with solid train significance and an agreeing (but small) validate
  sample. Everything else is not held.

## Next

The definitive test remains the frozen forward protocol
(algoterminal-strategy-audit forward_test_protocol.md). The cleaned
claim to carry into it: the long-crush edge; short-stretch and the
conditional tilts are demoted to ideas needing new data, not held
edges.

## Artifacts

- `hold_harness.py`, `results/hold_validation.csv`
- Corrections appended to regime docs.
