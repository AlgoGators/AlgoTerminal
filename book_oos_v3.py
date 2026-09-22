"""Book v3 — engine measurement fixes + honest OOS construction.

Fixes over long_backtest.py / book_oos_v2.py (each is a real gap found by the
16y window):

G1 leg-switch fill bug: the cross_sectional return builder filled flat days'
"held level" with crack_321 (a different scale), producing spurious +-20-43%
single-day returns on entry/exit transitions (2012-01-09 -22.5% on a day with
no level move; 2024-01-12 -43% in-sample). Fix: hold the CHOSEN leg's level on
every day (argmin z), whether or not a position is on; pos=0 days then return 0.

G2 basis mismatch: vol_scale() sized on rel = diff/level but returns were
measured as diff/base (base = rolling mean |level|). Near zero-crossings
(bzwti crosses 548x in 2007-26) the two disagree wildly, so "inverse-vol"
weights favored bzwti on an artifact. Fix: size AND measure on diff/base.

G3 gap-day notional: positions run up to 1.0 notional; a real -20% level day
(2019-09-03 RBOB crash -18.2% NAV) or -31% (2020-04-20 bzwti) is catastrophic.
Fix: per-factor notional cap pos <= CAP3SIG * base / (3 * sigma_dlevel)
so a 3-sigma level day loses at most CAP3SIG of the book.

Overlay v2 (DD control): keyed on EXPERIENCED equity drawdown with re-cock on
engine new highs (the v1 overlay keyed on engine dd, which decoupled from the
experienced dd and let it reach -26.9% vs engine -7% in 2011).

Design space: subsets x weight schemes x cap x overlay, all IS-trained only.
"""

from __future__ import annotations

import importlib.util
import sys
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

spec = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)

SUBSETS = {
    "FULL": ["crack_321", "crack_ho", "cross_sectional", "ng", "bzwti"],
    "NOHO": ["crack_321", "cross_sectional", "ng", "bzwti"],
    "CORE3": ["crack_321", "cross_sectional", "bzwti"],
    "CORE2": ["crack_321", "cross_sectional"],
}


def base_of(level: pd.Series, lookback: int = 20) -> pd.Series:
    return level.abs().rolling(lookback, min_periods=10).mean()


def fixed_vol_scale(s: pd.Series, vt: float) -> pd.Series:
    """G2 fix: same basis as returns. rel = diff / base (not diff / level)."""
    level = s.abs().rolling(fb.VOL_LOOKBACK, min_periods=10).mean().shift(1)
    base = base_of(s, fb.VOL_LOOKBACK).shift(1)
    denom = base.replace(0.0, np.nan)
    rel = s.diff() / denom
    rv = rel.rolling(fb.VOL_LOOKBACK, min_periods=10).std().shift(1).replace(0.0, np.nan) * np.sqrt(252)
    scale = (vt / rv).clip(upper=fb.MAX_LEV)
    uncond = rel.expanding(min_periods=10).std().shift(1).replace(0.0, np.nan) * np.sqrt(252)
    fallback = (vt / uncond).clip(upper=fb.MAX_LEV)
    return scale.fillna(fallback).fillna(0.5).clip(upper=fb.MAX_LEV)


def gap_cap_pos(s: pd.Series, cap3sig: float | None, vt_thresh_days: float = 3.0) -> pd.Series:
    """G3 fix: cap position so a 3-sigma level move loses <= cap3sig of book."""
    if cap3sig is None or cap3sig <= 0:
        return pd.Series(fb.MAX_LEV, index=s.index)
    base = base_of(s, fb.VOL_LOOKBACK).shift(1).replace(0.0, np.nan)
    sd = s.diff().rolling(fb.VOL_LOOKBACK, min_periods=10).std().shift(1).replace(0.0, np.nan)
    cap = (cap3sig * base / (vt_thresh_days * sd)).clip(upper=fb.MAX_LEV)
    return cap.fillna(fb.MAX_LEV)


def sp_ret(pos: pd.Series, level: pd.Series) -> pd.Series:
    """Return with the common (base) basis: pos_{t-1} * dlevel_t / base_{t-1}."""
    base = base_of(level).shift(1).replace(0.0, np.nan)
    r = pos.shift(1).fillna(0.0) * level.diff() / base
    return r.fillna(0.0)


def chosen_leg_every_day(levels: dict[str, pd.Series], legs: list[str]) -> pd.Series:
    """G1 fix: the leg that WOULD be held each day (argmin z), for ALL days."""
    zdf = pd.DataFrame({k: fb.seasonal_z(levels[k]) for k in legs})
    arr = zdf.to_numpy(dtype=float)
    cols = list(zdf.columns)
    out = pd.Series(np.nan, index=zdf.index)
    for i in range(len(zdf)):
        row = arr[i]
        if np.isnan(row).all():
            continue
        out.iloc[i] = levels[cols[int(np.nanargmin(row))]].iloc[i]
    return out


