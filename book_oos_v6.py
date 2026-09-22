"""Book v6 — reversal-speed discriminator overlay (Round 8).

Pre-registered hypothesis (stated BEFORE measuring engine result):

The windfall/bleed split is SPEED not LEVEL. A V-shaped crash — the
held crush leg deepening FAST (>= THR_CRASH z in 5 days) INTO deep
territory (depth <= THR_DEPTH) — precedes the crisis-reversion payoff.
A grind (deep but not deepening, crash5 ~ 0) precedes the slow bleed.
Forcing FULL participation during the V-state should capture the windfall
without paying the grind bleed that killed v3 (depth alone) and CLGATE
(crude level alone).

Pre-registered primary thresholds (round numbers, a priori):
  THR_CRASH = 1.0 z, THR_DEPTH = -1.25  (also tested -1.5 as secondary)
The diagnostic bucket pass in diag_reversal2.py established these as the
informative region but was not used to pick the overlay optimum — the
engine grid below reports both.

Rule: same v2 ladder except the V-state forces FULL (overrides DD) at
the open of day t when the causal V signal at close t-1 is true. All
causal: V(t) uses depth.shift(1) and crash5 = depth.shift(6)-depth.shift(1).
Net is 5bps/20roll, EQ book, CORE3.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = (Path("/tmp/panel_adj_2007_2026.parquet")
         if Path("/tmp/panel_adj_2007_2026.parquet").exists()
         else Path(__file__).resolve().parent / "panel_v2.parquet")
IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90
TRADE_BPS = 5.0
ROLL_BPS = 20.0

spec = importlib.util.spec_from_file_location("b5", str(DEV / "book_oos_v5.py"))
b5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b5)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)

SUBSETS = {"CORE3": ["crack_321", "cross_sectional", "bzwti"]}


def v_signal(depth: pd.Series, thr_crash: float = 1.0, thr_depth: float = -1.25) -> pd.Series:
    """Causal V-state at close t: depth.shift(1) and crash5 known at t."""
    held = depth.shift(1)
    crash5 = depth.shift(6) - depth.shift(1)
    return (crash5 >= thr_crash) & (held <= thr_depth)


def apply_overlay_v4(
    book: pd.Series,
    vstate: pd.Series,
    vol_target: float = 0.10,
    cut: float = -0.06,
    halt: float = -0.10,
) -> pd.Series:
    """v2 ladder with V-state forcing FULL (overrides DD)."""
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
    n = len(book)
    scale = np.empty(n)
    state = 1.0
    eq, hwm = 1.0, 1.0
    eng_eq, eng_hwm = 1.0, 1.0
    vv = vstate.reindex(book.index).fillna(False).to_numpy(dtype=bool)
    for t in range(n):
        scale[t] = state
        r = float(book.iloc[t])
        ret = r * float(g.iloc[t]) * scale[t]
        eq *= 1.0 + ret
        hwm = max(hwm, eq)
        exp_dd = eq / hwm - 1.0 if hwm > 0 else 0.0
        eng_eq *= 1.0 + r
        was_hwm = eng_hwm
        eng_hwm = max(eng_hwm, eng_eq)
        new_high = eng_eq >= was_hwm
        if vv[t]:
            state = 1.0
        elif state == 1.0:
            if exp_dd <= halt:
                state = 0.0
            elif exp_dd <= cut:
                state = 0.5
        elif state == 0.5:
            if exp_dd <= halt:
                state = 0.0
            elif new_high:
                state = 1.0
        else:
            if new_high:
                state = 1.0
    return book * pd.Series(scale, index=book.index) * g


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "worst_day": np.nan, "vol": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 252
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1, "sharpe": r.mean() / r.std() * np.sqrt(252),
            "maxdd": (eq / eq.cummax() - 1).min(), "worst_day": r.min(), "vol": r.std() * np.sqrt(252)}


def window(r: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    out = r.loc[start:end]
    return out.iloc[WARMUP:] if len(out) > WARMUP else out


def main():
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    levels["__df__"] = df

    # depth (most-crushed held leg z)
    import tempfile
    factors, rets, turn, legpos = b5.build_v5(levels, None, False)
    net = b5.apply_costs(factors, rets, turnover=turn)
    isw = window(net, IS_START, df.index.max())
    oos = window(net, OOS_START, IS_START)

    zdf = {}
    for leg in ["crack_321", "crack_gas", "crack_ho", "ng", "bzwti"]:
        zdf[leg] = fb.seasonal_z(levels[leg])
    for leg in ["brent321", "brent_gas", "brent_ho"]:
        zdf[leg] = fb.seasonal_z(b5.brent_levels(df)[leg])
    depth = b5.book_depth(legpos, zdf, net.index)

    w = b5.weight_scheme(isw[SUBSETS["CORE3"]], "EQ")
    book = b5.book_returns(net, SUBSETS["CORE3"], w)
    b_is, b_oos = book.loc[isw.index], book.loc[oos.index]

    print("Window:", df.index.min().date(), "->", df.index.max().date(), " rows=%d" % len(df))
    print("CORE3 EQ raw: IS Sh %.2f DD %+.1f%% | OOS Sh %.2f DD %+.1f%% CAGR %.2f%% vol %.1f%%" % (
        stats(b_is)["sharpe"], stats(b_is)["maxdd"] * 100,
        stats(b_oos)["sharpe"], stats(b_oos)["maxdd"] * 100,
        stats(b_oos)["cagr"] * 100, stats(b_oos)["vol"] * 100))

    # baselines
    for label, fn in [("V2", lambda s: b5.apply_overlay_v2(s)),
                      ("CLGATE", lambda s: __import__("gate_test_overlay", fromlist=["x"]) if False else None)]:
        pass

    # v2 champ
    v2_is = b5.apply_overlay_v2(b_is)
    v2_oos = b5.apply_overlay_v2(b_oos)
    print("V2 champ:  IS Sh %.2f DD %+.1f%% | OOS Sh %.2f DD %+.1f%% CAGR %.2f%% vol %.1f%% worst %+.2f%%" % (
        stats(v2_is)["sharpe"], stats(v2_is)["maxdd"] * 100,
        stats(v2_oos)["sharpe"], stats(v2_oos)["maxdd"] * 100,
        stats(v2_oos)["cagr"] * 100, stats(v2_oos)["vol"] * 100, stats(v2_oos)["worst_day"] * 100))

    # raw overlay gate (CL z <= -1.5) for comparison — inline
    clz = fb.seasonal_z(df.CL)

    def overlay_gate(book_, gate):
        rv = book_.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
        gear = (0.10 / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
        g = gear.shift(1).fillna(1.0)
        n = len(book_)
        scale = np.empty(n)
        state = 1.0
        eq, hwm = 1.0, 1.0
        eng_eq, eng_hwm = 1.0, 1.0
        gv = gate.reindex(book_.index).to_numpy(dtype=float)
        for t in range(n):
            scale[t] = state
            r = float(book_.iloc[t])
            ret = r * float(g.iloc[t]) * scale[t]
            eq *= 1.0 + ret
            hwm = max(hwm, eq)
            exp_dd = eq / hwm - 1.0 if hwm > 0 else 0.0
            eng_eq *= 1.0 + r
            was_hwm = eng_hwm
            eng_hwm = max(eng_hwm, eng_eq)
            new_high = eng_eq >= was_hwm
            if not np.isnan(gv[t]) and gv[t] <= -1.5:
                state = 1.0
            elif state == 1.0:
                if exp_dd <= -0.10:
                    state = 0.0
                elif exp_dd <= -0.06:
                    state = 0.5
            elif state == 0.5:
                if exp_dd <= -0.10:
                    state = 0.0
                elif new_high:
                    state = 1.0
            else:
                if new_high:
                    state = 1.0
        return book_ * pd.Series(scale, index=book_.index) * g

    cg_is = overlay_gate(b_is, clz.loc[b_is.index])
    cg_oos = overlay_gate(b_oos, clz.loc[b_oos.index])
    print("CLGATE:    IS Sh %.2f DD %+.1f%% | OOS Sh %.2f DD %+.1f%% CAGR %.2f%% vol %.1f%% worst %+.2f%%" % (
        stats(cg_is)["sharpe"], stats(cg_is)["maxdd"] * 100,
        stats(cg_oos)["sharpe"], stats(cg_oos)["maxdd"] * 100,
        stats(cg_oos)["cagr"] * 100, stats(cg_oos)["vol"] * 100, stats(cg_oos)["worst_day"] * 100))

    print("\n=== V4 grid (crash-speed discriminator) ===")
    print("  %-18s | %6s %8s | %6s %8s %8s %8s %6s | %6s" % (
        "variant", "IS_Sh", "IS_DD", "OOS_Sh", "OOS_CAGR", "OOS_DD", "OOS_vol", "OOS_worst", "top5"))
    for tc, td in [(1.0, -1.25), (1.0, -1.5), (0.8, -1.25), (1.2, -1.5)]:
        v = v_signal(depth, tc, td)
        vi = apply_overlay_v4(b_is, v.loc[b_is.index])
        vo = apply_overlay_v4(b_oos, v.loc[b_oos.index])
        si, so = stats(vi), stats(vo)
        top5_raw = b_oos.nlargest(5).sum()
        top5_vo = vo.loc[b_oos.nlargest(5).index].sum()
        print("  V>=%.1f d<=%.2f | %6.2f %8.1f%% | %6.2f %8.2f%% %8.1f%% %8.1f%% %6.2f%% | %5.1f%%" % (
            tc, td, si["sharpe"], si["maxdd"] * 100,
            so["sharpe"], so["cagr"] * 100, so["maxdd"] * 100, so["vol"] * 100,
            so["worst_day"] * 100, top5_vo / top5_raw * 100 if top5_raw else 0))

    # best variant yearly + worst days
    tc, td = 1.0, -1.25
    v = v_signal(depth, tc, td)
    vo = apply_overlay_v4(b_oos, v.loc[b_oos.index])
    vi = apply_overlay_v4(b_is, v.loc[b_is.index])
    print("\n=== V4 (1.0/-1.25) yearly OOS: raw | V2 | V4 | CLGATE ===")
    raw_y = b_oos.groupby(b_oos.index.year).sum()
    v2_y = v2_oos.groupby(v2_oos.index.year).sum()
    v4_y = vo.groupby(vo.index.year).sum()
    cg_y = cg_oos.groupby(cg_oos.index.year).sum()
    for y in sorted(set(b_oos.index.year)):
        print("  %4d  %+6.1f%%  %+6.1f%%  %+6.1f%%  %+6.1f%%" % (
            y, raw_y.loc[y] * 100, v2_y.loc[y] * 100, v4_y.loc[y] * 100, cg_y.loc[y] * 100))

    print("\n=== V4 worst days OOS ===")
    for idx, val in vo.nsmallest(5).items():
        print("  %-12s %+6.2f%%  raw %+6.2f%%  V2 %+6.2f%%" % (
            idx.date(), val * 100, b_oos.loc[idx] * 100, v2_oos.loc[idx] * 100))

    # negative control: shuffle V labels, re-run V4
    print("\n=== negative control: shuffle V labels (15 draws) OOS Sharpe ===")
    rng = np.random.default_rng(7)
    sh = []
    v_oos_bool = v.loc[b_oos.index].to_numpy(dtype=bool)
    for _ in range(15):
        perm = rng.permutation(len(v_oos_bool))
        sh_v = pd.Series(v_oos_bool[perm], index=b_oos.index)
        sh.append(stats(apply_overlay_v4(b_oos, sh_v))["sharpe"])
    print("  shuffled V4 OOS Sharpe: mean %.2f sd %.2f (real V4 %.2f, V2 %.2f, raw %.2f)" % (
        np.mean(sh), np.std(sh), stats(vo)["sharpe"], stats(v2_oos)["sharpe"], stats(b_oos)["sharpe"]))

    # persist
    pd.DataFrame({"date": b_oos.index, "raw": b_oos, "v2": v2_oos, "v4": vo, "clgate": cg_oos}).to_csv(
        DEV / "book_oos_v6_results.csv", index=False)
    print("\nSaved book_oos_v6_results.csv")

if __name__ == "__main__":
    main()
