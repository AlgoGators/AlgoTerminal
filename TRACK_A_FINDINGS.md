# Track A — Incremental CORE3 Upgrade (Round 10A)

Date: 2026-09-10
Worktree: `strategy-dev` branch. Panel `/tmp/panel_adj_2007_2026.parquet` 4829 rows 2007-07-02 -> 2026-09-09.
Engine: `book_oos_v8_A.py` imports `factor_book.py` (fb) + `book_oos_v5.py` (b5) + `book_oos_v4.py` (b4).
Book: CORE3 = crack_321 + cross_sectional + bzwti, EQ weights, NOCAP default, 5bps/20roll, warmup 90.
Windows: IS 2023-09-08 -> 2026-09-09, OOS 2007-07-30 -> 2023-09-08.
Costs causal. All signals decided at close t-1 for day t.

Grid: cap (NOCAP/CAP8/CAP5) x Cushing (OFF/S05 min 0.5 / S07 min 0.7) x joint (V2/ J_FULL / J_P3 / J_P5 / J_P10) x overlay (BOOK / PER). 90 rows in `book_oos_v8_A_results.csv`.
Thresholds pre-registered round numbers: JOINT = crash5>=1.0 & depth<=-1.25 & crude20<=-15%. Cushing scale = 1 - (1-min)*clip((z-0)/1.5,0,1).
Probationary JOINT: joint at close t-1 forces FULL for N days (timer), retrigger extends.

## 1. Behavior — which regimes did it win, which did it bleed

- Joint is rare crisis state. OOS 29 days (0.73% of OOS), IS 0 days. IS intact for all variants.
- V2 champion (BOOK NOCAP V2 OFF): OOS Sharpe 0.95 DD -11.1% vol 6.6% CAGR 6.27%. IS 1.13 DD -10.2%.
- Probationary variants (BOOK NOCAP):
  - J_P5: OOS 0.957 DD -14.7% vol 9.06% CAGR 8.63%. IS 1.13 DD -10.2% (unchanged).
  - J_P10: OOS 0.956 DD -14.9% vol 9.12% CAGR 8.69%.
  - J_FULL (infinite): OOS 0.946 DD -14.2% vol 8.89% CAGR 8.37%.
  - J_P3: OOS 0.944 DD -15.7% vol 8.99% CAGR 8.44%.
  All probationary gain +0.006-0.007 Sharpe over V2 for +3.1 to +4.6% DD cost.

Yearly OOS (raw -> V2 -> P5 -> FULL):
- 2013 bleed: raw -23.1% -> V2 -6.2% -> P5 -6.2% -> FULL -6.2% (joint never fires in 2013 grind).
- 2019 bleed: raw -15.3% -> V2 -0.9% -> P5 -2.2% -> FULL -3.4% (P5 adds -1.3% vs V2).
- 2020 windfall: raw +32.8% -> V2 +4.2% -> P5 +41.0% -> FULL +39.6% (P5 captures full windfall plus timer bleed, even exceeds raw due to avoiding Jan-Feb losses).
- 2014 flat recovery: raw +12.2% -> V2 0.0% -> P5 -3.2% -> FULL -1.6% (P5 re-exposes to post-crisis grind).
- Other years flat: 2014, 2015, 2018 see small P5 bleed -0.7% to -3.2% vs V2 0.0%.
- The DD slip comes from re-exposure duration, not the joint days themselves (2014 bleed days are not joint, but timer keeps scale 1 into grind).

Worst days OOS:
- V2 worst: -2.85% (single gap). All probationary worst -3.02% (same gap, slightly larger due to being ON).
- Raw worst: -12.1% (2019-09-03). Overlay cuts tail by vol gear, not by joint.

Cushing sizing (BOOK):
- NOCAP V2 OFF 0.95/-11.1% vs NOCAP S05 V2 0.89/-11.2% vs S07 0.86/-12.1%. Cushing hurts Sharpe -0.06, lifts DD slightly.
- NOCAP J_P5 OFF 0.957 vs S05 0.912 vs S07 not better. Scaling dims bzwti when Cushing high; bzwti is small 1/3 weight, so book impact diluted and directionally wrong for total book.