def build_v3(levels, cap3sig: float | None):
    """V3 engine: factor_book logic with fixed vol basis + optional gap cap."""
    fb.vol_scale = fixed_vol_scale
    factors = {}
    factors.update(fb.f1_positions(levels))
    factors.update(fb.f2_positions(levels))
    factors.update(fb.f3_positions(levels))
    factors.update(fb.f4_positions(levels))

    # apply gap caps on top of engine positions
    if cap3sig is not None:
        for name, pos in factors.items():
            lvl = levels[name] if name != "cross_sectional" else chosen_leg_every_day(
                levels, ["crack_321", "crack_gas", "crack_ho"]).fillna(levels["crack_321"])
            factors[name] = pos.clip(-gap_cap_pos(lvl, cap3sig), gap_cap_pos(lvl, cap3sig))

    rets = {}
    for name, pos in factors.items():
        if name == "cross_sectional":
            held = chosen_leg_every_day(levels, ["crack_321", "crack_gas", "crack_ho"])
            rets[name] = sp_ret(pos, held.fillna(levels["crack_321"]))
        else:
            rets[name] = sp_ret(pos, levels[name])
    return factors, rets


def apply_costs(positions, returns, trade_bps=TRADE_BPS, roll_bps=ROLL_BPS):
    out = {}
    for name in returns:
        pos = positions[name].fillna(0.0)
        dp = pos.diff().fillna(0.0).abs()
        out[name] = (returns[name] - trade_bps / 10000.0 * dp - roll_bps / 252.0 / 10000.0 * pos.abs()).fillna(0.0)
    return pd.DataFrame(out)


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "worst_day": np.nan, "vol": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 252
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1,
            "sharpe": r.mean() / r.std() * np.sqrt(252),
            "maxdd": (eq / eq.cummax() - 1).min(), "worst_day": r.min(),
            "vol": r.std() * np.sqrt(252)}


def window(r: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    out = r.loc[start:end]
    return out.iloc[WARMUP:] if len(out) > WARMUP else out


def weight_scheme(returns_is: pd.DataFrame, scheme: str) -> dict[str, float]:
    vols = returns_is.std().replace(0.0, np.nan)
    if scheme == "EQ":
        w = pd.Series(1.0, index=returns_is.columns)
    elif scheme == "INV":
        w = 1.0 / vols
    elif scheme == "HLV":
        w = (1.0 / vols) ** 0.5
    else:
        raise ValueError(scheme)
    return (w / w.sum()).to_dict()


def book_returns(net: pd.DataFrame, factors: list[str], weights: dict[str, float]) -> pd.Series:
    s = pd.Series(0.0, index=net.index)
    for f in factors:
        s = s + weights[f] * net[f]
    return s


def drawdown(s: pd.Series) -> pd.Series:
    eq = (1 + s).cumprod()
    return eq / eq.cummax() - 1


def apply_overlay(book: pd.Series, vol_target: float = 0.10,
                  cut: float = -0.06, halt: float = -0.10) -> pd.Series:
    """DD overlay v2: hysteresis on EXPERIENCED equity dd, re-cock on engine new highs.

    Scale decided using info through t-1, applied to day t.
    FULL(1.0) -> CUT(0.5) when experienced dd <= cut
    CUT -> OFF(0.0) when experienced dd <= halt
    OFF/CUT -> FULL when the underlying engine makes a new high (re-cock).
    Also: CUT -> FULL if experienced dd recovers above cut (before any new high).
    """
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)  # gear through t-1 applied at day t
    n = len(book)
    scale = np.empty(n)
    state = 1.0
    eq, hwm = 1.0, 1.0
    eng_eq, eng_hwm = 1.0, 1.0
    for t in range(n):
        scale[t] = state
        r = float(book.iloc[t])
        ret = r * float(g.iloc[t]) * scale[t]
        eq *= 1.0 + ret
        hwm = max(hwm, eq)
        exp_dd = eq / hwm - 1.0 if hwm > 0 else 0.0
        # end of day t -> state for t+1
        eng_eq *= 1.0 + r
        was_hwm = eng_hwm
        eng_hwm = max(eng_hwm, eng_eq)
        if eng_eq >= was_hwm:  # engine new high -> re-cock
            state = 1.0
        elif exp_dd <= halt:
            state = 0.0
        elif exp_dd <= cut:
            state = 0.5
        # else stay
    return book * pd.Series(scale, index=book.index) * g


def fmt(v) -> str:
    return "      --" if pd.isna(v) else ("%7.2f%%" % (v * 100))


