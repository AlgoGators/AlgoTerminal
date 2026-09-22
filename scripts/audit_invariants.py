"""Audit invariants. Fails if a corrected defect silently returns.

Run: python scripts/audit_invariants.py

Checks, in order:
  1. No undocumented "OOS" window that overlaps its TRAIN window. The five
     harnesses that still carry the old window must also carry the warning
     marker, so the defect can never be silent again.
  2. No live factor-return computation uses pct_change. The one documented
     exception is the frozen legacy engine/factor_book.py (dead code path).
  3. relnorm has no full-sample median fallback (latent lookahead).
  4. No v2 doc asserts the panel is back-adjusted.
  5. The two quoted walk-forward artifacts still reproduce their numbers.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILURES.append(f"{label}: {detail}")


def main() -> int:
    print("1. OOS window vs TRAIN window")
    pat = re.compile(r'OOS_LO,\s*OOS_HI\s*=\s*"([\d-]+)",\s*"([\d-]+)"')
    for p in sorted((ROOT / "scripts").glob("*.py")):
        t = p.read_text()
        m = pat.search(t)
        if not m:
            continue
        train = re.search(r'TRAIN_LO,\s*TRAIN_HI\s*=\s*"([\d-]+)",\s*"([\d-]+)"', t)
        train_hi = train.group(2) if train else "2018-12-31"
        overlaps = m.group(1) <= train_hi
        documented = ("NOT out-of-sample" in t) or ("WARNING" in t)
        check(f"{p.name}: window declared{'' if overlaps else ' (non-overlapping)'}",
              (not overlaps) or documented,
              "overlapping OOS window without the warning marker")

    print("2. pct_change in live factor returns")
    # Narrow rule: the G2 bug is a factor return written as
    #   pos * level.pct_change()
    # A bare pct_change on a plain price series (e.g. a correlation
    # diagnostic) is legitimate and must not be flagged.
    bug = re.compile(r"\*\s*[\w\.\[\]\"']+\.pct_change\(\)")
    allowed = {ROOT / "engine" / "factor_book.py",
               ROOT / "scripts" / "audit_invariants.py"}  # frozen/documented; self
    hits = []
    for d in ("scripts", "engine"):
        for p in sorted((ROOT / d).glob("*.py")):
            if p in allowed:
                continue
            if bug.search(p.read_text()):
                hits.append(str(p.relative_to(ROOT)))
    check("no live pct_change factor returns", not hits, f"found in {hits}")

    print("3. relnorm fallback causality")
    me = ROOT / "scripts" / "audit_invariants.py"
    hits = [str(p.relative_to(ROOT))
            for p in (ROOT / "scripts").glob("*.py")
            if p != me and "fillna(inv.median())" in p.read_text()]
    check("no full-sample median fallback", not hits, f"found in {hits}")

    print("4. back-adjustment claims in v2 docs")
    bad = []
    for d in ("findings", "research"):
        for p in (ROOT / d).glob("*.md"):
            t = p.read_text()
            if "back-adjusted closes" in t or "continuous back-adjusted" in t:
                bad.append(str(p.relative_to(ROOT)))
    check("no false back-adjustment claim", not bad, f"found in {bad}")

    print("5. quoted artifacts reproduce")
    import numpy as np
    import pandas as pd
    # Availability-correct H1 (as-published storage) is the default, so these
    # are the honest baselines. Values change only with a real methodological
    # correction, never silently.
    expect = {
        "walkforward_series.csv": (0.701, 10.03, 5),
        "spot_fixed_series.csv": (0.464, 6.77, 4),
        "wf_crush_spot_series.csv": (0.628, 8.59, 4),
    }
    for fname, (sh, ann, tol) in expect.items():
        p = ROOT / "results" / fname
        if not p.exists():
            check(f"{fname} present", False, "missing")
            continue
        r = pd.read_csv(p, parse_dates=["date"]).set_index("date")["ret"].dropna()
        got_sh = r.mean() / r.std(ddof=1) * np.sqrt(252)
        got_ann = r.mean() * 252 * 100
        ok = abs(got_sh - sh) < 1e-3 and abs(got_ann - ann) < 0.01
        check(f"{fname}: Sharpe {got_sh:.3f}, ann {got_ann:+.2f}%", ok,
              f"expected Sharpe {sh}, ann {ann}")

    print("6. research gates")
    import importlib.util as _ilu
    _g = _ilu.spec_from_file_location("gates", ROOT / "scripts" / "gates.py")
    gates = _ilu.module_from_spec(_g)
    _g.loader.exec_module(gates)
    dc = gates.load_dc()
    ok_c, _lines = gates.causality_gate(dc)
    check("causality gate (truncate and compare)", ok_c,
          "a transform at t changed when data after t was added")
    _lvl = dc.fb.build_levels(pd.read_parquet(ROOT / "engine" / "panel_spot.parquet").sort_index())["crack_321"]
    _finds = gates.artifact_scan(_lvl)
    check("data artifact gate (roll-free panel)", not _finds, f"findings: {_finds}")

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}):")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("all invariants hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
