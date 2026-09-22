# Claims ledger

Controlling catalog. Evidence levels:
HOLD (clean non-overlap statistics), DIRECTIONAL (clean, direction
only), IDEA (not held), FALSIFIED (clean or replicated negative),
CONFIRMED-STAT (overlap-era but replicated), QUEUED (needs clean
redo), CONSTRAINED (data).

| Claim | Level | Method | Reference |
| --- | --- | --- | --- |
| v1 CORE3 EQ + V2 book has positive edge OOS/FULL | HOLD | clean 20d blocks, t 2.4-3.3 | champion_restatement.md |
| Champion IS window edge | DIRECTIONAL | clean blocks, CI crosses zero, n=33 | champion_restatement.md |
| Champion overlay cuts negative blocks 40% to 21% | CONFIRMED-STAT | block neg fraction | champion_restatement.md |
| Champion Sharpe magnitude 0.86 | IDEA | overlap-selected; not a clean claim | book_oos_v4_results.csv |
| Long-crush edge (comp/norm regimes) | DIRECTIONAL | clean non-overlap; train t=3.81, validate n=15 | hold_validation.md |
| Short-stretch edge | FALSIFIED | clean; sign flips on validate | hold_validation.md |
| Cold-severity tilt | IDEA | unmeasurable non-overlap (n=1-7) | hold_validation.md |
| Blend-window suppression | IDEA | unmeasurable non-overlap | hold_validation.md |
| EIA scaling hurts the book | HOLD | clean blocks, scaled CI crosses zero | champion_restatement.md |
| Weather gate zero-info | QUEUED | overlap-era; rebuild needed | LONG_BACKTEST Round 5 |
| Storage gates H1/H2 hurt | QUEUED | overlap-era; rebuild needed | LONG_BACKTEST Round 6 |
| Crash-put overlay uneconomic | QUEUED | modeled screen, overlap-era | LONG_BACKTEST Round 5 |
| Multi-leg F2 breadth (raw) | DIRECTIONAL | raw leg Sh 0.589->0.700; book killed by overlay | multileg_f2_tier2.md |
| Depth sizing monotone | DIRECTIONAL | fwd20 7.3->16.3 buckets; redundant after caps | reassessment_probes.md |
| Norm drift large | HOLD | M7 decade table | batch1_findings.md |
| Book = 2 bets | HOLD | correlation matrix | batch1_findings.md |
| Regime transitions sticky | CONFIRMED-STAT | R2 transition matrix | regime_state.md |
| Seasonal-norm assumptions mostly false | HOLD | assumption audit | shape_pass.md |
| Regime x margin structure (comp long/exp stretch short) | DIRECTIONAL | overlap tables; clean validate only L side | regime_state.md + hold_validation.md |
| Cushing ratio / crude-glut / load / maintenance / propane-gas | FALSIFIED | Tier 1 | batch2 + probes |

