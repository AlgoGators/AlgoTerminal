# Preregistration: walkforward (fixed controls)

## Hypothesis
The refining-margin crush signal mean-reverts. A walk-forward that re-estimates
every data-driven component (exposure curve, tail scale, circuit breaker,
trailing distance) once per year on prior data only, with four controls fixed,
captures the reversion without lookahead.

## Evaluation window
2012-01-01 to 2026-09-30. This window is FULLY SPENT: it was used for both
development and selection, so nothing computed on it is out-of-sample evidence.

## Kill rule
Drop the variant if, on the roll-free panel, the block t-statistic at twice the
measured cost per side falls below 1.0, or if the sign of the mean return is
not positive. A variant that needs a single cost assumption to survive is dead.

## Cost basis
Historical comparison at 5 bps per side, disclosed as an assumption. The cost
ladder then applies the measured 16.2 to 24.0 bps per side and its double.
Roll carry is measured separately, not assumed.

## Decision rule
No claim is certifiable on this window. Only forward sessions on or after
2026-10-01 count as evidence, and only when the forward log has at least 250
sessions with a positive net.