Gap caps (BOOK V2):
- NOCAP 0.95/-11.1% | CAP8 0.61/-14.0% | CAP5 0.52/-15.9%. Cap hurts Sharpe 0.34 and worsens DD under V2.
- With J_FULL: CAP5 0.88/-13.6% still below NOCAP V2. Cap + joint recovers some Sharpe but never beats NOCAP V2, and IS 1.66 vs 1.13 shows IS overfit (CAP5 clips in low-vol IS tape, looks good IS, fails OOS).

Per-complex overlay (vs BOOK):
- NOCAP V2 PER 0.78/-12.5% vs BOOK 0.95/-11.1% (-0.17 Sharpe, -1.4% DD).
- NOCAP J_P5 PER 0.88/-14.6% vs BOOK 0.957/-14.7% (-0.07). Per-complex de-risks each complex on its own DD, so it stays OFF more often (two DD ladders), misses recovery, higher vol 9.5% vs 9.0%, lower Sharpe.
- CAP cases: per-complex occasionally beats BOOK by 0.08 (CAP8 V2 PER 0.69 vs 0.61) but still below NOCAP BOOK.

Bucket descriptive (OOS held days, causal):
- JOINT (1.0/-1.25/-15%): n=29 mean +0.89% vs grind +0.037% (book held days). Same as Round 9 (n=32 with NOCAP depth, now 29 with updated depth after warmup fix). Grind years 2013/2019 median crash5 0.00/-0.11, joint fires 0 times there — discriminative.
- Fast-deep alone (>=1.0/-1.25 without crude): mean +0.18% vs +0.037%.
- Adding crude <=-15% lifts +0.18% -> +0.89% — crude filters grind fast-deeps.

## 2. Mechanism — why did it happen

- Windfall and bleed share the same LEVEL (deep <=-1.25). Speed alone (crash5) separates partially, but crude crash selects the payoff-relevant deep events: crisis entries have crude crashing, grind deep events do not. That is the driver map from Round 9.
- Probationary is the duration hypothesis: does the DD cost (-2% in Round 9 full joint) come from the joint days themselves or from staying FULL after the joint window into the grind? Result: duration matters. P5 vs FULL vs V2 shows P5 captures same 2020 windfall as FULL (+41.0% vs +39.6% vs raw +32.8%) but pays with extra exposure in 2014-2015 grind (-3.2% vs -1.6% vs 0.0%). The timer extends exposure into non-crisis days, so the cost is post-crisis drift, not the crisis day itself.
- Cushing z scaling assumes bzwti edge is physical (tank tops). Book-level, bzwti is 1/3 weight and its OOS improvement (0.25->0.31 standalone) is too small to move the book; scaling down bzwti when Cushing high removes the few bzwti pay days that coincide with joint crises, so book Sharpe falls.
- Gap caps hurt because the honest engine already runs at ~6.6% vol with vol gear; capping at 5% of book for a 3-sigma move clips the same windfall legs that drive the edge (cross_sectional 40% vol, bzwti 16%). The cap binds on windy days that later mean-revert.
- Per-complex overlay hurts because diversification is weak (crack_321 vs cross 0.34, cross vs bzwti -0.25). Two DD ladders mean more time OFF, less capture of the joint recovery, but no DD gain (both complexes bleed together in compression years).

## 3. Retained signal — what is still usable

- JOINT as rare crisis flag remains the strongest single-state mean (+0.89% vs +0.037%). Its IS safety (n=0) is confirmed again. The timer variant does not improve it, but the flag itself is information.
- Probationary insight: the -2% DD cost is duration, not entry. A shorter probation (3 days) leaks less into grind (-3.2% vs -1.6% nuance) but still captures windfall (P3 2020 +? similar). The best Sharpe among probationaries is P5 0.957, but the difference from FULL is noise (0.011). The retained idea is to force FULL only on the joint day itself, not N days after — a single-day override would keep the flag without duration bleed. Not tested.
- Cushing direction for bzwti standalone is still correct (0.25->0.31 via z gate in Round 6). Book-level dilution is the problem, not the factor.
- Per-complex granularity is not useful for DD reduction with this correlation matrix. Retained: book-level overlay dominates.

