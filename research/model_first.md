# Model-first principle (v2)

Adopted by the captain. Supersedes "representation rebuild as a
strategy-vs-champion exercise".

## Order

1. Model the margin system.
2. Verify the model component by component.
3. Verify the assembled model: the measured phenomena must EMERGE
   without tuning for them.
4. Only then derive position rules from the model's state.

The strategy is a consumer of the model, never a substitute for one.

## Model target

Daily crack margin m_t, per leg (crack_321, crack_gas, crack_ho) and
the crude basis (bzwti):

    m_t = norm_t + D_t + S_t + B_t + R_t

Components:
- norm_t  drift-corrected seasonal norm (item 7 drift is large).
- D_t     demand state: calendar cycle + cold severity (item 2) +
          blend windows (item 3).
- S_t     supply state: utilization seasonal position + capacity
          trend (items 1, 7).
- B_t     storage buffer: stock deviation regime (items 6, 10).
- R_t     flow residual: the reversion-carrying state.

The regime (expansion / compression / crisis) gates how R_t reverts.
P5: stretched R_t reverts only in expansion (4.7 sd phenomenon).

## Verification protocol

- Component evidence first: each component gets Tier 1 tables.
- Emergence check: the assembled model must display, unprompted:
  - cold severity monotonicity in winter (P1),
  - blend-window edge suppression and vol jump (P2),
  - expansion/compression asymmetry of stretched margins (P5),
  - norm drift (M7),
  - windfall and bleed as the SAME state (Round 4 structural
    finding).
- Iteration rule: improve components from their own evidence, never
  from a target Sharpe.
- Kill rule: a component kill must name the failed level
  (phenomenon / representation / timing / costs / interaction).

## Strategy derivation (later tier)

Position rules are read from model state: R_t crush depth, D_t cold
severity, blend-window state, regime gate. Tier 2 machines only after
the model holds.

## Relation to previous work

The alpha source map and the Tier 1 passes are the evidence base the
model must reproduce. They are not replaced.
