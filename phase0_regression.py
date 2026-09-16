"""Phase 0 gate: reproduce the v1 champion in the v2 engine.

The v2 engine is a byte-identical copy of the corrected v4 engine.
This script verifies that it reproduces the frozen v1 reference numbers
from the audit worktree before any v2 change is allowed.

Reference (frozen, book_oos_v4_results.csv, CORE3 EQ NOCAP overlay=True):
  IS  : sharpe 0.8484624525106065, dd -0.1038936638413428
  OOS : sharpe 0.8621579162152395, cagr 0.05622456533983633,
        dd -0.10731104468333641, vol 0.0659289687709905,
        worst -0.028486405465007976
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
ENGINE = ROOT / "engine"
PANEL = ENGINE / "panel_v2.parquet"

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

REFERENCE = {
    ("IS", "sharpe"): 0.8484624525106065,
    ("IS", "maxdd"): -0.1038936638413428,
    ("OOS", "sharpe"): 0.8621579162152395,
    ("OOS", "cagr"): 0.05622456533983633,
    ("OOS", "maxdd"): -0.10731104468333641,
    ("OOS", "vol"): 0.0659289687709905,
    ("OOS", "worst_day"): -0.028486405465007976,
}


def champion_stats() -> dict[tuple[str, str], float]:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    factors, rets, turn = b4.build_v4(levels, None)
    net = b4.apply_costs(factors, rets, turnover=turn)
    isw = b4.window(net, b4.IS_START, df.index.max())
    oos = b4.window(net, b4.OOS_START, b4.IS_START)
    w = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], "EQ")
    book = b4.book_returns(net, b4.SUBSETS["CORE3"], w)
    ob_is = b4.apply_overlay(book.loc[isw.index])
    ob_oos = b4.apply_overlay(book.loc[oos.index])
    si = b4.stats(ob_is)
    so = b4.stats(ob_oos)
    return {
        ("IS", "sharpe"): si["sharpe"], ("IS", "maxdd"): si["maxdd"],
        ("OOS", "sharpe"): so["sharpe"], ("OOS", "cagr"): so["cagr"],
        ("OOS", "maxdd"): so["maxdd"], ("OOS", "vol"): so["vol"],
        ("OOS", "worst_day"): so["worst_day"],
    }


def main() -> None:
    sha = __import__("hashlib").sha256(PANEL.read_bytes()).hexdigest()
    print(f"panel sha256: {sha}")
    print(f"rows: {len(pd.read_parquet(PANEL))}")
    got = champion_stats()
    failures = 0
    print(f"{'metric':<16} {'reference':>16} {'got':>16} {'max_rel_err':>12}")
    for key, ref in REFERENCE.items():
        val = got[key]
        err = abs(val - ref) / max(abs(ref), 1e-12)
        flag = "OK" if err <= 1e-6 else "FAIL"
        if err > 1e-6:
            failures += 1
        print(f"{key[0] + ' ' + key[1]:<16} {ref:16.12f} {val:16.12f} {err:12.2e} {flag}")
    if failures:
        print(f"RESULT: FAIL ({failures} metrics out of tolerance)")
        raise SystemExit(1)
    print("RESULT: PASS v2 engine reproduces the frozen v1 champion")


if __name__ == "__main__":
    main()
