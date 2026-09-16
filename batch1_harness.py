"""Batch 1 harness: alpha source map cheap items.

Preregistered in research/batch1_alpha_map.md. No parameters fitted.

Sections:
  M1  winter maintenance calendar tilt (source 1)
  M2  cold-weather vehicle demand event study (source 2)
  M3  fuel blend windows (source 3)
  M7  norm drift diagnostics (source 7)
  M11 leg correlation matrix (source 11)
  M9  multi-crush basket + depth sizing (sources 9, 10)
"""
from __future__ import annotations

import importlib.util
import csv
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
ENGINE = ROOT / "engine"
PANEL = ENGINE / "panel_v2.parquet"
EIA = ENGINE / "eia"
WEA = ENGINE / "weather"

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

NC = 20
NC_SEED = 23
MAINT_DIP = 1.0
COLD_Z = -1.0
WINTER = (11, 12, 1, 2, 3)
DEPTH_K = 0.5
CROSS_LEGS = ["crack_321", "crack_gas", "crack_ho"]


def log(msg: str) -> None:
    print(msg, flush=True)


def read_csv(path: Path, col: str = "close") -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[col].astype(float)


def same_month_expanding_mean(s: pd.Series, min_obs: int = 30) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        cs = sub.cumsum()
        ct = sub.notna().cumsum()
        mean = cs.shift(1) / ct.shift(1)
        mean[ct.shift(1) < min_obs] = np.nan
        out.loc[idx] = mean
    return out


