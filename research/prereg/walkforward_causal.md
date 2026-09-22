# Preregistration: walkforward_causal (and the contiguous-crush variant)

## Hypothesis
If every control is re-derived each year from prior data alone, the result no
longer depends on a control set chosen with hindsight. The contiguous-crush
rule states the thesis directly: enter only where the forward return is
positive for the contiguous run of low crush z-bins.

## Evaluation window
2012-01-01 to 2026-09-30. FULLY SPENT. Used for development and selection.

## Kill rule
Drop the variant if the block t-statistic at twice the measured cost per side
falls below 1.0 on the roll-free panel, or if the contiguous-crush entry region
cannot be identified on prior data in most years.

## Cost basis
Same as walkforward: 5 bps per side disclosed as an assumption, then the
measured 16.2 to 24.0 bps per side and its double in the cost ladder.

## Decision rule
The entry threshold is a SELECTION, not a derivation: it wanders widely across
training windows and is not pinned by the data. It is frozen here and must not
be re-tuned per run. No claim is certifiable on this window; only forward
sessions on or after 2026-10-01 count, at 250 sessions or more with positive net.
