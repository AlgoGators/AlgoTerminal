"""Evaluation-window burn register.

Each look at an evaluation window spends information. On this project the
entire historical sample was already used for development and selection, so it
is fully spent: no result computed on it can be called out-of-sample evidence,
no matter how it is labelled.

This module records every read of the historical window, and states plainly
that only FORWARD data can certify a claim. A claim is allowed only when the
forward log has enough sessions and the result is positive there.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "results" / "eval_window_log.jsonl"
FORWARD_LOG = ROOT / "results" / "forward_log.jsonl"

SPENT_WINDOW = ("2012-01-01", "2026-09-30")   # fully spent: development + selection
FORWARD_START = "2026-10-01"                   # the only clean window
MIN_FORWARD_SESSIONS = 250                     # about one year before a claim


def record(source: str, note: str = "") -> None:
    """Log a read of the historical evaluation window. One row per source per day."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    if LOG.exists():
        for line in reversed(LOG.read_text().splitlines()):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("source") == source and str(row.get("at", "")).startswith(today):
                return
    with LOG.open("a") as fh:
        fh.write(json.dumps({
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source,
            "window": SPENT_WINDOW,
            "note": note,
        }) + "\n")


def reads() -> int:
    if not LOG.exists():
        return 0
    return sum(1 for line in LOG.read_text().splitlines() if line.strip())


def forward_sessions() -> int:
    """Sessions in the forward log on or after FORWARD_START."""
    if not FORWARD_LOG.exists():
        return 0
    n = 0
    for line in FORWARD_LOG.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("date", "")) >= FORWARD_START:
            n += 1
    return n


def forward_net_positive() -> bool:
    if not FORWARD_LOG.exists():
        return False
    total, n = 0.0, 0
    for line in FORWARD_LOG.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("date", "")) >= FORWARD_START and "ret" in row:
            total += float(row["ret"])
            n += 1
    return n > 0 and total > 0


def evidence_status() -> str:
    """'forward' if forward evidence exists, else 'none'."""
    if forward_sessions() >= MIN_FORWARD_SESSIONS and forward_net_positive():
        return "forward"
    return "none"


def claim_allowed() -> tuple[bool, str]:
    status = evidence_status()
    if status == "forward":
        return True, "forward evidence present"
    return False, (
        f"historical window {SPENT_WINDOW[0]}..{SPENT_WINDOW[1]} is fully spent "
        f"({reads()} recorded reads); forward sessions so far: {forward_sessions()} "
        f"(need {MIN_FORWARD_SESSIONS} with positive net). No claim is certifiable yet."
    )


if __name__ == "__main__":
    ok, why = claim_allowed()
    print(f"evidence status: {evidence_status()}")
    print(f"historical-window reads: {reads()}")
    print(f"claim allowed: {ok} :: {why}")