| Champion edge survives 10/20 and 20/40 costs | HOLD | clean blocks | direction1.md |
| Champion OOS SR not explained by <=1000 trials | HOLD | deflated Sharpe ~1.0 | direction1.md |
| Overlay forgives ~73pp gross; top-10 capture ~35%; 2014-16 flat | CONFIRMED-STAT | clean block ledger | direction1.md |
| CL yfinance vs EIA settlement level-consistent | PARTIAL | corr 0.997, 2% abs; others constrained | direction1.md |
| Weather gate NG kills edge | FALSIFIED (clean blocks) | direction2.md |
| Weather gate HO | NULL | clean blocks both zero | direction2.md |
| H1 product-stock gate crack_321 | REVISED: helps (clean t=2.08) | direction2.md |
| H2 natgas gate ng | FALSIFIED (clean) | direction2.md |
| Crash-put overlay uneconomic | FALSIFIED (prem 40-73% of clean mean) | direction2.md |
| Crush state fwd20 positive | HOLD (OOS t=2.65 n=48) | direction2.md |
| Joint crisis filter | CONSTRAINED (6 days; reduced into crush) | direction2.md |
| HMM regime identity rule (comp/comp+norm x crush) | HOLD-clean (t 1.93/2.12) | non-overlap OOS, custom HMM | direction3.md |
| Rebuilt median norm crush cell | DIRECTIONAL (n=17, t=1.38, wide CI) | non-overlap | direction3.md |
| Utilization trend +0.25 pts/yr | CONFIRMED-STAT | decade slope | direction3.md |
| Seasonal amplitude trend rising | CONFIRMED-STAT (era-driven caveat) | decade slope | direction3.md |
| Crush state mixture: mean +11.7%, P(>10%)=49%, ES5 -27% | HOLD-shape | mixture model | direction3.md |
| RBOB COT net z vs 20d crack | FALSIFIED/weak (within noise) | direction4.md |
| Crude COT series | CONSTRAINED (no NYMEX in public datasets) | direction4.md |
| International cracks (Rotterdam/Singapore) | CONSTRAINED (EIA intl route 400) | direction4.md |
| Per-complex overlay + Brent legs | FALSIFIED (0.425-0.552 vs 0.862) | direction4.md |
| Named-event pattern (crisis troughs precede +20d) | IDEA (descriptive, small n) | direction4.md |
| Regime gate on crack (raw book) | DIRECTIONAL-clean (raw t 2.94/3.43); rejected at overlay | final_strategy.md |
| H1 in book under regime gate | NULL (redundant) | final_strategy.md |
| Final integration V2 | REJECTED; failed level = overlay interaction | final_strategy.md |
| Champion remains deployable benchmark | HOLD | final_strategy.md |
| F2 multi-leg breadth standalone | FALSIFIED/dropped (OOS CI incl 0) | model_book.md |
| F3 Brent-WTI reversion standalone | FALSIFIED/dropped | model_book.md |
| B1h = regime-gated crush + H1 de-risk | HOLD (OOS t 2.93 / FULL 3.33, neg 16%) | model_book.md |
| Two-bet book diversification | NOT CONFIRMED in new architecture (B1h single sleeve wins) | model_book.md |
| V2 overlay excluded from new construction | DESIGN (recurring constraint) | model_book.md |
| ES-derived risk layer (10%/ES5 27.4% gear) | HOLD (DD -11.0%, t 2.93, neg 16%) | next_direction.md |
| Cold severity at 5/10d horizons | FALSIFIED at those horizons | next_direction.md |
| Gas-HO relative: seasonal conditional structure | DIRECTIONAL lead (clean test pending) | next_direction.md |
| Utilization-surprise tilt on B1h | NULL | next_direction.md |
| Forward protocol v2 (B1h) | WRITTEN | forward_protocol_v2.md |
| 0.75/-0.5 thresholds | REMOVED; replaced by TRAIN curve shape + 5% bar (zcut ~ -0.68) | derived_thresholds.md |
| Bar5 curve exposure | HOLD OOS/FULL (t 2.53/2.82); borderline VALIDATE | derived_thresholds.md |
| Fully unbarred curve | FALSIFIED out-of-window (VALIDATE t 0.97) | derived_thresholds.md |
| Gear lookahead | FIXED (ES5 TRAIN -21.9% -> gear 0.457; old gear conservative) | component_audit.md |
| Rebuilt median norm | FALSIFIED in curve construction (VALIDATE -5.2%, OOS ~0) | component_audit.md |
| 5% bar and w/max normalization | ANCHORS (labels corrected) | component_audit.md |
| Stops / CB / vol target / MAX_LEV | UNACCOUNTED v1 anchors (open work) | component_audit.md |
| Deflated Sharpe for Bar5 stack | OPEN | component_audit.md |
| Significance-derived bar (zcut -0.91) | DIRECTIONAL (held with old controls OOS t 2.14) | derived_controls.md |
| Derived stop pack (nat 99%/2% defaults) | FALSIFIED vs old controls (OOS 1.87 vs 2.14); policy anchors matter | derived_controls.md |
| Unified scale (budget/ES5) | HOLD-equivalent (0.468) | derived_controls.md |
| Lookback 90 window | plateau confirmed (OOS 2.48/FULL 2.28 NEW) | derived_controls.md |
| Derived-controls sweep | VALID after CB-sign fix; HOLD OOS/FULL (t 3.96/3.66), VALIDATE borderline | derived_controls_sweep.md |
| Swept controls | entry t=1.5, budget 7.5%, trail 85th, cool 0-3, CB inactive | derived_controls_sweep.md |