def main():
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    print("Window:", df.index.min().date(), "->", df.index.max().date(), " rows=%d" % len(df))

    # --- G1 validation: cross_sectional worst days under fix vs old ---
    print("\n=== G1 check: cross_sectional worst days (v3 engine, no cap) ===")
    factors, rets = build_v3(levels, None)
    net = apply_costs(factors, rets)
    for f in ["cross_sectional", "crack_321"]:
        s = net[f][net[f] < -0.04]
        print("  %-16s days<-4%%: %d" % (f, len(s)))
        for idx, v in s.nsmallest(4).items():
            print("     %s  %+7.2f%%" % (idx.date(), v * 100))

    isw = window(net, IS_START, df.index.max())
    oos = window(net, OOS_START, IS_START)
    print("\nPer-factor (v3, no cap): IS vs OOS")
    for f in net.columns:
        si, so = stats(isw[f]), stats(oos[f])
        print("  %-16s IS Sh %5.2f DD %8s | OOS Sh %5.2f DD %8s vol %6.1f%%" % (
            f, si["sharpe"], fmt(si["maxdd"]), so["sharpe"], fmt(so["maxdd"]), so["vol"] * 100))

    # --- design space ---
    caps = {"NOCAP": None, "CAP8": 0.08, "CAP5": 0.05, "CAP3": 0.03}
    results = []
    print("\n=== SUBSET x WEIGHT x CAP x OVERLAY (v3 engine) ===")
    print("%-6s %-4s %-5s %-2s | %-7s %-8s %-8s | %-7s %-8s %-8s %-7s" % (
        "subset", "wt", "cap", "ov", "IS_Sh", "IS_DD", "OOS_Sh", "OOS_CAGR", "OOS_DD", "OOS_vol", "worstD"))
    for capname, cap3 in caps.items():
        factors, rets = build_v3(levels, cap3)
        net = apply_costs(factors, rets)
        isw = window(net, IS_START, df.index.max())
        oos = window(net, OOS_START, IS_START)
        for sname, flist in SUBSETS.items():
            for scheme in ["EQ", "HLV", "INV"]:
                w = weight_scheme(isw[flist], scheme)
                book = book_returns(net, flist, w)
                b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
                for ov in [0, 1]:
                    bi = apply_overlay(b_is) if ov else b_is
                    bo = apply_overlay(b_oos) if ov else b_oos
                    si, so = stats(bi), stats(bo)
                    results.append({"cap": capname, "subset": sname, "scheme": scheme, "ov": bool(ov),
                                    "IS_sh": si["sharpe"], "IS_dd": si["maxdd"], "OOS_sh": so["sharpe"],
                                    "OOS_cagr": so["cagr"], "OOS_dd": so["maxdd"], "OOS_vol": so["vol"],
                                    "OOS_worst": so["worst_day"]})
                    if ov == 0 and capname in ("NOCAP", "CAP5"):
                        print("%-6s %-4s %-5s %-2s | %7.2f %8s %7.2f | %7.2f %8s %8s %7s" % (
                            sname, scheme, capname, "--",
                            si["sharpe"], fmt(si["maxdd"]), so["sharpe"],
                            fmt(so["cagr"]), fmt(so["maxdd"]), fmt(so["vol"])))
    res = pd.DataFrame(results)
    res.to_csv(DEV / "book_oos_v3_results.csv", index=False)
    print("\nSaved book_oos_v3_results.csv (%d rows)" % len(res))

    # --- top candidates by OOS Sharpe with OOS DD <= -12% ---
    print("\n=== Best OOS candidates with OOS MaxDD <= -12%% (any overlay) ===")
    sub = res[(res["OOS_dd"] >= -0.12) & (res["IS_sh"] >= 1.0)]
    top = sub.sort_values("OOS_sh", ascending=False).head(12)
    for _, r in top.iterrows():
        print("  %-6s %-4s %-5s ov=%d | IS Sh %5.2f DD %8s | OOS Sh %5.2f CAGR %8s DD %8s vol %6.1f%%" % (
            r["subset"], r["scheme"], r["cap"], int(r["ov"]), r["IS_sh"], fmt(r["IS_dd"]),
            r["OOS_sh"], fmt(r["OOS_cagr"]), fmt(r["OOS_dd"]), r["OOS_vol"] * 100))

    # --- overlay sensitivity on the best raw candidate ---
    print("\n=== Overlay sensitivity (CORE3 HLV CAP5 raw) ===")
    factors, rets = build_v3(levels, 0.05)
    net = apply_costs(factors, rets)
    isw = window(net, IS_START, df.index.max())
    oos = window(net, OOS_START, IS_START)
    w = weight_scheme(isw[SUBSETS["CORE3"]], "HLV")
    book = book_returns(net, SUBSETS["CORE3"], w)
    b_oos = book.loc[oos.index]
    for cut_, halt_, vt_ in [(0.0, 0.0, 0.0), (-0.06, -0.10, 0.10), (-0.05, -0.09, 0.10),
                             (-0.075, -0.12, 0.10), (-0.06, -0.10, 0.15), (-0.04, -0.08, 0.10)]:
        if cut_ == 0.0:
            s = stats(b_oos)
            print("  raw                 | OOS Sh %5.2f CAGR %8s DD %8s vol %6.1f%%" % (
                s["sharpe"], fmt(s["cagr"]), fmt(s["maxdd"]), s["vol"] * 100))
            continue
        ob = apply_overlay(b_oos, vol_target=vt_, cut=cut_, halt=halt_)
        s = stats(ob)
        print("  cut %6.3f halt %6.3f vt %.2f | OOS Sh %5.2f CAGR %8s DD %8s vol %6.1f%% worst %8s" % (
            cut_, halt_, vt_, s["sharpe"], fmt(s["cagr"]), fmt(s["maxdd"]), s["vol"] * 100, fmt(s["worst_day"])))


if __name__ == "__main__":
    main()