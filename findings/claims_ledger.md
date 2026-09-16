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
## Rule

Every future claim enters here with its evidence level, method, and
reference. Claims without a level do not get cited in summaries.
