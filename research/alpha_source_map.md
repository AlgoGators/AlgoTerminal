> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Alpha source map — full coverage (v2)

Purpose: every alpha source named by the captain during the v1
breakdown gets a row, a test oracle, and a status. This is the mapping
document. Selection happens only after the map is covered.

Correction record: the earlier serial phase plan scoped only some of
these sources. This map supersedes that scoping. Phase memos stay as
records of their own tests.

Legend:
  status: UNTESTED / IN_PROGRESS / TESTED-keep / TESTED-kill-construction
          / CONSTRAINED (data) / ANSWERED

## The sources

| # | Source | Mechanism (captain's words) | Test oracle | Data needed | Cost | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Winter maintenance | Refineries do maintenance in winter to prep for summer, tightening supply | Ex-ante maintenance calendar (utilization seasonal dip) as a conditioning feature, vs realized utilization | EIA WPULEUS3 (have) | cheap | TESTED-kill (Tier1 absent, hypothesis_pass) |
| 2 | Cold-weather vehicle demand | Colder weather makes vehicles use more gas: longer warmup, thicker fluid, air drag, tire pressure loss | Gasoline crack forward returns conditioned on cold spells in major demand centers | NASA POWER temps (wired, keyless) | cheap | TESTED-keep phenomenon (Tier1 PRESENT: winter severity monotone, NYC; +11.4% top-bottom delta) |
| 3 | Fuel blends | Summer/winter blend transition moves cracks independent of demand | Blend-switch window dummies (spring, fall) interacting with seasonal deviation | calendar only | cheap | TESTED-keep (Tier1 PRESENT: de-risk window ~3 weeks around switch, vol 16% vs 9%) |
| 4 | Electrical load | Electricity demand shapes run rates and margins | Load or degree-day conditioning of crack legs | NYISO/PJM load or POWER-derived | medium | TESTED-kill (Tier1 absent, hypothesis_pass) |
| 5 | Other products | Distillate, jet, naphtha have their own seasonal peaks | Distillate winter peak on HO crack; jet/naphtha series | HO in panel; jet/naphtha need new series | medium | TESTED-kill-construction (batch2, HO winter/propane); jet/naphtha CONSTRAINED |
| 6 | Increasing demand/supply | The model must not assume flat demand and supply | Product supplied (retry other EIA routes) + stock-change demand proxy drift | EIA API | medium | TESTED-kill (Tier1 absent, hypothesis_pass); product supplied CONSTRAINED |
| 7 | Technological change | Efficiency, EV share, refinery closures drift the norm | Norm-drift diagnostics: same-month seasonal stats 2007-2015 vs 2016-2026 | panel only | cheap | ANSWERED (batch1): drift large; adaptive norm required |
| 8 | Asymmetry mechanism | Why does the left tail revert and the right tail not | Phase 1/1R answered: tightness persists; only regime-conditional short carries info. Next: tightness-ending events (utilization pin + stock rebuild) as the short entry | EIA + panel | medium | TESTED-keep phenomenon (Tier1 PRESENT STRONG 4.7sd: stretched in expansion -4.09% fwd20, in compression +3.52%; representation rebuild required) |
| 9 | Multiple crushes not captured | The cross factor holds one leg, leaves concurrent crushes untraded | Phase 2 basket: hold every crushed leg at product level | panel only | cheap | TESTED-kill-construction (batch1): product-level basket fails; multi-leg F2 variant open |
| 10 | Want both (all cracked legs) | Same as 9 | Same as 9 | panel only | cheap | TESTED-kill-construction (batch1, same as 9); variant open |
| 11 | Correlations recheck | The diversification math must be re-verified on honest returns | Re-export leg-level correlation matrix from v2 engine on corrected returns | panel only | cheap | ANSWERED (batch1): book is 2 bets; bzwti is the diversifier |
| 12 | Brent-WTI composition and efficiencies | Different grade composition, different processing efficiencies | Spread conditioned on storage plus refining-complex proxies; quality differentials via price-implied variables | EIA storage (have); quality series constrained | low-medium | TESTED-kill proxy (Tier1 proxy-poor: extremes mean-revert, not glut-monotone); composition CONSTRAINED |

## Workflow

1. Each row gets one minimal preregistered experiment in research/.
2. Experiments run in parallel batches where data allows.
3. Each result appends one row to results/ and updates findings/.
4. Batch order is by cost, not by champion benchmark. Selection only
   at the integration step.

## Batch plan (cost order)

- Batch 1 (cheap, panel + wired data): items 1, 2, 3, 7, 11, 9/10.
- Batch 2 (medium, data retry + targeted): items 4, 5, 6, 8, 12.
- Integration: combine survivors into the v2 construction.