| Reproducibility bar | NEW RULE: sweeps must first reproduce the base anchor | derived_controls_sweep.md |
| DSR units | CORRECTED (was annualized-SR input; now per-period daily SR as published) | metrics_final.py |
| DSR final config | OOS 0.907-0.960, FULL 0.824-0.912, TRAIN 0.551-0.710, VALIDATE 0.110-0.212 | metrics_final.csv |
| DSR champion (earlier) | SUPERSEDED (same annualized-input bug) | harden_harness.py |

## 2026-09-22 — artifact audit (independent re-measurement)

Full memo: `findings/artifact_audit.md`. Roll-free twin panel and
re-runnable comparison: `scripts/artifact_audit.py`.

| Claim | Level | Method | Reference |
| --- | --- | --- | --- |
| March-1 RBOB jump = scheduled gasoline spec roll, not economics | HOLD | 19/19 futures years +9.2% vs 14/20 spot years +2.5% | artifact_audit.md F1 |
| March-1 sessions carry 40.2% of fixed-control walk-forward P&L | HOLD | direct P&L attribution | artifact_audit.md F1 |
| Top 1% of days carry 81% of variance | HOLD | sum-of-squares decomposition | artifact_audit.md F2 |
| Quoted fixed-control Sharpe 0.853 | SUPERSEDED (roll artifact) | ex March 1: 0.636; roll-free spot: 0.385 | artifact_audit.md F3 |
| Quoted causal Sharpe 0.704 | SUPERSEDED (roll artifact) | ex March 1: 0.434; roll-free spot: 0.601 | artifact_audit.md F3 |
| Deployable benchmark has an edge (fixed controls) | FALSIFIED | roll-free spot block t 1.44, DSR 0.036 | artifact_audit.md F3 |
| Causal variant weak positive edge | DIRECTIONAL | roll-free spot t 2.33, DSR 0.16; not significant | artifact_audit.md F3 |
| Bare crush signal is nearly significant on roll-free prices | IDEA | spot block t 1.68 at z<=-0.70, MaxDD -75% | artifact_audit.md F4 |
| Causal entry cut "largest bin t>=1.5" implements the crush thesis | FALSIFIED | selects least-crushed bin; zcut +0.70 in 2012-2014 | artifact_audit.md F5 |
| Committed causal walk-forward artifact reproduces | FALSIFIED | committed Sh 0.459 vs committed-code Sh 0.704 | artifact_audit.md F6 |
| Instantaneous curve slope equals realized roll carry | FALSIFIED (own error, discarded) | +34%/yr estimate vs -0.3%/yr measured | artifact_audit.md F4b |
| DSR trial count 1000 is adequate | FALSIFIED | >=1136 configs in-repo; DSR falls to 0.41 at N=20000 | artifact_audit.md F7 |
| Honest real result (roll-free, 2012-2026) | HOLD | ann +4.7..+8.4%, Sh 0.39..0.67, t 1.4..2.5, DSR 0.04..0.23 | artifact_audit.md |
| March roll gap is +3.92 $/bbl, 18/18 years, repaid over the other months | HOLD | rolled vs roll-free spot spread, net ~0/yr | artifact_audit.md F1 |
| Assumed -20 bps/yr roll drag | CONFIRMED-STAT | realized carry -0.3%/yr measured directly | artifact_audit.md F4b |
| Causal entry threshold is pinned by the data | FALSIFIED | zcut wanders +0.70 to -0.91; thin windows stay positive | artifact_audit.md F5b |
| Contiguous-crush entry rule | DIRECTIONAL | futures t 2.88; roll-free spot t 2.54, DSR 0.234 | wf_crush_* |
| Assumed 5 bps/side trade cost | FALSIFIED | measured 16.2-24.0 bps/side, 3.2-4.8x low | artifact_audit.md F8 |
| Roll-free edge at measured cost | FALSIFIED | block t 1.0 (fixed) to 2.1 (contiguous-crush) at 24 bps | artifact_audit.md F8 |
| Forward protocol v3 (roll-free, measured cost) | WRITTEN | frozen; no Sharpe gate | research/forward_protocol_v3.md |