## 4. Control — what did the negative control prove

- Shuffled JOINT labels (30 draws, prob5 BOOK): mean Sharpe 0.833 sd 0.083 vs real P5 0.957 vs V2 0.95 vs raw 0.71. Real P5 is 1.5 sd above shuffled mean, V2 is 1.4 sd above. So JOINT carries ~0.12 Sharpe of information over shuffled rarity base rate, but V2 already captures most (1.4 sd). Probationary adds little over V2 (0.1 sd). This proves the construction (joint timer) has some information, but not much over V2.
- Shuffled V2 control from prior rounds: V2 1.4 sd above shuffled raw, joint 2.8 sd above in Round 9's off-by-one version; with causal fix gap shrinks. The new diagnostic shows probationary vs V2 is within noise.
- Cushing shuffled not needed; its book impact is negative even vs real, so no information at book level.
- Gap caps negative control would show no benefit (not run, but CAP5 V2 0.52 vs shuffled gap would be lower).

## 5. Scope — which exact hypothesis failed, which neighbors stand

Falsified constructions:
- Probationary JOINT (N=3,5,10) as a Sharpe/DD improvement over V2. Falsified at utility level: +0.007 Sharpe for -3.6% DD is not a win under the lens (MaxDD is hard). All N within 0.013 Sharpe, no optimum.
- Cushing continuous scaling (min 0.5/0.7 over z 0-1.5) at book level. Falsified: hurts Sharpe -0.06 and DD.
- Gap caps CAP8/CAP5 at book level under V2. Falsified: Sharpe -0.34 to -0.43, DD -2.9 to -4.8% worse.
- Per-complex DD overlay. Falsified: Sharpe -0.17 vs BOOK V2, no DD gain.

Not falsified (neighbors):
- Single-day JOINT override (N=1, force FULL only on joint day, no timer). Not tested — would capture windfall without duration bleed. This is the sharp next test.
- Cushing for bzwti standalone sizing (not book) — kept as factor-level, not adopted at book.
- Gap caps at leg level with vol-targeted sizing (lower MAX_LEV) rather than book overlay — not tested.
- Per-complex overlay with Brent legs (if they are added back) — not tested here because CORE3 only.
- Joint with tighter crude window (10d) or realized crude vol — not tested.

## 6. Variants — what was not tested

- JOINT N=1 (single day) or N=2.
- JOINT for re-cock only (0.5) rather than FULL — would keep part of windfall with half DD slip.
- Cushing utilization ratio (stocks / capacity proxy 76mm) vs z — we used z only.
- Cushing scaling applied only to bzwti position before book weighting vs scaling net return (we scaled net; equivalent but turnover nuance untested).
- Gap cap per-leg vs book-level; lower VT_F2 (0.35) with NOCAP vs CAP.
- Per-complex with different complex splits (three complexes vs two).
- 10-day crude crash vs 20-day.

## 7. Next question

Does a single-day JOINT override (force FULL only on the joint day, zero timer) keep the 2020 windfall (+21.1% on 04-20) while avoiding the post-crisis grind bleed that makes P5 bleed 2014-2015? That tests whether duration is the entire cost.

## Numbers second — payoff profile of retained vs rejected

Payoff concentration:
- Raw OOS total +186.7% over 16y: top5 days +60.2% (32.3% of total), top5 years (2008,2020,2021,2022,2023) 77% of total.
- V2: total +99.1%, top5 +29.8% (30.1%), top5 years similar but compressed (2022 29.3%, 2021 23.4%, 2008 19.9%).
- P5: total +131.7%, top5 +49.6% (37.6%), more concentrated than V2 (convexity up, as intended).
- Sharpe is thin average over bimodal: rolling 3y Sharpe swings -0.17 to +2.4.

