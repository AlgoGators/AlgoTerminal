> **PRE-AUDIT DOCUMENT (2026-09-22).** Results here predate the independent
> artifact audit and are superseded. The price panel is yfinance raw
> front-month (NOT back-adjusted); the March contract-roll artifact alone was
> 40.2% of the measured P&L; and the assumed 5 bps/side cost is 3.2-4.8x too
> low. On roll-free prices at the measured cost the edge is not
> statistically significant. See `findings/artifact_audit.md` and
> `findings/claims_ledger.md`.

# Regime model — sub-regime distributions and transitions

Date: this session. Harness: `regime_state_harness.py`. Method:
research/regime_model.md. Regime identity from data (R2 = rolling
median/MAD baseline bands; R1 = Gaussian mixture on deseasonalized
level). All forward tables causal at the state date. GMM identity is
a research construct (full-sample fit); trading will use causal R2
and re-estimated identity.

## Marginal distributions (crack_321 daily returns)

| Axis/state | n | daily mean | std | p5 | p95 | E[fwd20] |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R2 comp | 432 | -1.11% | 7.8% | -13.5% | +10.0% | **+16.33%** |
| R2 norm | 3304 | +0.07% | 11.3% | -8.2% | +9.0% | +2.73% |
| R2 exp | 890 | +1.47% | 21.1% | -8.9% | +11.3% | -1.17% |
| phase trough | 1590 | +0.27% | 9.5% | -9.2% | +10.3% | **+7.52%** |
| phase peak | 1609 | +0.48% | 19.8% | -8.4% | +9.8% | +0.47% |
| weather cold | 613 | +0.07% | 11.4% | -9.6% | +10.7% | +5.07% |
| blend switch | 1139 | -0.08% | 23.6% | -10.6% | +9.7% | -0.83% |
| blend far | 2048 | +0.30% | 8.2% | -8.0% | +8.7% | **+6.60%** |
| margin crush | 1192 | +1.05% | 8.0% | -7.9% | +9.9% | **+11.79%** |
| margin stretch | 1488 | -0.67% | 14.6% | -10.7% | +10.3% | -2.86% |

## Two-way: regime x margin (crack_321)

| R2 \ margin | crush | norm | stretch |
| --- | ---: | ---: | ---: |
| comp | **+21.1%** (224) | +11.7% (164) | +9.1% (44) |
| norm | +10.2% (906) | +2.1% (1587) | **-4.4%** (811) |
| exp | -3.1% (55) | +0.7% (216) | -1.7% (599) |

The structure is now explicit:
- Long crush edge: strongest in comp (+21%), alive in norm (+10%),
  dead in exp.
- Short stretch edge: best in norm (-4.4%), weak in exp (-1.7%),
  NEVER in comp (+9.1% adverse).
- In comp ALL margin states go up (regime dominates).

## Interactions

- weather x margin: cold crush +16.3% vs warm crush +11.2% — cold
  severity adds to crush reversion (P1 mechanism as an interaction).
- blend x phase: switch hurts most in shoulder (-6.8%) and removes
  edge entirely (switch -0.83% vs far +6.60%).
- R2 x phase: comp peak +29.1% (n=59) and comp trough +18.8%: the
  comp regime amplifies across all phases.
- inventory: marginal draws/builds add little; builds are very
  volatile (std 31.9%).

## Transitions (R2 regime, fractions)

- comp -> comp 0.85, norm 0.15, exp 0.00.
- norm -> norm 0.96, comp 0.02, exp 0.02.
- exp -> exp 0.93, norm 0.07, comp 0.00.

Regimes are sticky; compression never jumps straight to expansion.
Regime-based positioning is viable: no daily flip-flop.

## Derived rule candidates (constants read from the shapes)

1. Long crush: enter in comp or norm; skip in exp. Expected fwd20
   +21% / +10% vs ~0 in exp.
2. Short stretch: enter in norm or exp; forbidden in comp.
   Expected -4.4% / -1.7% vs +9.1% adverse.
3. Cold severity scales crush longs up (crush cell +16.3% cold vs
   +11.2% warm).
4. Blend switch window: suppress reversion trading (edge removed,
   vol 23.6%).
5. Trough phase (winter months) is the favorable season.

## Caveats

- Overlapping 20d windows: cells are not iid; patterns are robust
  but not significance-tested per cell.
- R1 GMM clusters mostly into one "comp" state (level vs seasonal
  mean, skew-driven); R2 median/MAD is the more useful identity.
- R2 is causal (trailing median/MAD). GMM identity needs a temporal
  model (HMM) before use in trading.

## Artifacts

- `regime_state_harness.py`, `results/regime_state.csv`
- `research/regime_model.md` updated with results.
