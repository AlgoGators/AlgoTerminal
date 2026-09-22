"""Book v5 — extract more edge (Round 4).

Pre-registered rules (stated before measuring, one IS/OOS pass):

A) Overlay v3 (regime-aware de-lever). The v2 overlay de-risks during the
   crisis regimes where the strategy makes its money (it sat flat on
   2020-04-20, +21.1% raw). v3 keeps FULL participation while the book
   holds a DEEP crush (any held leg seasonal z <= DEEP, DEEP=-1.25 a
   priori), and applies the v2 ladder only outside deep-crush states.
   Rationale: the edge IS crisis reversion; the windfalls come from deep
   crush episodes reversing. 2013/2019 bleeds had moderate crushes
   (z -0.5 to -1.0), so the gate does not re-expose them.

B) Sizing taming. The engine's MAX_LEV=1.0 binds before the vol target
   (ng at cap 60% of on-days), so it runs full-notional-when-on. TAMED
   applies a priori per-factor position caps (higher vol factors get
   lower caps): cross_sectional/brent_xs 0.40, ng 0.40, crack legs 0.60,
   bzwti 0.50. Goal: dampen gap-day kurtosis at the source.

C) Risk-parity weights with covariance shrinkage toward the diagonal
   (IS-trained only). RP05 = shrink 0.5, RP07 = shrink 0.7. The honest
   IS correlation (crack_321 vs cross_sectional ~0.30) should push the
   book off the crack-complex-heavy equal weight.

D) Brent complex legs (data already in the panel, BZ valid from OOS
   start). F5 = seasonal crush long on Brent 3:2:1; F6 = cross-sectional
   most-crushed of {brent321, brent_gas, brent_ho}. Same products priced
   against Brent instead of WTI: a different refining-margin geography.
   brent321 corr 0.39 with wti321; brent_gas corr 0.04. Included only if
   the honest OOS book improves (this is the OOS test, reported as-is).

Report: subset x weight x sizing x overlay, IS vs OOS, net 5bps/20roll.
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

spec = importlib.util.spec_from_file_location("b4", str(DEV / "book_oos_v4.py"))
b4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b4)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)

# --- per-factor position caps (a priori risk budget) ---
TAMING = {
    "cross_sectional": 0.40, "brent_xs": 0.40, "ng": 0.40,
    "crack_321": 0.60, "crack_ho": 0.60, "brent321": 0.60, "bzwti": 0.50,
}

SUBSETS = {
    "CORE3": ["crack_321", "cross_sectional", "bzwti"],
    "CORE3B5": ["crack_321", "cross_sectional", "bzwti", "brent321"],
    "CORE3B6": ["crack_321", "cross_sectional", "bzwti", "brent_xs"],
    "CORE3BB": ["crack_321", "cross_sectional", "bzwti", "brent321", "brent_xs"],
    "FULLB": ["crack_321", "crack_ho", "cross_sectional", "ng", "bzwti", "brent321", "brent_xs"],
}


def brent_levels(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "brent321": (2 * df.RB + df.HO) / 3 * 42 - df.BZ,
        "brent_gas": df.RB * 42 - df.BZ,
        "brent_ho": df.HO * 42 - df.BZ,
    }


def seasonal_crush_pos(level: pd.Series, vt: float, cap3sig: float | None) -> tuple[pd.Series, pd.Series, pd.Series]:
    """F1/F3-style seasonal crush long on one level. Returns (pos, ret, turnover)."""
    z = fb.seasonal_z(level)
    zz = z.to_numpy(dtype=float)
    vals = np.zeros(len(level))
    state = 0.0
    for i in range(len(level)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if state == 0.0 and zz[i] <= -fb.SMR_ENTRY:
            state = 1.0
        elif state == 1.0 and zz[i] >= fb.SMR_EXIT:
            state = 0.0
        vals[i] = state
    sig = pd.Series(vals, index=level.index)
    pos = sig * b4.fixed_vol_scale(level, vt)
    pos = b4.leg_risk(pos, level, trailing_stop=False)
    if cap3sig is not None:
        pos = pos.clip(-b4.gap_cap(level, cap3sig), b4.gap_cap(level, cap3sig))
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    ret = pos.shift(1).fillna(0.0) * level.diff() / base
    return pos.fillna(0.0), ret.fillna(0.0), pos.diff().abs().fillna(0.0)


def f2_generic(levels: dict[str, pd.Series], legs: list[str], name: str, vt: float,
               cap3sig: float | None) -> tuple[dict[str, pd.Series], pd.Series, pd.Series, dict[str, pd.Series]]:
    """Per-leg cross-sectional factor on arbitrary legs. Returns (leg_pos, total_pos, total_ret, turnover)."""
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
    leg_pos = {}
    leg_ret = {}
    for li, leg in enumerate(legs):
        lvl = levels[leg]
        on = chosen == li
        scale = b4.fixed_vol_scale(lvl, vt).where(on, 0.0)
        sig = pd.Series(1.0, index=lvl.index).where(on, 0.0)
        p = b4.leg_risk(sig * scale, lvl, trailing_stop=fb.TRAILING_STOP_ON["cross_sectional"])
        if cap3sig is not None:
            p = p.clip(-b4.gap_cap(lvl, cap3sig), b4.gap_cap(lvl, cap3sig))
        leg_pos[leg] = p.fillna(0.0)
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        leg_ret[leg] = p.shift(1).fillna(0.0) * lvl.diff() / base
    total_pos = pd.DataFrame(leg_pos).sum(axis=1)
    total_ret = pd.DataFrame(leg_ret).sum(axis=1).fillna(0.0)
    turnover = pd.DataFrame(leg_pos).diff().abs().sum(axis=1)
    return leg_pos, total_pos, total_ret, turnover


def build_v5(levels: dict[str, pd.Series], cap3sig: float | None,
             tamed: bool) -> tuple[dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series]]:
    """Build all factor positions/returns/turnover + per-leg positions (for depth)."""
    fb.vol_scale = b4.fixed_vol_scale
    factors, rets, turnover = {}, {}, {}
    leg_pos_all: dict[str, pd.Series] = {}

    # WTI factors (reuse v4 engine)
    f4pos, f4ret, f4turn = b4.build_v4(levels, cap3sig)
    factors.update(f4pos)
    rets.update(f4ret)
    turnover.update(f4turn)
    # WTI cross per-leg positions (recompute to expose legs)
    wti_legs, wti_pos, wti_ret, wti_turn = f2_generic(levels, ["crack_321", "crack_gas", "crack_ho"],
                                                      "cross_sectional", fb.VT_F2, cap3sig)
    # merge per-leg holdings across factors (F1 in crack_321 + F2 in crack_321)
    leg_pos_all["crack_321"] = factors["crack_321"] + wti_legs.get("crack_321", pd.Series(0.0, index=factors["crack_321"].index))
    leg_pos_all["crack_gas"] = wti_legs.get("crack_gas", pd.Series(0.0, index=factors["crack_321"].index))
    leg_pos_all["crack_ho"] = wti_legs.get("crack_ho", pd.Series(0.0, index=factors["crack_321"].index))
    # single-leg WTI factor positions -> their own leg
    for name in ["ng", "bzwti"]:
        leg_pos_all[name] = factors[name]

    # Brent factors
    bl = brent_levels(levels["__df__"]) if "__df__" in levels else None
    # pass the raw df through levels under a private key
    df = levels["__df__"]
    blevels = brent_levels(df)
    for k, v in blevels.items():
        levels[k] = v
    # F5: brent321 seasonal crush
    p5, r5, t5 = seasonal_crush_pos(blevels["brent321"], fb.VT_F1, cap3sig)
    factors["brent321"] = p5
    rets["brent321"] = r5
    turnover["brent321"] = t5
    # F6: brent cross-sectional
    blegs, bpos, bret, bturn = f2_generic(blevels, ["brent321", "brent_gas", "brent_ho"],
                                          "brent_xs", fb.VT_F2, cap3sig)
    factors["brent_xs"] = bpos
    rets["brent_xs"] = bret
    turnover["brent_xs"] = bturn
    # merge per-leg holdings across F5 and F6
    idx = factors["brent321"].index
    leg_pos_all["brent321"] = factors["brent321"] + blegs.get("brent321", pd.Series(0.0, index=idx))
    leg_pos_all["brent_gas"] = blegs.get("brent_gas", pd.Series(0.0, index=idx))
    leg_pos_all["brent_ho"] = blegs.get("brent_ho", pd.Series(0.0, index=idx))

    if tamed:
        for name, cap in TAMING.items():
            if name in factors:
                factors[name] = factors[name].clip(-cap, cap)
                lvl = levels.get(name)
                if lvl is None and name in blevels:
                    lvl = blevels[name]
                if lvl is not None:
                    base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
                    rets[name] = factors[name].shift(1).fillna(0.0) * lvl.diff() / base
                else:
                    # cross_sectional / brent_xs: recompute from leg_pos
                    lp = {k: v for k, v in leg_pos_all.items() if k in (["crack_321", "crack_gas", "crack_ho"] if name == "cross_sectional" else ["brent321", "brent_gas", "brent_ho"])}
                    tot = pd.DataFrame(lp).sum(axis=1)
                    # scale each leg down by cap/total max
                    mx = tot.abs().max()
                    if mx > cap:
                        f = cap / mx
                        for k in lp:
                            lp[k] = lp[k] * f
                        leg_pos_all.update(lp)
                        factors[name] = pd.DataFrame(lp).sum(axis=1)
                        rsum = pd.Series(0.0, index=factors[name].index)
                        for k, lvlk in (blevels if name == "brent_xs" else levels).items():
                            if k in lp:
                                base = b4.base_of(lvlk).shift(1).replace(0.0, np.nan)
                                rsum = rsum + lp[k].shift(1).fillna(0.0) * lvlk.diff() / base
                        rets[name] = rsum.fillna(0.0)
    return factors, rets, turnover, leg_pos_all


def apply_costs(positions, returns, turnover=None, trade_bps=TRADE_BPS, roll_bps=ROLL_BPS):
    out = {}
    for name in returns:
        pos = positions[name].fillna(0.0)
        dp = turnover[name].fillna(0.0) if turnover is not None and name in turnover else pos.diff().fillna(0.0).abs()
        out[name] = (returns[name] - trade_bps / 10000.0 * dp - roll_bps / 252.0 / 10000.0 * pos.abs()).fillna(0.0)
    return pd.DataFrame(out)


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


def weight_scheme(returns_is: pd.DataFrame, scheme: str) -> dict[str, float]:
    vols = returns_is.std().replace(0.0, np.nan)
    if scheme == "EQ":
        w = pd.Series(1.0, index=returns_is.columns)
    elif scheme == "HLV":
        w = (1.0 / vols) ** 0.5
    elif scheme == "INV":
        w = 1.0 / vols
    elif scheme in ("RP05", "RP07"):
        shrink = 0.5 if scheme == "RP05" else 0.7
        w = rp_weights(returns_is, shrink)
    else:
        raise ValueError(scheme)
    return (w / w.sum()).to_dict()


def rp_weights(returns_is: pd.DataFrame, shrink: float) -> pd.Series:
    cov = returns_is.cov().to_numpy(dtype=float)
    d = np.sqrt(np.diag(cov))
    corr = cov / np.outer(d, d)
    shrunk = (1 - shrink) * corr + shrink * np.eye(len(corr))
    covs = shrunk * np.outer(d, d)
    w = np.ones(len(corr))
    for _ in range(200):
        mcv = covs @ w
        w = 1.0 / np.sqrt(np.maximum(mcv, 1e-12))
        w = w / w.sum()
    return pd.Series(w, index=returns_is.columns)


def book_returns(net: pd.DataFrame, factors: list[str], weights: dict[str, float]) -> pd.Series:
    s = pd.Series(0.0, index=net.index)
    for f in factors:
        s = s + weights[f] * net[f]
    return s


def drawdown(s: pd.Series) -> pd.Series:
    eq = (1 + s).cumprod()
    return eq / eq.cummax() - 1


def book_depth(leg_pos: dict[str, pd.Series], zdf: dict[str, pd.Series], index) -> pd.Series:
    """Most-crushed held leg z through t-1. NaN where nothing held."""
    cols = {}
    for leg, p in leg_pos.items():
        z = zdf[leg]
        cols[leg] = z.shift(1).where((p.shift(1).abs() > 0))
    D = pd.DataFrame(cols, index=index)
    return D.min(axis=1)


def apply_overlay_v2(book: pd.Series, vol_target: float = 0.10, cut: float = -0.06, halt: float = -0.10) -> pd.Series:
    return b4.apply_overlay(book, vol_target, cut, halt)


def apply_overlay_v3(book: pd.Series, depth: pd.Series, vol_target: float = 0.10,
                     cut: float = -0.06, halt: float = -0.10, deep: float = -1.25) -> pd.Series:
    """Regime-aware: deep crush (depth<=deep) forces FULL; else v2 ladder."""
    rv = book.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    gear = (vol_target / rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
    n = len(book)
    scale = np.empty(n)
    state = 1.0
    eq, hwm = 1.0, 1.0
    eng_eq, eng_hwm = 1.0, 1.0
    ddepth = depth.reindex(book.index).to_numpy(dtype=float)
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
        d = ddepth[t]
        if not np.isnan(d) and d <= deep:
            state = 1.0  # deep crush active -> stay invested
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


def fmt(v) -> str:
    return "      --" if pd.isna(v) else ("%7.2f%%" % (v * 100))


def main():
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    levels["__df__"] = df  # carry raw df for brent levels
    print("Window:", df.index.min().date(), "->", df.index.max().date(), " rows=%d" % len(df))

    zdf = {}
    for leg in ["crack_321", "crack_gas", "crack_ho", "ng", "bzwti"]:
        zdf[leg] = fb.seasonal_z(levels[leg])
    for leg in ["brent321", "brent_gas", "brent_ho"]:
        zdf[leg] = fb.seasonal_z(brent_levels(df)[leg])

    results = []
    print("\n=== design space: subset x weight x sizing x overlay ===")
    for capname, cap3 in [("NOCAP", None), ("CAP5", 0.05)]:
        for tamed in [False, True]:
            factors, rets, turn, legpos = build_v5(levels, cap3, tamed)
            net = apply_costs(factors, rets, turnover=turn)
            isw = window(net, IS_START, df.index.max())
            oos = window(net, OOS_START, IS_START)
            depth = book_depth(legpos, zdf, net.index)
            for sname, flist in SUBSETS.items():
                for scheme in ["EQ", "HLV", "RP05", "RP07"]:
                    w = weight_scheme(isw[flist], scheme)
                    book = book_returns(net, flist, w)
                    b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
                    d_is, d_oos = depth.loc[isw.index], depth.loc[oos.index]
                    for ov in ["OFF", "V2", "V3"]:
                        if ov == "OFF":
                            bi, bo = b_is, b_oos
                        elif ov == "V2":
                            bi, bo = apply_overlay_v2(b_is), apply_overlay_v2(b_oos)
                        else:
                            bi, bo = apply_overlay_v3(b_is, d_is), apply_overlay_v3(b_oos, d_oos)
                        si, so = stats(bi), stats(bo)
                        results.append({"cap": capname, "tamed": tamed, "subset": sname, "scheme": scheme,
                                        "ov": ov, "IS_sh": si["sharpe"], "IS_dd": si["maxdd"],
                                        "OOS_sh": so["sharpe"], "OOS_cagr": so["cagr"], "OOS_dd": so["maxdd"],
                                        "OOS_vol": so["vol"], "OOS_worst": so["worst_day"]})
                        if capname == "NOCAP" and not tamed and ov in ("OFF", "V3"):
                            print("%-7s %-5s %-5s %-3s | IS %6.2f %8s | OOS %6.2f %7.2f%% %8s %6.1f%%" % (
                                sname, scheme, "NT", ov, si["sharpe"], fmt(si["maxdd"]),
                                so["sharpe"], so["cagr"] * 100, fmt(so["maxdd"]), so["vol"] * 100))
    res = pd.DataFrame(results)
    res.to_csv(DEV / "book_oos_v5_results.csv", index=False)
    print("\nSaved book_oos_v5_results.csv (%d rows)" % len(res))

    print("\n=== top OOS candidates: OOS DD <= -12%, IS sh >= 0.9 ===")
    sub = res[(res["OOS_dd"] >= -0.12) & (res["IS_sh"] >= 0.9)]
    top = sub.sort_values("OOS_sh", ascending=False).head(15)
    for _, r in top.iterrows():
        print("  %-7s %-5s %-4s %-3s %-5s | IS %5.2f %8s | OOS %5.2f %7.2f%% %8s %5.1f%%" % (
            r["subset"], r["scheme"], "T" if r["tamed"] else "NT", r["ov"], r["cap"],
            r["IS_sh"], fmt(r["IS_dd"]), r["OOS_sh"], r["OOS_cagr"] * 100, fmt(r["OOS_dd"]), r["OOS_vol"] * 100))

    # Brent contribution check: CORE3 vs CORE3BB, EQ, NT, V3
    print("\n=== Brent legs contribution (EQ, NT, V3) ===")
    for sname in ["CORE3", "CORE3B5", "CORE3B6", "CORE3BB"]:
        row = res[(res["subset"] == sname) & (res["scheme"] == "EQ") & (res["tamed"] == False) & (res["ov"] == "V3") & (res["cap"] == "NOCAP")]
        if len(row):
            r = row.iloc[0]
            print("  %-8s OOS Sh %5.2f CAGR %7.2f%% DD %8s vol %5.1f%%" % (
                sname, r["OOS_sh"], r["OOS_cagr"] * 100, fmt(r["OOS_dd"]), r["OOS_vol"] * 100))


if __name__ == "__main__":
    main()