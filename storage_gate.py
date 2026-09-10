"""Storage/utilization gate — pre-registered (Round 6, EIA data).

Hypotheses (stated before measuring):
- H1 product stocks: the seasonal-crush reversion on crack_321 and
  cross_sectional is weakest when the market is drowning in products.
  De-risk when the combined gasoline+distillate stock seasonal z is high
  (> +1.0 surplus); restore at <= +0.5.
- H2 natgas storage: the NG crush reversion is demand-driven. De-risk ng
  when working gas storage seasonal z is high (> +1.0 glut); restore at
  <= +0.5.
- H3 Cushing crude: the BZ-WTI basis reversion breaks when Cushing runs
  toward tank tops. De-risk bzwti when the Cushing crude z is high
  (> +1.0); restore at <= +0.5. Low prior: F4's OOS collapse is structural.

Signal (causal):
- Weekly EIA series -> same-month expanding z (min 12 obs).
- Report lag: the weekly value becomes known ~6 days after the week-end
  (WPSR publishes Thursday for the Friday week-end). obs_date = period+6d.
- Forward-fill to the daily panel index; gate decided at t-1.

Rules are pre-registered; the answer is measured once. Report per-factor
IS/OOS, book tests with the v2 overlay, threshold/city-style robustness,
and a negative control (shuffled storage z).
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

spec = importlib.util.spec_from_file_location("b4", str(DEV / "book_oos_v4.py"))
b4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b4)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)


def weekly_z(f: Path, min_obs: int = 12, lag_days: int = 6) -> pd.Series:
    """Same-month expanding z of a weekly series, shifted for report lag."""
    if not f.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(f, index_col=0, parse_dates=True)["close"].dropna()
    out = pd.Series(np.nan, index=df.index)
    for m in range(1, 13):
        idx = df.index[df.index.month == m]
        for i in range(len(idx)):
            t = idx[i]
            past = df.loc[: t - pd.Timedelta(days=1)]
            past = past[past.index.month == m].dropna()
            if len(past) >= min_obs:
                mu, sd = past.mean(), past.std()
                if sd > 1e-9:
                    out.loc[t] = (df.loc[t] - mu) / sd
    out = out.clip(-8.0, 8.0)
    out.index = out.index + pd.Timedelta(days=lag_days)  # report release
    return out.sort_index()


def daily_gate_z(z: pd.Series, index: pd.Index) -> pd.Series:
    """Forward-fill the lagged weekly z onto the daily index (available at close t)."""
    return z.reindex(index.union(z.index)).ffill().reindex(index)


def gate_state(z: pd.Series, hi: float, lo: float) -> pd.Series:
    zz = z.to_numpy(dtype=float)
    st = np.ones(len(z), dtype=float)
    state = 1.0
    for i in range(len(z)):
        if np.isnan(zz[i]):
            st[i] = state
            continue
        if state == 1.0 and zz[i] > hi:
            state = 0.0
        elif state == 0.0 and zz[i] <= lo:
            state = 1.0
        st[i] = state
    return pd.Series(st, index=z.index)


def gated_from(pos0: pd.Series, ret0: pd.Series, g: pd.Series):
    """Scalar gate applied to an existing factor (works for any factor incl. multi-leg).

    state_g is decided at close t from z available at close t; the position held
    overnight from t is pos_t*g_t, so gated P&L during day t = g_{t-1}*ret_t.
    """
    g = g.reindex(pos0.index).fillna(1.0)
    pos = pos0 * g
    ret = ret0 * g.shift(1).fillna(1.0)
    turn = pos.diff().abs().fillna(0.0)
    return pos.fillna(0.0), ret.fillna(0.0), turn


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "vol": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 252
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1, "sharpe": r.mean() / r.std() * np.sqrt(252),
            "maxdd": (eq / eq.cummax() - 1).min(), "vol": r.std() * np.sqrt(252)}


def window(r: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    out = r.loc[start:end]
    return out.iloc[WARMUP:] if len(out) > WARMUP else out


def weight_scheme(returns_is: pd.DataFrame) -> dict[str, float]:
    w = pd.Series(1.0, index=returns_is.columns)
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
    factors, rets, turn = b4.build_v4(levels, None)
    net = b4.apply_costs(factors, rets, turnover=turn)
    isw = window(net, IS_START, df.index.max())
    oos = window(net, OOS_START, IS_START)

    # storage z series
    z_all = {}
    for key, fname in [
        ("gasoline", "W_EPM0F_SAX_NUS_MBBL"),
        ("distillate", "W_EPD0_SAX_NUS_MBBL"),
        ("crude", "W_EPC0_SAX_NUS_MBBL"),
        ("cushing", "W_EPC0_SAX_YCX_MBBL"),
        ("natgas", "NGW_EPG0_SWO_NUS_MMCF"),
    ]:
        z_all[key] = weekly_z(Path(f"/tmp/eia_{fname}.csv"))
    avail = {k: v for k, v in z_all.items() if len(v) > 0}
    print("available EIA z series:", list(avail.keys()))
    if not avail:
        print("No EIA data. Run fetch_eia.py first with EIA_API_KEY in the environment.")
        return

    # combined product stocks z (gasoline + distillate, same-month z of the SUM series)
    def combined_z(k1: str, k2: str) -> pd.Series:
        f1, f2 = Path(f"/tmp/eia_{k1}.csv"), Path(f"/tmp/eia_{k2}.csv")
        s1 = pd.read_csv(f1, index_col=0, parse_dates=True)["close"] if f1.exists() else pd.Series(dtype=float)
        s2 = pd.read_csv(f2, index_col=0, parse_dates=True)["close"] if f2.exists() else pd.Series(dtype=float)
        s = s1.add(s2, fill_value=0.0).dropna()
        out = pd.Series(np.nan, index=s.index)
        for m in range(1, 13):
            idx = s.index[s.index.month == m]
            for i in range(len(idx)):
                t = idx[i]
                past = s.loc[: t - pd.Timedelta(days=1)]
                past = past[past.index.month == m].dropna()
                if len(past) >= 12:
                    mu, sd = past.mean(), past.std()
                    if sd > 1e-9:
                        out.loc[t] = (s.loc[t] - mu) / sd
        out = out.clip(-8, 8)
        out.index = out.index + pd.Timedelta(days=6)
        return out.sort_index()

    product_z = combined_z("W_EPM0F_SAX_NUS_MBBL", "W_EPD0_SAX_NUS_MBBL")

    # pre-registered gates: (factor, z series, hi, lo)
    gates = []
    if len(product_z) > 0:
        gates.append(("crack_321", product_z, 1.0, 0.5))
        gates.append(("cross_sectional", product_z, 1.0, 0.5))
    if "natgas" in avail:
        gates.append(("ng", avail["natgas"], 1.0, 0.5))
    if "cushing" in avail:
        gates.append(("bzwti", avail["cushing"], 1.0, 0.5))

    print("\n=== Gated per-factor stats (storage gates, THR hi=1.0 lo=0.5) ===")
    gated_pos, gated_ret, gated_turn = {}, {}, {}
    for name, zseries, hi, lo in gates:
        dz = daily_gate_z(zseries, net.index)
        g = gate_state(dz, hi, lo)
        gp, gr, gt = gated_from(factors[name], rets[name], g)
        gated_pos[name], gated_ret[name], gated_turn[name] = gp, gr, gt
        gnet = gr - 5 / 10000 * gt - 20 / 252 / 10000 * gp.abs()
        iw = window(pd.DataFrame({name: gnet}), IS_START, df.index.max())[name]
        ow = window(pd.DataFrame({name: gnet}), OOS_START, IS_START)[name]
        si, so = stats(iw), stats(ow)
        raw_i = stats(window(pd.DataFrame({name: net[name]}), IS_START, df.index.max())[name])
        raw_o = stats(window(pd.DataFrame({name: net[name]}), OOS_START, IS_START)[name])
        print("  %-16s gated IS %5.2f OOS %5.2f DD %8s | raw IS %5.2f OOS %5.2f" % (
            name, si["sharpe"], so["sharpe"], fmt(so["maxdd"]), raw_i["sharpe"], raw_o["sharpe"]))

    # apply gates on top of base engine net
    f2, r2, t2 = dict(factors), dict(rets), dict(turn)
    for name in gated_pos:
        f2[name] = gated_pos[name]
        r2[name] = gated_ret[name]
        t2[name] = gated_turn[name]
    net2 = b4.apply_costs(f2, r2, turnover=t2)
    isw2 = window(net2, IS_START, df.index.max())
    oos2 = window(net2, OOS_START, IS_START)

    # combine product-gated crack+cross into one net variant vs champion
    base_factors = ["crack_321", "cross_sectional", "bzwti"]
    print("\n=== Books with storage gates (v2 overlay, EQ) ===")
    combos = {
        "CORE3 (champion)": base_factors,
        "CORE3+Gprod": base_factors,  # crack_321+cross gated by product z (same list, gated net)
        "CORE3+NG-S": base_factors + ["ng"],
        "CORE3+Gprod+NG-S+CU": base_factors + ["ng"],
    }
    for cname, flist in combos.items():
        w = weight_scheme(isw[flist] if cname != "CORE3 (champion)" else isw[flist])
        if cname == "CORE3+Gprod":
            book = book_returns(net2, flist, w)
        elif cname == "CORE3+NG-S":
            book = book_returns(net2, flist, w)
        elif cname == "CORE3+Gprod+NG-S+CU":
            book = book_returns(net2, flist, w)
        else:
            book = book_returns(net, flist, w)
        b_i, b_o = book.loc[isw2.index], book.loc[oos2.index]
        bi, bo = b4.apply_overlay(b_i), b4.apply_overlay(b_o)
        si, so = stats(bi), stats(bo)
        print("  %-22s | IS Sh %5.2f DD %8s | OOS Sh %5.2f CAGR %7.2f%% DD %8s vol %5.1f%%" % (
            cname, si["sharpe"], fmt(si["maxdd"]), so["sharpe"], so["cagr"] * 100,
            fmt(so["maxdd"]), so["vol"] * 100))

    # negative control: shuffled storage z on the strongest gate (ng)
    if "natgas" in avail:
        rng = np.random.default_rng(23)
        zs = avail["natgas"]
        sh = []
        for _ in range(10):
            perm = rng.permutation(len(zs))
            zsh = pd.Series(zs.to_numpy()[perm], index=zs.index)
            dz = daily_gate_z(zsh, net.index)
            g = gate_state(dz, 1.0, 0.5)
            gp, gr, gt = gated_from(factors["ng"], rets["ng"], g)
            f3 = dict(f2); f3["ng"] = gp
            r3 = dict(r2); r3["ng"] = gr
            t3 = dict(t2); t3["ng"] = gt
            n3 = b4.apply_costs(f3, r3, turnover=t3)
            i3 = window(n3, IS_START, df.index.max())
            o3 = window(n3, OOS_START, IS_START)
            w3 = weight_scheme(i3[base_factors + ["ng"]])
            bo = b4.apply_overlay(book_returns(n3, base_factors + ["ng"], w3).loc[o3.index])
            sh.append(stats(bo)["sharpe"])
        real = None
        w4 = weight_scheme(isw2[base_factors + ["ng"]])
        r4 = b4.stats(b4.apply_overlay(book_returns(net2, base_factors + ["ng"], w4).loc[oos2.index]))["sharpe"]
        print("\n  negative control (ng gate): shuffled mean OOS Sh %.2f vs real gated %.2f" % (
            np.mean(sh), r4))


if __name__ == "__main__":
    main()