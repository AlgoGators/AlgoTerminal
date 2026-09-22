"""Weather gate — Round 5, pre-registered.

Hypothesis (stated before measuring): the NG and winter-distillate (crack_ho)
seasonal-crush longs need weather support. When current weather is materially
warmer than the same-month norm, heating demand is weak, so the crush
reversion has no fundamental driver. Cut the position; restore on recovery.

Signal (causal):
- hdd7 = rolling-7d mean of max(0, 18C - T2M)  (heating degree days proxy)
- z = (hdd7 - same_month_mean) / same_month_std over PRIOR same-month hdd7
  (expanding, strictly before t, min 12 obs ~ 3 years). Clipped +-8.
- Primary city: NYC (US heating demand is population-weighted east).
- Robustness check: Houston as the alternate proxy.

Gate (hysteresis, like the entry logic):
- state 1 -> 0 when z < -THR   (THR pre-registered = -1.0)
- state 0 -> 1 when z >= -0.5
- gated position = factor position * state  (causal: z through t-1)

Tests (single pass, no OOS tuning):
1. NG-W and HO-W per-factor IS/OOS vs ungated.
2. Books with overlay v2: CORE3 vs CORE3+NG-W vs CORE3+HO-W vs CORE3+NG-W+HO-W.
3. Threshold sweep (-0.75 / -1.0 / -1.5) as a plateau check, not selection.
4. City robustness (Houston vs NYC).
5. Negative control: shuffled weather must not help.
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


def load_weather(city: str) -> pd.Series:
    df = pd.read_csv(f"/tmp/weather_{city}.csv", index_col=0, parse_dates=True)
    return df["close"]


def hdd_z(city: str) -> pd.Series:
    t2m = load_weather(city)
    hdd7 = pd.Series(np.maximum(0.0, 18.0 - t2m), index=t2m.index).rolling(7, min_periods=3).mean()
    out = pd.Series(np.nan, index=hdd7.index)
    for m in range(1, 13):
        idx = hdd7.index[hdd7.index.month == m]
        for i in range(len(idx)):
            t = idx[i]
            past = hdd7.loc[: t - pd.Timedelta(days=1)]
            past = past[past.index.month == m].dropna()
            if len(past) >= 12:
                mu, sd = past.mean(), past.std()
                if sd > 1e-9:
                    out.loc[t] = (hdd7.loc[t] - mu) / sd
    return out.clip(-8.0, 8.0)


def gate_state(z: pd.Series, thr: float, reenter: float = -0.5) -> pd.Series:
    zz = z.to_numpy(dtype=float)
    n = len(z)
    st = np.ones(n, dtype=float)
    state = 1.0
    for i in range(n):
        if np.isnan(zz[i]):
            st[i] = state
            continue
        if state == 1.0 and zz[i] < thr:
            state = 0.0
        elif state == 0.0 and zz[i] >= reenter:
            state = 1.0
        st[i] = state
    return pd.Series(st, index=z.index).shift(1).fillna(1.0)  # apply from next day


def gated_factor(name: str, city: str, levels, cap3sig, thr: float, reenter: float = -0.5):
    """Gate an existing factor by weather. Returns (pos, ret, turn)."""
    z = hdd_z(city)
    g = gate_state(z, thr, reenter)
    # rebuild the base factor series from the engine (single-leg factors only)
    if name == "ng":
        pos0 = b4.build_v4(levels, cap3sig)[0]["ng"]
        lvl = levels["ng"]
    elif name == "crack_ho":
        pos0 = b4.build_v4(levels, cap3sig)[0]["crack_ho"]
        lvl = levels["crack_ho"]
    else:
        raise ValueError(name)
    pos = pos0 * g.reindex(pos0.index).fillna(1.0)
    base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    ret = pos.shift(1).fillna(0.0) * lvl.diff() / base
    turn = pos.diff().abs().fillna(0.0)
    return pos.fillna(0.0), ret.fillna(0.0), turn


def build_engine(levels, cap3sig):
    factors, rets, turn = b4.build_v4(levels, cap3sig)
    return factors, rets, turn


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


def weight_scheme(returns_is: pd.DataFrame, scheme: str = "EQ") -> dict[str, float]:
    if scheme == "EQ":
        w = pd.Series(1.0, index=returns_is.columns)
    elif scheme == "HLV":
        vols = returns_is.std().replace(0.0, np.nan)
        w = (1.0 / vols) ** 0.5
    else:
        raise ValueError(scheme)
    return (w / w.sum()).to_dict()


def book_returns(net: pd.DataFrame, factors: list[str], weights: dict[str, float]) -> pd.Series:
    s = pd.Series(0.0, index=net.index)
    for f in factors:
        s = s + weights[f] * net[f]
    return s


def fmt(v) -> str:
    return "      --" if pd.isna(v) else ("%7.2f%%" % (v * 100))


def main():
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)

    factors, rets, turn = build_engine(levels, None)
    net0 = b4.apply_costs(factors, rets, turnover=turn)

    print("\n=== Gated per-factor stats (NYC HDD z, THR=-1.0) ===")
    for name in ["ng", "crack_ho"]:
        z = hdd_z("NYC").reindex(net0.index)
        g = gate_state(z, -1.0).reindex(net0.index)
        gpos = factors[name] * g.fillna(1.0)
        lvl = levels[name]
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        gret = gpos.shift(1).fillna(0.0) * lvl.diff() / base
        gnet = gret - TRADE_BPS / 10000.0 * gpos.diff().abs().fillna(0.0) - ROLL_BPS / 252.0 / 10000.0 * gpos.abs()
        isw = window(pd.DataFrame({name: gnet}), IS_START, df.index.max())
        oos = window(pd.DataFrame({name: gnet}), OOS_START, IS_START)
        si, so = stats(isw[name]), stats(oos[name])
        n0 = net0[name]
        s0is, s0oos = stats(window(pd.DataFrame({name: n0}), IS_START, df.index.max())[name]), stats(window(pd.DataFrame({name: n0}), OOS_START, IS_START)[name])
        on0 = (factors[name].abs() > 0).mean()
        ong = (gpos.abs() > 0).mean()
        print("  %-10s gated: IS Sh %5.2f | OOS Sh %5.2f DD %8s (daysOn %.0f%%) | raw: IS Sh %5.2f OOS Sh %5.2f (daysOn %.0f%%)" % (
            name, si["sharpe"], so["sharpe"], fmt(so["maxdd"]), ong * 100,
            s0is["sharpe"], s0oos["sharpe"], on0 * 100))

    print("\n=== Books with weather-gated legs (overlay v2, EQ weights) ===")
    # rebuild full net with gated legs replacing the originals
    gpos_ng, gret_ng, gturn_ng = gated_factor("ng", "NYC", levels, None, -1.0)
    gpos_ho, gret_ho, gturn_ho = gated_factor("crack_ho", "NYC", levels, None, -1.0)
    factors_g = dict(factors)
    factors_g["ng"] = gpos_ng
    factors_g["crack_ho"] = gpos_ho
    rets_g = dict(rets)
    rets_g["ng"] = gret_ng
    rets_g["crack_ho"] = gret_ho
    turn_g = dict(turn)
    turn_g["ng"] = gturn_ng
    turn_g["crack_ho"] = gturn_ho
    netg = b4.apply_costs(factors_g, rets_g, turnover=turn_g)
    isw = window(net_g := netg, IS_START, df.index.max())
    oos = window(net_g, OOS_START, IS_START)

    combos = {
        "CORE3": ["crack_321", "cross_sectional", "bzwti"],
        "CORE3+NGW": ["crack_321", "cross_sectional", "bzwti", "ng"],
        "CORE3+HOW": ["crack_321", "cross_sectional", "bzwti", "crack_ho"],
        "CORE3+NGW+HOW": ["crack_321", "cross_sectional", "bzwti", "ng", "crack_ho"],
    }
    for cname, flist in combos.items():
        w = weight_scheme(isw[flist])
        book = book_returns(net_g, flist, w)
        b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
        for ov in [0, 1]:
            bi = b4.apply_overlay(b_is) if ov else b_is
            bo = b4.apply_overlay(b_oos) if ov else b_oos
            si, so = stats(bi), stats(bo)
            print("  %-14s ov=%d | IS Sh %5.2f DD %8s | OOS Sh %5.2f CAGR %7.2f%% DD %8s vol %5.1f%% worst %6.2f%%" % (
                cname, ov, si["sharpe"], fmt(si["maxdd"]), so["sharpe"], so["cagr"] * 100,
                fmt(so["maxdd"]), so["vol"] * 100, so["worst_day"] * 100))

    print("\n=== Threshold sweep (CORE3+NGW, overlay v2, EQ) ===")
    for thr in [-0.75, -1.0, -1.5]:
        gp, gr, gt = gated_factor("ng", "NYC", levels, None, thr)
        f2, r2, t2 = dict(factors), dict(rets), dict(turn)
        f2["ng"], r2["ng"], t2["ng"] = gp, gr, gt
        n2 = b4.apply_costs(f2, r2, turnover=t2)
        i2 = window(n2, IS_START, df.index.max())
        o2 = window(n2, OOS_START, IS_START)
        w2 = weight_scheme(i2[["crack_321", "cross_sectional", "bzwti", "ng"]])
        bo = b4.apply_overlay(book_returns(n2, ["crack_321", "cross_sectional", "bzwti", "ng"], w2).loc[o2.index])
        so = stats(bo)
        print("  THR %5.2f | OOS Sh %5.2f CAGR %7.2f%% DD %8s vol %5.1f%%" % (
            thr, so["sharpe"], so["cagr"] * 100, fmt(so["maxdd"]), so["vol"] * 100))

    print("\n=== City robustness (CORE3+NGW, THR=-1.0, overlay v2) ===")
    for city in ["NYC", "HOUSTON"]:
        gp, gr, gt = gated_factor("ng", city, levels, None, -1.0)
        f2, r2, t2 = dict(factors), dict(rets), dict(turn)
        f2["ng"], r2["ng"], t2["ng"] = gp, gr, gt
        n2 = b4.apply_costs(f2, r2, turnover=t2)
        i2 = window(n2, IS_START, df.index.max())
        o2 = window(n2, OOS_START, IS_START)
        w2 = weight_scheme(i2[["crack_321", "cross_sectional", "bzwti", "ng"]])
        bo = b4.apply_overlay(book_returns(n2, ["crack_321", "cross_sectional", "bzwti", "ng"], w2).loc[o2.index])
        so = stats(bo)
        print("  %-8s | OOS Sh %5.2f CAGR %7.2f%% DD %8s vol %5.1f%%" % (
            city, so["sharpe"], so["cagr"] * 100, fmt(so["maxdd"]), so["vol"] * 100))

    print("\n=== Negative control: shuffled weather (CORE3+NGW, THR=-1.0) ===")
    z_nyc = hdd_z("NYC")
    rng = np.random.default_rng(11)
    sh = []
    for _ in range(12):
        zs = pd.Series(z_nyc.to_numpy()[rng.permutation(len(z_nyc))], index=z_nyc.index)
        g = gate_state(zs, -1.0).reindex(net0.index)
        gpos = factors["ng"] * g.fillna(1.0)
        lvl = levels["ng"]
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        gret = gpos.shift(1).fillna(0.0) * lvl.diff() / base
        gnet = gret - TRADE_BPS / 10000.0 * gpos.diff().abs().fillna(0.0) - ROLL_BPS / 252.0 / 10000.0 * gpos.abs()
        n2 = pd.DataFrame(dict(net0))
        n2["ng"] = gnet
        i2 = window(n2, IS_START, df.index.max())
        o2 = window(n2, OOS_START, IS_START)
        w2 = weight_scheme(i2[["crack_321", "cross_sectional", "bzwti", "ng"]])
        bo = b4.apply_overlay(book_returns(n2, ["crack_321", "cross_sectional", "bzwti", "ng"], w2).loc[o2.index])
        sh.append(stats(bo)["sharpe"])
    print("  shuffled OOS Sharpe mean %.2f (real gated %.2f, CORE3 baseline %.2f)" % (
        np.mean(sh),
        stats(b4.apply_overlay(book_returns(net_g, ["crack_321", "cross_sectional", "bzwti", "ng"],
                                            weight_scheme(isw[["crack_321", "cross_sectional", "bzwti", "ng"]])
                                            ).loc[oos.index]))["sharpe"],
        stats(b4.apply_overlay(book_returns(net_g, ["crack_321", "cross_sectional", "bzwti"], weight_scheme(isw[["crack_321", "cross_sectional", "bzwti"]])).loc[oos.index]))["sharpe"]))


if __name__ == "__main__":
    main()