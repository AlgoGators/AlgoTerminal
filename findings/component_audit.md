# Component audit — findings

Date: this session. Harness: `audit_harness.py`. Prereg:
`research/component_audit.md` (ac7b82a).

## 1. Gear lookahead fixed

ES5 of the crush-state fwd20 on TRAIN only: -21.9% (full-sample
mixture was -27.4%). gear_train = 10/21.9 = 0.457 (full-sample gear
was 0.365).

The old full-sample gear was CONSERVATIVE, not optimistic: validation
tails made ES5 larger, so the gear was lower. Still, the paramet is
now TRAIN-derived and clean.

## 2. Rebuilt-norm variant measured (no more assumption fights)

| Variant | TRAIN t | VALIDATE t | OOS t | FULL t | neg% |
| --- | ---: | ---: | ---: | ---: | ---: |
| old norm (current z) | 2.53 | 1.54 | 2.73 | 3.01 | 16-18% |
| new median/robust norm | 1.10 | **-1.35** | 0.08 | 0.08 | 9-13% |

The rebuilt median norm KILLS the edge: VALIDATE -5.21% ann,
OOS ~0. Decision per prereg rule: keep the old norm. The tradeoff is
documented, not dodged:
- The old norm's statistical assumptions are false (audit: drift,
  mean vs median, variance, Gaussianity).
- Empirically, in this construction, the old norm carries the edge;
  the assumption-clean norm carries none.
- The honest middle path (drift-corrected or decaying-window norm)
  is named, not tested yet.

The new norm also labels crush states very differently (494 vs 1193
crush days), so its curve construction behaves differently. The
failure is not about the norm's shape alone; it is about which
normalization produces states that predict forward returns.

## 3. Ledger labels corrected

- 5% expected-return bar and the w/max normalization: ANCHORS
  (mislabeled as derived before; fixed).
- Gear: TRAIN-derived now.
- Curve shape, regime identity (median/MAD), H1 z>=1: data-derived.
- Stops (trailing 1.25s, hard 20%, CB 3s, cooldown 5): still v1
  anchors, UNACCOUNTED — flagged as open work (derive stop
  parameters from the per-state distribution next).
- Selection residue: a deflated Sharpe has not been computed for the
  Bar5 stack. Open work.

## Remaining unaccounted items (open)

1. Stop/circuit-breaker parameters (v1 anchors).
2. Vol target 0.50 and MAX_LEV 1.0 (v1 anchors).
3. Deflated Sharpe for the final stack.
4. Drift-corrected norm middle path.

## Artifacts

- `audit_harness.py`, `results/component_audit.csv`
