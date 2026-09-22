"""Pre-registration gate.

An experiment must not run before its hypothesis, evaluation window, kill
rule, cost basis, and decision rule are written down. Without that, the
experiment becomes a search over the evaluation window, which is what produced
the earlier false result.

Each experiment script calls `require("<name>")` at the top. It exits if
`research/prereg/<name>.md` is missing or incomplete. Reproduction of an
already registered experiment passes, because the file exists.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREREG = ROOT / "research" / "prereg"
REQUIRED = ("Status", "Hypothesis", "Evaluation window", "Kill rule", "Cost basis", "Decision rule")

# artifacts produced by each registered experiment
ARTIFACTS: dict[str, list[str]] = {
    "walkforward": ["results/walkforward_series.csv", "results/spot_fixed_series.csv"],
    "walkforward_causal": ["results/walkforward_causal_series.csv", "results/spot_causal_series.csv",
                            "results/wf_crush_futures_series.csv", "results/wf_crush_spot_series.csv"],
}


def _sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    cur = None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = ""
        elif cur:
            out[cur] += line + "\n"
    return out


def check(name: str) -> list[str]:
    """Return a list of problems; empty means the registration is valid."""
    p = PREREG / f"{name}.md"
    if not p.exists():
        return [f"missing registration file: research/prereg/{name}.md"]
    secs = _sections(p.read_text())
    problems = []
    for req in REQUIRED:
        body = secs.get(req, "").strip()
        if not body:
            problems.append(f"missing or empty section: '{req}'")
    return problems


def require(name: str) -> None:
    problems = check(name) + order_problems(name)
    if problems:
        raise SystemExit(
            f"REFUSING TO RUN '{name}': pre-registration incomplete.\n  "
            + "\n  ".join(problems)
            + f"\nWrite research/prereg/{name}.md with: " + ", ".join(REQUIRED)
        )


def _first_commit_ts(relpath: str) -> int | None:
    """Unix time of the earliest commit touching relpath, or None."""
    try:
        out = subprocess.run(["git", "log", "--format=%ct", "--reverse", "--", relpath],
                             cwd=ROOT, capture_output=True, text=True, timeout=20)
    except Exception:
        return None
    lines = [x for x in out.stdout.splitlines() if x.strip()]
    return int(lines[0]) if lines else None


def order_problems(name: str) -> list[str]:
    """The registration must be committed BEFORE the run it registers.

    If an artifact already existed when the registration was first committed,
    the registration is retrospective and carries no evidential weight. That is
    allowed only if the file says so.
    """
    prereg_ts = _first_commit_ts(f"research/prereg/{name}.md")
    if prereg_ts is None:
        return []  # not committed yet: nothing to compare
    predating = [a for a in ARTIFACTS.get(name, [])
                 if (_first_commit_ts(a) or prereg_ts) < prereg_ts]
    if not predating:
        return []
    text = (PREREG / f"{name}.md").read_text().lower()
    if "retrospective" in text:
        return []  # declared, no evidential weight claimed
    return [f"artifacts predate the registration ({', '.join(predating)}); "
            f"mark the prereg retrospective, or re-run only after registering"]


if __name__ == "__main__":
    import sys

    names = sys.argv[1:] or [p.stem for p in sorted(PREREG.glob("*.md"))]
    bad = 0
    for n in names:
        probs = check(n)
        print(f"  [{'ok' if not probs else 'FAIL'}] {n}"
              + ("" if not probs else ": " + "; ".join(probs)))
        bad += 1 if probs else 0
    raise SystemExit(1 if bad else 0)