def same_month_expanding_std(s: pd.Series, min_obs: int = 30) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        mean = sub.expanding().mean().shift(1)
        var = ((sub - mean).pow(2)).expanding().mean().shift(1)
        sd = var.pow(0.5)
        sd[sd.index.isin(mean.index[mean.isna()])] = np.nan
        sd[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = sd
    return out


def state_machine(z: pd.Series, enter: float = -0.75, exit_: float = -0.5) -> pd.Series:
    zz = z.to_numpy(dtype=float)
    vals = np.zeros(len(z), dtype=float)
    state = 0.0
    for i in range(len(z)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if state == 0.0 and zz[i] <= enter:
            state = 1.0
        elif state == 1.0 and zz[i] >= exit_:
            state = 0.0
        vals[i] = state
    return pd.Series(vals, index=z.index)


def leg_ready(level: pd.Series, vt: float):
    z = fb.seasonal_z(level)
    scale = b4.fixed_vol_scale(level, vt)
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    diff = level.diff()
    return z, scale, base, diff


def leg_pos(sig, level, scale, base, diff, trailing, extra=None):
    mult = extra if extra is not None else pd.Series(1.0, index=level.index)
    raw = sig * scale * mult.reindex(level.index).fillna(1.0).shift(1).fillna(1.0)
    pos = b4.leg_risk(raw, level, trailing_stop=trailing).fillna(0.0)
    ret = (pos.shift(1).fillna(0.0) * diff / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    return pos, ret, turn


def cross_once(levels, zdf, tilt, vt):
    """v1 F2 most-crushed with tilt, using a precomputed z frame."""
    arr = zdf.to_numpy(dtype=float)
    cols = list(zdf.columns)
    idx = zdf.index
    chosen = pd.Series(np.nan, index=idx, dtype=float)
    valid = zdf.notna().all(axis=1)
    for i in range(len(zdf)):
        if valid.iloc[i]:
            row = arr[i]
            if np.isnan(row).all():
                continue
            k = cols[int(np.nanargmin(row))]
            if row[int(np.nanargmin(row))] < fb.XS_MIN_Z:
                chosen.iloc[i] = CROSS_LEGS.index(k)
    leg_p, leg_r, leg_t = {}, {}, {}
    for li, leg in enumerate(CROSS_LEGS):
        lvl = levels[leg]
        on = chosen == li
        sc = tilt.reindex(lvl.index).fillna(1.0).shift(1).fillna(1.0)
        raw = (pd.Series(1.0, index=lvl.index).where(on, 0.0)
               * b4.fixed_vol_scale(lvl, vt) * sc)
        p = b4.leg_risk(raw, lvl, trailing_stop=False).fillna(0.0)
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        leg_p[leg] = p
        leg_r[leg] = (p.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
        leg_t[leg] = p.diff().abs().fillna(0.0)
    return (pd.DataFrame(leg_p).sum(axis=1).rename("cross"),
            pd.DataFrame(leg_r).sum(axis=1).fillna(0.0).rename("cross"),
            pd.DataFrame(leg_t).sum(axis=1).rename("cross"))


def book_stats_positions(parts: dict, oos_idx, isw_idx):
    pos = {k: v[0] for k, v in parts.items()}
    ret = {k: v[1] for k, v in parts.items()}
    turn = {k: v[2] for k, v in parts.items()}
    net = b4.apply_costs(pos, ret, turnover=turn)
    for c in net.columns:
        net[c] = net[c].fillna(0.0)
    return net


def stats_book(net, names, oos_idx, isw_idx):
    w = b4.weight_scheme(net[names], "EQ")
    bk = b4.book_returns(net, names, w)
    si_raw = b4.stats(bk.loc[isw_idx.intersection(bk.index)])
    so_raw = b4.stats(bk.loc[oos_idx.intersection(bk.index)])
    si_ov = b4.stats(b4.apply_overlay(bk).loc[isw_idx.intersection(bk.index)])
    so_ov = b4.stats(b4.apply_overlay(bk).loc[oos_idx.intersection(bk.index)])
    return si_raw, so_raw, si_ov, so_ov


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    isw_idx = b4.window(pd.DataFrame(index=full_idx), b4.IS_START, full_idx.max()).index
    oos_idx = b4.window(pd.DataFrame(index=full_idx), b4.OOS_START, b4.IS_START).index

    fac4, rets4, turn4 = b4.build_v4(levels, None)
    names4 = ["crack_321", "cross_sectional", "bzwti"]
    champ = {n: (fac4[n], rets4[n], turn4[n]) for n in names4}
    # ------------------------------------------------------------------
    log("=== M11: leg correlation matrix (corrected net returns) ===")
    net4 = b4.apply_costs(fac4, rets4, turnover=turn4)
    nets = net4[["crack_321", "cross_sectional", "crack_ho", "ng", "bzwti"]]
    c_is = nets.loc[isw_idx.intersection(nets.index)].corr()
    c_oos = nets.loc[oos_idx.intersection(nets.index)].corr()
    for name, cm in (("IS", c_is), ("OOS", c_oos)):
        log(f"\n{name} correlation:\n{cm.round(3).to_string()}")
    c_is.round(4).to_csv(ROOT / "results" / "batch1_correlations_IS.csv")
    c_oos.round(4).to_csv(ROOT / "results" / "batch1_correlations_OOS.csv")

    # ------------------------------------------------------------------
    log("\n=== M1: winter maintenance calendar tilt ===")
    util = read_csv(EIA / "raw_WPULEUS3.csv")
    av = util.copy()
    av.index = av.index + pd.Timedelta(days=6)
    av = av[~av.index.duplicated(keep="last")].sort_index()
    util_d = av.reindex(av.index.union(full_idx)).sort_index().ffill().reindex(full_idx)
    sm_mean = same_month_expanding_mean(util_d)
    ann_mean = util_d.rolling(365, min_periods=200).mean().shift(1)
    mwin = pd.Series(np.select(
        [(sm_mean.shift(1) < ann_mean - MAINT_DIP) & ann_mean.notna()],
        [1.25], default=1.0), index=full_idx)
    cz, cs, cb, cd = leg_ready(levels["crack_321"], fb.VT_F1)
    crack_sig = state_machine(cz)
    cross_z = pd.DataFrame({k: fb.seasonal_z(levels[k]) for k in CROSS_LEGS})
    cpos, cret, cturn = leg_pos(crack_sig, levels["crack_321"], cs, cb, cd,
                                fb.TRAILING_STOP_ON["crack_321"], extra=mwin)
    xpos, xret, xturn = cross_once(levels, cross_z, mwin, fb.VT_F2)
    bpos, bret, bturn = fac4["bzwti"], rets4["bzwti"], turn4["bzwti"]
    netm1 = book_stats_positions({"crack": (cpos, cret, cturn),
                                  "cross": (xpos, xret, xturn),
                                  "bzwti": (bpos, bret, bturn)}, oos_idx, isw_idx)
    si, so, siov, soov = stats_book(netm1, ["crack", "cross", "bzwti"], oos_idx, isw_idx)
    ref = stats_book(book_stats_positions(champ, oos_idx, isw_idx), names4, oos_idx, isw_idx)
    log(f"M1 real: OOS raw {so['sharpe']:.3f} / ov {soov['sharpe']:.3f} "
        f"(champion ov {ref[3]['sharpe']:.3f}); IS ov {siov['sharpe']:.3f}")
    nc = []
    inv = pd.Series(np.select([mwin == 1.25], [1.0], default=1.25), index=full_idx)
    cpos_i, cret_i, cturn_i = leg_pos(crack_sig, levels["crack_321"], cs, cb, cd,
                                      fb.TRAILING_STOP_ON["crack_321"], extra=inv)
    xpos_i, xret_i, xturn_i = cross_once(levels, cross_z, inv, fb.VT_F2)
    neti = book_stats_positions({"crack": (cpos_i, cret_i, cturn_i),
                                 "cross": (xpos_i, xret_i, xturn_i),
                                 "bzwti": (bpos, bret, bturn)}, oos_idx, isw_idx)
    so_i = stats_book(neti, ["crack", "cross", "bzwti"], oos_idx, isw_idx)[3]
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        perm = rng.permutation(len(full_idx))
        mw = pd.Series(mwin.to_numpy()[perm], index=full_idx)
        cp, cr, ct = leg_pos(crack_sig, levels["crack_321"], cs, cb, cd,
                             fb.TRAILING_STOP_ON["crack_321"], extra=mw)
        xp, xr, xt = cross_once(levels, cross_z, mw, fb.VT_F2)
        netn = book_stats_positions({"crack": (cp, cr, ct), "cross": (xp, xr, xt),
                                     "bzwti": (bpos, bret, bturn)}, oos_idx, isw_idx)
        sn = stats_book(netn, ["crack", "cross", "bzwti"], oos_idx, isw_idx)[3]
        nc.append(sn["sharpe"] if not np.isnan(sn["sharpe"]) else 0.0)
    log(f"M1 controls: inverted {so_i['sharpe']:.3f}, "
        f"shuffled mean {np.mean(nc):.3f} sd {np.std(nc):.3f}")

    # ------------------------------------------------------------------
    log("\n=== M2: cold-weather vehicle demand (NYC T2M) ===")
    t2m = read_csv(WEA / "raw_T2M_NYC.csv").reindex(full_idx)
    sm_z = (t2m - same_month_expanding_mean(t2m)) / same_month_expanding_std(t2m)
    zim = t2m.index.month.to_numpy()
    cold = pd.Series((sm_z <= COLD_Z) & pd.Series([m in WINTER for m in zim], index=full_idx),
                     index=full_idx)
    rows2 = []
    for leg_name, lvl in [("crack_gas", levels["crack_gas"]), ("crack_ho", levels["crack_ho"])]:
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        for h in (10, 20):
            fwd = (lvl.shift(-h) - lvl) / base
            cold_days = fwd[cold & base.notna()].dropna()
            warm_days = fwd[~cold & pd.Series(
                [m in WINTER for m in zim], index=full_idx) & base.notna()].dropna()
            log(f"  {leg_name} fwd{h}: cold n={len(cold_days)} mean {cold_days.mean()*100:.3f}%  "
                f"winter-noncold n={len(warm_days)} mean {warm_days.mean()*100:.3f}%")
            rows2.append({"leg": leg_name, "h": h, "cold_n": len(cold_days),
                          "cold_mean": cold_days.mean(), "warm_mean": warm_days.mean()})
    # control: shuffle cold labels among winter days
    winter_pos = np.where(cold.to_numpy() | pd.Series([m in WINTER for m in zim], index=full_idx).to_numpy())[0]
    for leg_name, lvl in [("crack_gas", levels["crack_gas"])]:
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        fwd = (lvl.shift(-10) - lvl) / base
        real = fwd[cold & base.notna()].dropna().mean()
        nc2 = []
        for i in range(NC):
            rng = np.random.default_rng(NC_SEED + i)
            sub = fwd.iloc[winter_pos].dropna()
            lab = rng.random(len(sub)) < (cold.iloc[winter_pos].sum() / max(len(winter_pos), 1))
            nc2.append(sub[lab].mean())
        log(f"  control crack_gas fwd10: real {real*100:.3f}%  shuffled mean "
            f"{np.mean(nc2)*100:.3f}% sd {np.std(nc2)*100:.3f}%")
    pd.DataFrame(rows2).to_csv(ROOT / "results" / "batch1_cold.csv", index=False)

    # ------------------------------------------------------------------
    log("\n=== M3: fuel blend windows ===")
    mon = full_idx.month.to_numpy()
    day = full_idx.day.to_numpy()
    spring = ((mon == 3) & (day >= 20)) | ((mon == 4) & (day <= 15))
    fall = mon == 9
    win = spring | fall
    zg, sg, bg, dg = leg_ready(levels["crack_gas"], fb.VT_F1)
    base_g = b4.base_of(levels["crack_gas"]).shift(1).replace(0.0, np.nan)
    rel_g = levels["crack_gas"].diff() / base_g
    fwd20g = (levels["crack_gas"].shift(-20) - levels["crack_gas"]) / base_g
    vol20g = rel_g.rolling(20, min_periods=10).std().shift(-19) * np.sqrt(252)
    ins = win & base_g.notna() & fwd20g.notna()
    out = ~win & base_g.notna() & fwd20g.notna()
    log(f"  crack_gas: in-window n={int(ins.sum())} zmean {zg[ins].mean():.3f} "
        f"fwd20 {fwd20g[ins].mean()*100:.3f}% vol {vol20g[ins].mean()*100:.2f}%")
    log(f"  crack_gas: out-window n={int(out.sum())} zmean {zg[out].mean():.3f} "
        f"fwd20 {fwd20g[out].mean()*100:.3f}% vol {vol20g[out].mean()*100:.2f}%")
    nc3 = []
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        lab = rng.random(len(full_idx)) < (win.sum() / len(full_idx))
        nc3.append(fwd20g[lab & fwd20g.notna()].mean())
    log(f"  control fwd20 in-window: real {fwd20g[ins].mean()*100:.3f}%  "
        f"shuffled mean {np.mean(nc3)*100:.3f}% sd {np.std(nc3)*100:.3f}%")

    # ------------------------------------------------------------------
    log("\n=== M7: norm drift diagnostics ===")
    lvl = levels["crack_321"]
    util_w = read_csv(EIA / "raw_WPULEUS3.csv")
    rows7 = []
    for m in range(1, 13):
        for tag, lo, hi in (("07-15", "2007-01-01", "2015-12-31"),
                            ("16-26", "2016-01-01", "2026-12-31")):
            seg = lvl.loc[lo:hi]
            segm = seg[seg.index.month == m]
            rows7.append({"metric": "crack_321", "month": m, "period": tag,
                          "mean": segm.mean(), "std": segm.std()})
    utilm = util_w
    for tag, lo, hi in (("07-15", "2007-01-01", "2015-12-31"), ("16-26", "2016-01-01", "2026-12-31")):
        seg = utilm.loc[lo:hi]
        rows7.append({"metric": "utilization", "month": 0, "period": tag,
                      "mean": seg.mean(), "std": seg.std()})
    for r in rows7:
        log(f"  {r['metric']:<12} month {r['month']:>2} {r['period']} mean {r['mean']:.2f} "
            f"std {r['std']:.2f}")
    pd.DataFrame(rows7).to_csv(ROOT / "results" / "batch1_drift.csv", index=False)

    # ------------------------------------------------------------------
    log("\n=== M9: multi-crush basket + depth ===")
    zgas, sgas, bgas, dgas = leg_ready(levels["crack_gas"], fb.VT_F1)
    zho, sho, bho, dho = leg_ready(levels["crack_ho"], fb.VT_F1)
    sig_g = state_machine(zgas)
    sig_h = state_machine(zho)
    dm_g = pd.Series(np.where(sig_g.to_numpy() != 0,
                              np.clip(1 + DEPTH_K * ((zgas.abs().to_numpy() - 0.75)), 1.0, 2.0), 1.0),
                     index=full_idx)
    dm_h = pd.Series(np.where(sig_h.to_numpy() != 0,
                              np.clip(1 + DEPTH_K * ((zho.abs().to_numpy() - 0.75)), 1.0, 2.0), 1.0),
                     index=full_idx)
    flat = {"crack_gas": leg_pos(sig_g, levels["crack_gas"], sgas, bgas, dgas,
                                 fb.TRAILING_STOP_ON["crack_321"]),
            "crack_ho": leg_pos(sig_h, levels["crack_ho"], sho, bho, dho,
                                fb.TRAILING_STOP_ON["crack_ho"]),
            "bzwti": (bpos, bret, bturn)}
    depth = {"crack_gas": leg_pos(sig_g, levels["crack_gas"], sgas, bgas, dgas,
                                  fb.TRAILING_STOP_ON["crack_321"], extra=dm_g),
             "crack_ho": leg_pos(sig_h, levels["crack_ho"], sho, bho, dho,
                                 fb.TRAILING_STOP_ON["crack_ho"], extra=dm_h),
             "bzwti": (bpos, bret, bturn)}
    for tag, parts in (("champion", champ), ("basket_flat", flat), ("basket_depth", depth)):
        si2, so2, siov2, soov2 = stats_book(book_stats_positions(parts, oos_idx, isw_idx),
                                            list(parts), oos_idx, isw_idx)
        log(f"  {tag:<13} OOS raw {so2['sharpe']:.3f} ({so2['cagr']*100:.2f}%, "
            f"DD {so2['maxdd']*100:.2f}%)  ov {soov2['sharpe']:.3f} "
            f"({soov2['cagr']*100:.2f}%, DD {soov2['maxdd']*100:.2f}%)  "
            f"IS ov {siov2['sharpe']:.3f}")
    nc9 = []
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        pm = rng.permutation(len(full_idx))
        dm_g_s = pd.Series(dm_g.to_numpy()[pm], index=full_idx)
        dm_h_s = pd.Series(dm_h.to_numpy()[pm], index=full_idx)
        parts = {"crack_gas": leg_pos(sig_g, levels["crack_gas"], sgas, bgas, dgas,
                                      fb.TRAILING_STOP_ON["crack_321"], extra=dm_g_s),
                 "crack_ho": leg_pos(sig_h, levels["crack_ho"], sho, bho, dho,
                                     fb.TRAILING_STOP_ON["crack_ho"], extra=dm_h_s),
                 "bzwti": (bpos, bret, bturn)}
        sn = stats_book(book_stats_positions(parts, oos_idx, isw_idx),
                        list(parts), oos_idx, isw_idx)[3]
        nc9.append(sn["sharpe"] if not np.isnan(sn["sharpe"]) else 0.0)
    log(f"  depth control: real depth ov "
        f"{stats_book(book_stats_positions(depth, oos_idx, isw_idx), list(depth), oos_idx, isw_idx)[3]['sharpe']:.3f}  "
        f"shuffled mean {np.mean(nc9):.3f} sd {np.std(nc9):.3f}")

    log("\nBatch 1 done. Results in results/batch1_*.csv")


if __name__ == "__main__":
    main()
