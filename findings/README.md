# Findings — record moved

All pre-audit findings, research notes, the superseded headline report, and the
full audit trail (including the correction ledger) were removed from this tree
because they contained falsified performance figures. They are preserved with
their correction banners and evidence intact at:

    /home/sebas/algoterminal-archive/pre-audit-docs/

and in git history.

Why the figures were falsified. Four defects:

1. The price panel is yfinance raw front-month continuous, NOT back-adjusted.
   The legs roll on different dates, so the crack spread booked a scheduled
   contract-roll jump as profit every March.
2. The H1 storage gate used the current vintage of weekly stocks instead of the
   as-published values, so it saw numbers that were not public at the time.
3. The fixed-control walk-forward was in-sample for its controls across several
   years of the evaluation window.
4. The assumed trade cost per side was several times too low.

Nothing in this tree states a performance figure, by policy. To regenerate the
honest figures run `scripts/walkforward.py`, `scripts/walkforward_causal.py`,
and the roll-free-panel variants; `scripts/artifact_audit.py` prints the
corrected comparison; `scripts/audit_invariants.py` fails if any corrected
defect returns.
