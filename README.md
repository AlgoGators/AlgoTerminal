# Strategy v2

Next-generation crack-complex strategy. Worktree: `v2-dev`.

## Purpose

v2 reworks the frozen v1 strategy. v1 is CORE3 equal-weight plus V2 overlay
in the `algoterminal-strategy-audit` worktree. v2 addresses four critique
gaps found in the v1 review:

1. Short side untested and long-only asymmetry unproven (Phase 1).
2. Cross-sectional factor holds one leg at a time (Phase 2).
3. Physical flow never modeled directionally, only gated (Phase 3).
4. Z-pipeline discards shape and hides structural assumptions (Phase 4).

## House rules

- v1 stays frozen. Nothing in the audit worktree gets edited by v2.
- v2 has its own inputs. `engine/panel_v2.parquet` is immutable.
- Every phase: pre-register hypothesis, build harness, run negative
  control, one IS/OOS pass, write decision memo, keep artifacts.
- Every boundary: kill constructions, keep ideas. Behavior first,
  numbers second.
- The v1 forward test runs independently of v2.

## Phase status

| Phase | Cost | Status |
| --- | --- | --- |
| 0 Scaffolding | trivial | done (commit 5558b0e) |
| 1 Side structure | done (mirror test) | findings/phase1_findings.md |
| 1R Side structure (mechanism-based) | done | findings/phase1r_findings.md |
| 2 Basket + depth | medium | preregistered |
| 3 Flow modeling | done | findings/phase3_findings.md |
| 4 Representation | expensive | preregistered |

Preregistration docs live in `research/`. Each phase gates the next.

## Layout

```
README.md
inputs_manifest.txt    frozen input hashes
engine/                corrected v4 engine snapshot + frozen panel + data inputs (eia/weather/cot)
research/              methodology, pre-registrations, relation graph (graph/)
findings/              decision memos, final report, claims ledger
results/               output CSVs
scripts/               all v2 harnesses, tools, metrics, verification
legacy/                v1-era base code, docs, and old result CSVs (from the original snapshot)
discovery/             generated graphify outputs (gitignored)
```

## v1 references (read-only)

- Audit worktree: `/home/sebas/algoterminal-strategy-audit`
- v1 champion reference numbers: `book_oos_v4_results.csv` row
  CORE3, EQ, NOCAP, overlay=True.
- v1 frozen forward protocol:
  `/home/sebas/algoterminal-strategy-audit/research/forward_test_protocol.md`
