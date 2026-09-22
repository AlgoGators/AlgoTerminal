"""Durable experiment counter.

Every configuration that is evaluated must increment this counter, so the
deflated Sharpe and any multiple-testing correction read a real number
instead of a guess. The previous project quoted a trial count of 1000 while
the repository alone held 1136 configuration rows across 85 result files,
which understated the correction.

The counter lives in results/trial_count.json. It starts at the known floor
(1136) so it cannot understate the historical search, and only ever grows.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "results" / "trial_count.json"
FLOOR = 1136  # visible pre-audit configuration rows; a floor, not a guess


def _read() -> dict:
    if PATH.exists():
        return json.loads(PATH.read_text())
    return {"trials": FLOOR, "note": "initialised to the known pre-audit floor"}


def count() -> int:
    """Current number of evaluated configurations."""
    return int(_read()["trials"])


def bump(n: int = 1) -> int:
    """Record n newly evaluated configurations. Returns the new total."""
    state = _read()
    state["trials"] = int(state["trials"]) + int(n)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(state, indent=2) + "\n")
    return state["trials"]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "bump":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        print(bump(n))
    else:
        print(count())
