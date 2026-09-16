# Batch 2 findings — alpha source map, medium items

Date: this session. Harness: `batch2_harness.py`. Inputs: frozen panel,
EIA weekly (incl. propane WPRSTUS1), NASA POWER NYC T2M.
Preregistration: `research/batch2_alpha_map.md` (committed 587280a).

## Verdicts

| Source | Result | Status |
| --- | --- | --- |
| 4 electrical load | No edge via degree days | TESTED-kill-construction |
| 5 other products | HO winter/propane variants fail | TESTED-kill-construction (jet/naphtha constrained) |
| 6 increasing demand/supply | Retest fails the 2 sd bar | ANSWERED-partial (constrained on true series) |
| 8 tightness-ending short | Confirmations do not time the entry | ANSWERED (S3 regime filter stands) |
| 12 Brent-WTI crude-glut proxy | No edge | TESTED-kill-construction (composition constrained) |

## L4 — electrical load (HDD/CDD degree days)

- Real OOS ov 0.845 vs champion 0.862. IS ov -0.050.
- Inverted 0.685. Shuffled mean 0.821, sd 0.066. Real is about 0.4 sd
  above shuffled. No information.
- EIA weekly electricity codes returned 400 on probe; NYISO public
  CSVs 404. The degree-day proxy was the feasible route and it is
  dead. Killed as constructed.

## L5 — other products

Standalone HO crack leg OOS (net, raw):

| Variant | Sharpe | CAGR | MaxDD |
| --- | ---: | ---: | ---: |
| plain | -0.080 | -2.26% | -68.71% |
| winter tilt (Dec-Feb 1.25) | -0.067 | -2.16% | -68.75% |
| propane gauge tilt | -0.157 | -3.04% | -69.23% |

- Champion + winter-HO 4-leg book: OOS ov 0.554 vs champion 0.862.
- The distillate winter peak adds nothing to a leg that is dead OOS.
  The propane gauge makes it worse.
- Jet and naphtha series remain unavailable in free sources. Recorded
  as constrained. Item 5 closed on its testable halves.

## L6 — increasing demand/supply (confirmatory retest)

- Real OOS ov 0.867 (champion 0.862), IS ov 1.249 (champion 1.126).
- Control: shuffled mean 0.787, sd 0.072. Real is about 1.1 sd above
  shuffled.
- The preregistered bar was >= 2 sd without IS degradation. It cleared
  the IS check but not the sd bar.
- The result is directionally consistent with the Phase 3 flip finding
  (both show the building tilt above control) but small. Not
  adoptable. Weak retained for Phase 4 reanalysis, not as a trade.
- True weekly product supplied series unavailable on probed EIA routes
  (wpsd 400, wiup/stoc empty). Constrained.

## L8 — tightness-ending short entry

- Real OOS raw 0.073, ov -0.029. IS ov 0.693.
- Control: shuffled confirmations mean 0.034, sd 0.173. Real ov is
  within shuffled noise.
- The physical confirmations (utilization pin >= 90, stock rebuild)
  remove trades without improving timing. Phase 1R S3 (0.16 ov) is
  still the best short construction, and it is still too weak.
- Item 8 answered: the tightness-ending variant is killed. The regime
  filter remains the only usable element of the short side.

## L12 — Brent-WTI crude-glut conditioning

- Real OOS ov 0.855 vs champion 0.862. IS ov 1.126.
- Inverted 0.864. Shuffled mean 0.823, sd 0.067. Real is within noise.
- The crude-stock glut state (WCESTUS1 z) does not condition the
  Brent-WTI leg at these thresholds. The composition/quality series
  remain unavailable; recorded as constrained.

## Map completion

All 12 captain-named sources now have a status. Two weak signals are
retained (item 2 cold-weather relative tilt, item 3 blend-window
de-risk) plus three construction constraints (product supplied,
jet/naphtha, composition). The champion remains CORE3 EQ + V2 overlay
at OOS ov Sharpe 0.862.

## Notes for Phase 4

- Adaptive seasonal norm is required (item 7 drift is large).
- The building tilt and cold-weather relative tilt are the only
  direction-consistent conditional signals; both weak.
- Blend windows are de-risk periods, not add periods.
- Multi-leg F2 with depth weighting remains the one open basket
  variant.

## Artifacts

- `batch2_harness.py`
- `results/batch2_results.csv`
- `engine/eia/raw_WPRSTUS1.csv` (new frozen input)
- Statuses updated in `research/alpha_source_map.md`
