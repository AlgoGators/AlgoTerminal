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

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREREG = ROOT / "research" / "prereg"
REQUIRED = ("Hypothesis", "Evaluation window", "Kill rule", "Cost basis", "Decision rule")


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
    problems = check(name)
    if problems:
        raise SystemExit(
            f"REFUSING TO RUN '{name}': pre-registration incomplete.\n  "
            + "\n  ".join(problems)
            + f"\nWrite research/prereg/{name}.md with: " + ", ".join(REQUIRED)
        )


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
