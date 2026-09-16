# Hypothesis-first rule (v2 methodology)

Adopted after the captain's review of Batch 1/2 verdicts. The old
pipeline built a full position machine per idea, then read "no edge"
from the machine. That conflated four failures:

1. Phenomenon absent.
2. Phenomenon present, representation destroyed it.
3. Phenomenon present, timing wrong.
4. Phenomenon present, costs or overlay interaction ate it.

## Two tiers

Tier 1 phenomenon evidence. Measure the hypothesis directly. Buckets,
monotonicity, sign consistency, one shuffle control. No positions, no
engineered thresholds, no costs, no overlay. Question: does the
forcing variable display the claimed relationship, and in what shape?

Tier 2 machine. Build the minimal construction only where Tier 1
shows the phenomenon with the correct sign. If the machine fails,
record which level failed: phenomenon absent / representation /
timing / costs / interaction.

## Kill rule

A kill verdict must name the failed level. "No edge" is not a
mechanism. Kill verdicts from before this rule are re-opened for
Tier 1 evidence (see findings/hypothesis_pass_findings.md).
