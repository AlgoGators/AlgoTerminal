"""Research gates. Executable checks that must pass before any claim.

Every false result in this project would have been caught by a machine check,
so the checks are code, not habit.

  Gate 1  causality     recompute a transform from data truncated at t and
                        assert it equals the value used at t. Kills lookahead.
  Gate 2  data artifact scan a panel for scheduled discontinuities (contract
                        rolls), implausible moves, and missing-data ratio.
  Gate 4  trial counter every evaluated configuration is counted, so the
                        multiple-testing correction reads a real number.
  Gate 5  cost ladder   a result must survive twice the measured cost.

Run:            python scripts/gates.py
Prove they bite: python scripts/gates.py --self-test
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

GALLONS = 42.0
RESEARCH_PANEL = ROOT / "engine" / "panel_spot.parquet"      # roll-free
CONTAMINATED_PANEL = ROOT / "engine" / "panel_v2.parquet"    # raw front-month
MEASURED_COST_LOW = 16.2   # bps per side, from the measured cost model
MEASURED_COST_HIGH = 24.0
SURVIVE_COST = 2 * MEASURED_COST_HIGH


def load_dc():
    spec = importlib.util.spec_from_file_location("dc", str(ROOT / "scripts" / "derived_controls_harness.py"))
    dc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dc)
    return dc


# ---------------------------------------------------------------- gate 1

def truncate_and_compare(fn, series: pd.Series, probes: int = 40, warmup: int = 320) -> float:
    """Max |value from truncated history - value from full history| at probes."""
    n = len(series)
    idxs = np.linspace(warmup, n - 1, num=min(probes, max(1, n - warmup)), dtype=int)
    full = fn(series)
    worst = 0.0
    for i in idxs:
        part = fn(series.iloc[: i + 1])
        a, b = full.iloc[i], part.iloc[-1]
        if pd.isna(a) and pd.isna(b):
            continue
        worst = max(worst, abs(float(a) - float(b)))
    return worst


def causality_gate(dc) -> tuple[bool, list[str]]:
    df_f = pd.read_parquet(CONTAMINATED_PANEL).sort_index()
    df_s = pd.read_parquet(RESEARCH_PANEL).sort_index()
    lvl_f = dc.fb.build_levels(df_f)["crack_321"]
    lvl_s = dc.fb.build_levels(df_s)["crack_321"]
    checks = {
        "crack z (roll-free panel)": truncate_and_compare(lambda s: dc.z_factory(s, 90, 8.0), lvl_s),
        "crack z (futures panel)": truncate_and_compare(lambda s: dc.z_factory(s, 90, 8.0), lvl_f),
        "return denominator base_of": truncate_and_compare(lambda s: dc.b4.base_of(s), lvl_s),
    }
    # the H1 storage gate, on the as-published series
    v = pd.read_csv(ROOT / "engine" / "eia" / "raw_wpsr_vintage_gs.csv",
                    parse_dates=["release_date"]).set_index("release_date").sort_index()
    vs = v["gas"] + v["dist"]

    def h1(s: pd.Series) -> pd.Series:
        pz = dc.sm_z(s.diff())
        return (pz >= 1.0).astype(float)

    checks["H1 storage gate"] = truncate_and_compare(h1, vs)

    lines, ok = [], True
    for name, worst in checks.items():
        good = worst < 1e-9
        ok = ok and good
        lines.append(f"    [{'ok' if good else 'FAIL'}] {name}: max |truncated - full| = {worst:.3e}")
    return ok, lines


# ---------------------------------------------------------------- gate 2

def artifact_scan(level: pd.Series) -> list[str]:
    """Scheduled discontinuities, implausible moves, missing-data ratio.

    Moves are measured on the spread-safe basis used everywhere else
    (change over a rolling mean of the absolute level). Using pct_change here
    would flag a spread simply for crossing zero, which is not an artifact.
    """
    out: list[str] = []
    base = level.abs().rolling(20, min_periods=10).mean().shift(1)
    rel = level.diff() / base.replace(0.0, np.nan)
    first = pd.Series(level.index, index=level.index).groupby(
        [level.index.year, level.index.month]).first()
    is_first = pd.Series([d in set(pd.to_datetime(first.values)) for d in level.index],
                         index=level.index)
    ratio = rel[is_first].abs().mean() / rel[~is_first].abs().mean()
    # A construction artifact needs a CONSISTENTLY SIGNED calendar jump, not
    # merely noisy month starts (real seasonality elevates both signs).
    signed_months = []
    for m in range(1, 13):
        vals = rel[is_first & (level.index.month == m)].dropna()
        if len(vals) >= 15 and (np.sign(vals) != 0).sum() >= 15:
            same = max((vals > 0).mean(), (vals < 0).mean())
            if same >= 0.9 and abs(vals.mean()) > 0.02:
                signed_months.append(f"month {m:02d} first session is {same:.0%} one-signed "
                                     f"(mean {vals.mean():+.1%}), {len(vals)} years")
    if signed_months:
        out.append(f"scheduled discontinuity: first-trading-day |move| is {ratio:.2f}x "
                   f"other days, with signed jumps")
        out.extend(signed_months)
    elif ratio > 2.5:
        out.append(f"elevated first-session volatility ({ratio:.2f}x): check for a roll")
    nan_ratio = float(level.isna().mean())
    if nan_ratio > 0.02:
        out.append(f"{nan_ratio:.1%} of sessions missing")
    return out


# ---------------------------------------------------------------- gate 5

def block_t(r: pd.Series) -> float:
    r = pd.Series(r).dropna()
    n = len(r)
    pos = np.arange(n)
    sums = np.array([r[pos // 20 == b].sum() for b in range(pos.max() // 20 + 1)
                     if (pos // 20 == b).sum() == 20])
    if len(sums) < 5:
        return float("nan")
    return float(sums.mean() / (sums.std(ddof=1) / np.sqrt(len(sums))))


def cost_gate(series_csv: Path, base_bps: float = 5.0) -> tuple[bool, list[str]]:
    d = pd.read_csv(series_csv, parse_dates=["date"]).set_index("date")
    turn = d["pos"].diff().abs().fillna(0.0)
    gross = d["ret"] + (base_bps / 10000.0) * turn
    lines = []
    for c in (MEASURED_COST_LOW, MEASURED_COST_HIGH, SURVIVE_COST):
        net = gross - (c / 10000.0) * turn
        t = block_t(net)
        tag = "must survive" if c == SURVIVE_COST else ""
        lines.append(f"    block t at {c:>5.1f} bps/side: {t:+.2f} {tag}")
    ok = block_t(gross - (SURVIVE_COST / 10000.0) * turn) >= 1.0
    return ok, lines


# ---------------------------------------------------------------- self test

def self_test(dc) -> int:
    print("self-test: the gates must bite on known-bad inputs")
    bad = 0

    # causality: a NON-causal transform (uses the whole series mean) must fail
    lvl = dc.fb.build_levels(pd.read_parquet(RESEARCH_PANEL).sort_index())["crack_321"]
    worst_bad = truncate_and_compare(lambda s: s - s.mean(), lvl)
    good = worst_bad > 1e-9
    bad += 0 if good else 1
    print(f"  [{'ok' if good else 'FAIL'}] non-causal transform detected (diff {worst_bad:.3e})")

    # causality: the real transform must pass
    worst_ok = truncate_and_compare(lambda s: dc.z_factory(s, 90, 8.0), lvl)
    good = worst_ok < 1e-9
    bad += 0 if good else 1
    print(f"  [{'ok' if good else 'FAIL'}] causal transform passes (diff {worst_ok:.3e})")

    # artifact: the raw front-month panel must be flagged
    f_lvl = dc.fb.build_levels(pd.read_parquet(CONTAMINATED_PANEL).sort_index())["crack_321"]
    f_find = artifact_scan(f_lvl)
    good = len(f_find) > 0
    bad += 0 if good else 1
    print(f"  [{'ok' if good else 'FAIL'}] contaminated panel flagged ({len(f_find)} findings)")

    # artifact: the roll-free panel must pass
    s_lvl = dc.fb.build_levels(pd.read_parquet(RESEARCH_PANEL).sort_index())["crack_321"]
    s_find = artifact_scan(s_lvl)
    good = len(s_find) == 0
    bad += 0 if good else 1
    print(f"  [{'ok' if good else 'FAIL'}] roll-free panel clean ({len(s_find)} findings)")

    print("self-test " + ("PASSED" if bad == 0 else f"FAILED ({bad})"))
    return bad


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    dc = load_dc()

    if args.self_test:
        return 1 if self_test(dc) else 0

    import trials

    print("Gate 1 causality")
    ok_c, lines = causality_gate(dc)
    print("\n".join(lines))
    print(f"  -> {'PASS' if ok_c else 'FAIL'}")

    print("\nGate 2 data artifact")
    import pandas as pd  # noqa: F811
    s_lvl = dc.fb.build_levels(pd.read_parquet(RESEARCH_PANEL).sort_index())["crack_321"]
    f_lvl = dc.fb.build_levels(pd.read_parquet(CONTAMINATED_PANEL).sort_index())["crack_321"]
    s_find, f_find = artifact_scan(s_lvl), artifact_scan(f_lvl)
    for m in s_find:
        print(f"    [FAIL] research panel: {m}")
    if not s_find:
        print("    [ok] research panel (roll-free) clean")
    for m in f_find:
        print(f"    [warn] futures panel (known contaminated): {m}")
    ok_a = not s_find
    print(f"  -> {'PASS' if ok_a else 'FAIL'}")

    print("\nGate 4 trial counter")
    n = trials.count()
    print(f"    configurations evaluated so far: {n}")
    print("    every new evaluation must call trials.bump()")

    print("\nGate 5 cost ladder (must survive twice measured cost)")
    primary = ROOT / "results" / "wf_crush_spot_series.csv"
    if primary.exists():
        ok_k, lines = cost_gate(primary)
        print("\n".join(lines))
        print(f"  -> {'PASS' if ok_k else 'FAIL'} (edge does not survive double cost)"
              if not ok_k else "  -> PASS")
    else:
        ok_k = False
        print(f"    [FAIL] missing {primary.name}; run walkforward_causal.py first")

    hard = ok_c and ok_a
    print(f"\nhard gates: {'PASS' if hard else 'FAIL'}"
          f"   advisory cost gate: {'PASS' if ok_k else 'FAIL'}")
    return 0 if hard else 1


if __name__ == "__main__":
    raise SystemExit(main())