Stress correlation:
- Strategy vs energy vol (trailing 20d): raw corr ~ -0.05 (uncorrelated), V2 corr ~0.10 (slightly positive after de-risk).
- Drawdown phases: V2 is OFF 2014-2016 and 2018-2019 bleed years, flat. P5 is ON during 2014 probation windows, correlates with crude stress.

Participation:
- V2 sat out 2020-04-20 (+21.1% raw) -> 0%, P5 captured 100% (+21.1%), FULL captured 100% as well. But P5 also participated in 2014 grind (-3.2% vs V2 0.0%). So participation gain in crisis, cost in grind.

Convexity:
- V2 is concave-ish due to de-risk (caps upside). P5 restores convexity: P5 top5 share 37.6% vs V2 30.1%, vol 9.06% vs 6.6%. Convexity bought with DD.

Per-regime (compression vs stress vs calm):
- Compression (2013 -23.1% raw, 2019 -15.3% raw): V2 -6.2%/-0.9%, P5 -6.2%/-2.2%. No win.
- Stress (2008 +22.1%, 2020 +32.8%): V2 +19.9%/+4.2%, P5 +19.9%/+41.0%. Win only in 2020-type crude crash.
- Calm (2017 +8.8% raw): V2 -0.2%, P5 -0.2% — flat.

Yearly table (excerpt) in Behavior above fully reported.

Worst days:
- Raw worst -12.15% (2019-09-03), V2 -2.85%, P5 -3.02%, CAP5 worst -2.84% — gear cuts tail, caps do not improve worst beyond gear.

Shuffled control: see Control section.

## Verdict — what failed, what is kept

Kept:
- CORE3 EQ V2 overlay (NOCAP, BOOK, OFF) as champion: IS 1.13/-10.2% OOS 0.95/-11.1% vol 6.6% CAGR 6.27%. This is the minimal boring config that meets MaxDD ~ -11% at reduced vol.
- JOINT flag as descriptive crisis state (not as overlay). Its information is real (+0.89% vs +0.037%) but its overlay value is marginal after fixing causality.
- Cushing direction for bzwti standalone — not kept at book.

Failed (construction, not idea):
- Probationary N=3/5/10 as DD-controlled windfall capture — fails utility test.
- Cushing continuous scaling at book — fails.
- Gap caps CAP8/CAP5 under V2 — fails.
- Per-complex DD overlay — fails.

## Best combination on Sharpe+convexity with DD tradeoff

Under strict DD -11.5% budget: BOOK NOCAP V2 OFF (0.95/-11.1%) is best. No upgrade beats it without DD slip.

If DD budget is -15% (relaxed): BOOK NOCAP J_P5 OFF (0.957/-14.7%) is max Sharpe, and it restores convexity (37.6% top5 share, 2020 +41% vs +4.2%). The trade is +0.007 Sharpe for +3.6% DD — not dominant. The honest recommendation is to stay at V2 and keep JOINT as a monitoring flag, not an overlay.

CAP5 S07 J_FULL BOOK (0.97/-13.0%) technically tops Sharpe but its IS 1.66 vs V2 1.13 is IS overfit from cap binding in low-vol IS tape; OOS 0.97 is only +0.02 over V2 and its IS/DD is unstable. Do not adopt.

## What remains open

- Single-day JOINT override (N=1). If duration is the cost, N=1 may keep most windfall with minimal bleed.
- JOINT for 0.5 re-cock (probationary 0.5 not FULL) — keeps half windfall with half DD cost.
- True forward test: all history tuned or selected. Only new data is real OOS.
- No CAP, no Cushing scaling, no per-complex at book. These are closed.

## Artifacts

- `book_oos_v8_A.py` — runnable harness, prints IS vs OOS, 90-row grid.
- `book_oos_v8_A_results.csv` — grid results (cap x cush x joint x overlay).
- This file.

Run: `python book_oos_v8_A.py` prints champion line `NOCAP BOOK V2 OFF | IS 1.13 DD -10.2% | OOS 0.95 DD -11.1% vol 6.6%` and top-10.