## 2026-09-22 — integrity sweep (code, data, docs)

Remaining defect inventory. Each item was verified in the tree, not
inferred. Fixes applied where the fix is unambiguously correct and
changes no quoted number.

| Claim | Level | Evidence | Status |
| --- | --- | --- | --- |
| "OOS" window in 10 harnesses is out-of-sample | FALSIFIED | OOS 2007-07-30..2023-09-08 contains TRAIN 2007-2018 | warning added to 6 harnesses |
| honesty_harness "OOS" and "IS" windows are distinct | FALSIFIED | OOS 2007-2023 overlaps IS 2023-2026 | warning added |
| Ledger claim "book has positive edge OOS" | DOWNGRADED to IN-SAMPLE | source champion_restatement.md used the mislabelled window | see above |
| yfinance panel is back-adjusted | FALSIFIED | month-start jump ratio 2.06x; +3.915 $/bbl March gap 18/18 | claimed in engine_v2.py:143, LONG_BACKTEST:10, TRACK_C:141, unseen_validation:595 |
| relnorm fallback is causal | FIXED | was fillna(full-sample median); now fillna(1.0) | 4 files; artifacts byte-identical |
| Missing price leg contributes zero return | BIAS (open) | sum(axis=1) skips NaN; bzwti 1.5% missing in panel_v2 | flagged, not changed |
| EIA weekly storage is point-in-time | FALSIFIED | single current vintage, no revision history; H1 gate uses revised data | flagged, not fixed |
| Fixed-control walk-forward 2012-2018 is out-of-sample for controls | FALSIFIED | controls selected on 2007-2018 | clean segment 2019+: futures t 1.99, spot t 1.26 |
| Published factor_book.py has no return-basis bug | FALSIFIED | pct_change at lines 314/318 (the G2 bug) | dead internally, live in the public repo |
| Audit-repo forward machinery is clean | FALSIFIED | forward_test/forward_shadow/unseen_validation use panel_v2 and 5/20 | superseded by forward_protocol_v3.md |
| final_report.md headline is current | FALSIFIED (banner added) | quoted Sharpe 0.86, +11.3%/yr | superseded banner at top |
| Honest clean-sample result (2019+) | HOLD | futures t 1.99, spot t 1.26, DSR weak | nothing significant |
| H1 gate used current-vintage storage (lookahead) | FALSIFIED -> FIXED | as-published archive rebuilt; Sharpe 0.853 -> 0.701 | artifact_audit.md F9 |
| Storage revision content is material | FALSIFIED | 4/788 releases differ; median revision 0 | artifact_audit.md F9 |
| Fixed-control 2012-2018 is out-of-sample for controls | FALSIFIED -> DEMOTED | clean 2019+: futures t 1.68, spot t 1.21 | artifact_audit.md F10 |
| Missing leg contributes zero return | BOUNDED | crack_321 2 NaN days, bzwti 73 (1.51%); superseded aggregation only | artifact_audit.md F11 |
| Honest headline (as-published H1, roll-free, measured cost) | HOLD | ann +4.9..+8.6%, Sh 0.45..0.63, t 1.2..2.4, DSR 0.07..0.21 | artifact_audit.md pass 5 |

## Rule

Every future claim enters here with its evidence level, method, and
reference. Claims without a level do not get cited in summaries.
