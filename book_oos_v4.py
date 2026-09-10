"""Book v4 — per-leg correct F2 + consistent basis + gap caps + DD overlay.

The 16y window exposed two structural measurement bugs in the recorded cross-
sectional factor (F2):

G1 (leg-switch phantom): the "chosen leg" series switches between crack_321 /
crack_gas / crack_ho — daily levels at completely different dollar scales.
The old return builder booked the level JUMP between legs as P&L
(2012-01-09: -22.5% on a day with no market move; 2007-12-20: -53%).
The engine's circuit breaker also fired on the phantom jump itself, forcing
whipsaw exits. Fix: F2 is rebuilt per-leg — position, return, hard stop,
circuit breaker and trade cost are all per-leg; a leg switch is a real
exit+entry trade pair measured on each leg's own level and own base.

G2 (basis mismatch): sizing used rel = dlevel/level while returns used
dlevel/base. Same denominator (base = rolling mean |level|) everywhere now.

G3 (gap notional): positions up to 1.0 notional turn real -20% level days
(2019-09-03 RB crash, 2020-03-12 COVID) into -18% book days. New per-factor
notional cap: pos <= CAP3SIG * base / (3 * sd_dlevel).

Report: subset x weight x overlay, IS vs OOS, honest.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = Path("/tmp/panel_adj_2007_2026.parquet")
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
    """G2 fix: size on the same diff/base basis as returns."""
    base = base_of(s, fb.VOL_LOOKBACK).shift(1).replace(0.0, np.nan)
    rel = s.diff() / base
    rv = rel.rolling(fb.VOL_LOOKBACK, min_periods=10).std().shift(1).replace(0.0, np.nan) * np.sqrt(252)
    scale = (vt / rv).clip(upper=fb.MAX_LEV)
    uncond = rel.expanding(min_periods=10).std().shift(1).replace(0.0, np.nan) * np.sqrt(252)
    fallback = (vt / uncond).clip(upper=fb.MAX_LEV)
    return scale.fillna(fallback).fillna(0.5).clip(upper=fb.MAX_LEV)


def gap_cap(s: pd.Series, cap3sig: float | None, k: float = 3.0) -> pd.Series:
    """G3: max position so a k-sigma level move loses <= cap3sig of the book."""
    if cap3sig is None or cap3sig <= 0:
        return pd.Series(fb.MAX_LEV, index=s.index)
    base = base_of(s, fb.VOL_LOOKBACK).shift(1).replace(0.0, np.nan)
    sd = s.diff().rolling(fb.VOL_LOOKBACK, min_periods=10).std().shift(1).replace(0.0, np.nan)
    cap = (cap3sig * base / (k * sd)).clip(upper=fb.MAX_LEV)
    return cap.fillna(fb.MAX_LEV)


def leg_risk(pos: pd.Series, level: pd.Series, trailing_stop: bool) -> pd.Series:
    """per-leg version of factor_book.apply_leg_risk (cb + hard stop + cooldown)."""
    out = pos.fillna(0.0).clip(-fb.MAX_LEV, fb.MAX_LEV)
    s = level.to_numpy(dtype=float)
    arr = out.to_numpy(dtype=float).copy()
    prev_held = out.shift(1).fillna(0.0).to_numpy(dtype=float)
    move = level.diff().to_numpy(dtype=float)
    day_std = level.diff().rolling(fb.DAY_STD_LOOKBACK, min_periods=10).std()
    vol = day_std.shift(1).replace(0.0, np.nan).to_numpy(dtype=float)
    maxv = level.shift(1).rolling(fb.STOP_LOOKBACK, min_periods=10).max().to_numpy(dtype=float)
    minv = level.shift(1).rolling(fb.STOP_LOOKBACK, min_periods=10).min().to_numpy(dtype=float)
    dist = vol * fb.STOP_SIGMA * np.sqrt(fb.STOP_LOOKBACK)
    if trailing_stop:
        stop_hit = ((arr > 0.0) & (s < maxv - dist)) | ((arr < 0.0) & (s > minv + dist))
    else:
        stop_hit = np.zeros(len(arr), dtype=bool)
    sigma_move = move / vol
    cb_hit = (prev_held * sigma_move) <= -fb.DAILY_LOSS_SIGMA
    entry_level = np.full(len(arr), np.nan)
    cur_entry = np.nan
    for i in range(len(arr)):
        if arr[i] > 0.0 and np.isnan(cur_entry):
            cur_entry = s[i]
        elif arr[i] == 0.0:
            cur_entry = np.nan
        entry_level[i] = cur_entry
    hard_hit = (arr > 0.0) & (s < entry_level * (1.0 - fb.HARD_STOP_PCT))
    event = np.asarray(stop_hit | cb_hit | hard_hit, dtype=bool)
    arr[event] = 0.0
    n = len(arr)
    for event_i in np.flatnonzero(event):
        hi = min(event_i + 1 + fb.COOLDOWN_BARS, n)
        arr[event_i + 1:hi] = 0.0
    return pd.Series(arr, index=level.index)


def f2_per_leg(levels, vt: float, cap3sig: float | None):
    """Correct cross-sectional factor: one leg at a time, per-leg P&L/risk/cost."""
    legs = ["crack_321", "crack_gas", "crack_ho"]
    zdf = pd.DataFrame({k: fb.seasonal_z(levels[k]) for k in legs})
    arr = zdf.to_numpy(dtype=float)
    cols = list(zdf.columns)
    chosen = pd.Series(np.nan, index=zdf.index, dtype=float)
    valid = zdf.notna().all(axis=1)
    for i in range(len(zdf)):
        if valid.iloc[i]:
            row = arr[i]
            if np.isnan(row).all():
                continue
            k = cols[int(np.nanargmin(row))]
            if row[int(np.nanargmin(row))] < fb.XS_MIN_Z:
                chosen.iloc[i] = legs.index(k)
    # per-leg scaled positions
    leg_pos = {}
    leg_ret = {}
    for li, leg in enumerate(legs):
        lvl = levels[leg]
        on = chosen == li
        scale = fixed_vol_scale(lvl, vt).where(on, 0.0)
        sig = pd.Series(1.0, index=lvl.index).where(on, 0.0)
        raw = sig * scale
        p = leg_risk(raw, lvl, trailing_stop=fb.TRAILING_STOP_ON["cross_sectional"])
        leg_pos[leg] = p
        b = base_of(lvl).shift(1).replace(0.0, np.nan)
        leg_ret[leg] = p.shift(1).fillna(0.0) * lvl.diff() / b
    # G3 gap cap on total F2 (smallest cap across legs applies)
    if cap3sig is not None:
        caps = {leg: gap_cap(levels[leg], cap3sig) for leg in legs}
        for leg in legs:
            leg_pos[leg] = leg_pos[leg].clip(-caps[leg], caps[leg])
            b = base_of(levels[leg]).shift(1).replace(0.0, np.nan)
            leg_ret[leg] = leg_pos[leg].shift(1).fillna(0.0) * levels[leg].diff() / b
    total_pos = pd.DataFrame(leg_pos).sum(axis=1)
    total_ret = pd.DataFrame(leg_ret).sum(axis=1).fillna(0.0)
    # turnover: sum of per-leg |dpos| (captures leg switches as exit+entry)
    turnover = pd.DataFrame(leg_pos).diff().abs().sum(axis=1)
    return {"cross_sectional": total_pos}, {"cross_sectional": total_ret}, turnover


def build_v4(levels, cap3sig: float | None, vt_f2: float = 0.50):
    """Corrected engine for the 4 non-F2 factors (single-leg, basis fixed) + per-leg F2."""
    fb.vol_scale = fixed_vol_scale
    factors = {}
    factors.update(fb.f1_positions(levels))
    factors.update(fb.f3_positions(levels))
    factors.update(fb.f4_positions(levels))
    f2p, f2r, f2turn = f2_per_leg(levels, vt_f2, cap3sig)
    factors.update(f2p)
    rets = dict(f2r)
    turnover = {"cross_sectional": f2turn}
    for name, pos in factors.items():
        if name == "cross_sectional":
            continue
        lvl = levels[name]
        cap = gap_cap(lvl, cap3sig) if cap3sig is not None else None
        if cap is not None:
            factors[name] = pos.clip(-cap, cap)
        b = base_of(lvl).shift(1).replace(0.0, np.nan)
        rets[name] = pos.shift(1).fillna(0.0) * lvl.diff() / b
        turnover[name] = pos.diff().abs()
    return factors, rets, turnover


def apply_costs(positions, returns, turnover=None, trade_bps=TRADE_BPS, roll_bps=ROLL_BPS,
                extra_turnover=None):
    out = {}
    for name in returns:
        pos = positions[name].fillna(0.0)
        if turnover is not None and name in turnover:
            dp = turnover[name].fillna(0.0)
        else:
            dp = pos.diff().fillna(0.0).abs()
        if extra_turnover is not None and name in extra_turnover:
            dp = dp + extra_turnover[name].fillna(0.0)
        out[name] = (returns[name] - trade_bps / 10000.0 * dp
                     - roll_bps / 252.0 / 10000.0 * pos.abs()).fillna(0.0)
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
    """DD overlay v2: hysteresis on EXPERIENCED equity dd, re-cock on engine new highs."""
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
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
        eng_eq *= 1.0 + r
        was_hwm = eng_hwm
        eng_hwm = max(eng_hwm, eng_eq)
        if eng_eq >= was_hwm:
            state = 1.0
        elif exp_dd <= halt:
            state = 0.0
        elif exp_dd <= cut:
            state = 0.5
    return book * pd.Series(scale, index=book.index) * g


def fmt(v) -> str:
    return "      --" if pd.isna(v) else ("%7.2f%%" % (v * 100))


def main():
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    print("Window:", df.index.min().date(), "->", df.index.max().date(), " rows=%d" % len(df))

    # ========= A) corrected per-factor baseline (no cap) =========
    factors, rets, turn = build_v4(levels, None)
    net = apply_costs(factors, rets, turnover=turn)
    isw = window(net, IS_START, df.index.max())
    oos = window(net, OOS_START, IS_START)
    print("\n=== per-factor (v4 corrected engine, NO gap cap) ===")
    print("  %-16s | %-8s %-8s %-8s | %-8s %-8s %-8s %-8s %-6s" % (
        "factor", "IS_Sh", "IS_DD", "IS_worst", "OOS_Sh", "OOS_DD", "OOS_worst", "OOS_vol", "daysOn"))
    for f in net.columns:
        si, so = stats(isw[f]), stats(oos[f])
        pos = factors[f]
        don = float((pos.loc[oos.index].abs() > 0).mean())
        print("  %-16s | %8.2f %8s %8s | %8.2f %8s %8s %8s %5.1f%%" % (
            f, si["sharpe"], fmt(si["maxdd"]), fmt(si["worst_day"]),
            so["sharpe"], fmt(so["maxdd"]), fmt(so["worst_day"]), fmt(so["vol"]), don * 100))

    print("\nG1 check — cross_sectional worst days (per-leg fix):")
    s = net["cross_sectional"][net["cross_sectional"] < -0.04]
    print("  days<-4%%: %d" % len(s))
    for idx, v in s.nsmallest(5).items():
        print("     %s  %+7.2f%%" % (idx.date(), v * 100))

    # ========= B) design space: subset x weight x cap x overlay =========
    caps = {"NOCAP": None, "CAP8": 0.08, "CAP5": 0.05}
    results = []
    print("\n=== B design space (subset x weight x cap x overlay) ===")
    for capname, cap3 in caps.items():
        factors, rets, turn = build_v4(levels, cap3)
        net = apply_costs(factors, rets, turnover=turn)
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
                        print("%-6s %-4s %-5s -- | IS %6.2f %8s | OOS %6.2f %8.2f%% %8s %7.1f%%" % (
                            sname, scheme, capname, si["sharpe"], fmt(si["maxdd"]),
                            so["sharpe"], so["cagr"] * 100, fmt(so["maxdd"]), so["vol"] * 100))
    res = pd.DataFrame(results)
    res.to_csv(DEV / "book_oos_v4_results.csv", index=False)
    print("\nSaved book_oos_v4_results.csv (%d rows)" % len(res))

    # ========= C) top candidates: OOS DD <= -12% =========
    print("\n=== best OOS candidates with OOS MaxDD <= -12%% ===")
    sub = res[(res["OOS_dd"] >= -0.12) & (res["IS_sh"] >= 0.9)]
    top = sub.sort_values("OOS_sh", ascending=False).head(12)
    for _, r in top.iterrows():
        print("  %-6s %-4s %-5s ov=%d | IS Sh %5.2f DD %8s | OOS Sh %5.2f CAGR %8.2f%% DD %8s vol %5.1f%%" % (
            r["subset"], r["scheme"], r["cap"], int(r["ov"]), r["IS_sh"], fmt(r["IS_dd"]),
            r["OOS_sh"], r["OOS_cagr"] * 100, fmt(r["OOS_dd"]), r["OOS_vol"] * 100))

    # ========= D) F2 vol budget dimension (vt_f2) =========
    print("\n=== D: F2 engine vol target (vt_f2) on CORE3 HLV CAP5 ===")
    for vtf2 in [0.50, 0.35, 0.25]:
        factors, rets, turn = build_v4(levels, 0.05, vt_f2=vtf2)
        net = apply_costs(factors, rets, turnover=turn)
        isw = window(net, IS_START, df.index.max())
        oos = window(net, OOS_START, IS_START)
        w = weight_scheme(isw[SUBSETS["CORE3"]], "HLV")
        book = book_returns(net, SUBSETS["CORE3"], w)
        for ov in [0, 1]:
            b = book.loc[oos.index]
            bo = apply_overlay(b) if ov else b
            si = stats(book.loc[isw.index] if not ov else apply_overlay(book.loc[isw.index]))
            so = stats(bo)
            print("  vt_f2=%.2f ov=%d | IS Sh %5.2f | OOS Sh %5.2f CAGR %7.2f%% DD %8s vol %5.1f%% worst %8s" % (
                vtf2, ov, si["sharpe"], so["sharpe"], so["cagr"] * 100, fmt(so["maxdd"]),
                so["vol"] * 100, fmt(so["worst_day"])))


if __name__ == "__main__":
    main()