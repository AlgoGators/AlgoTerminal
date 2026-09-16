"""Batch 2 harness: alpha source map medium items.

Preregistered in research/batch2_alpha_map.md. No parameters fitted.

Sections:
  L4  electrical load via HDD/CDD degree days (source 4)
  L5  other products: distillate winter peak + propane gauge (source 5)
  L6  demand/supply confirmatory retest, building tilt (source 6)
  L8  tightness-ending short entry (source 8)
  L12 Brent-WTI crude-glut conditioning (source 12)
"""
from __future__ import annotations

import importlib.util
import csv
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
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
UTIL_PIN = 90.0
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
        sd[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = sd
    return out


def sm_z(s: pd.Series, min_obs: int = 30) -> pd.Series:
    return ((s - same_month_expanding_mean(s, min_obs))
            / same_month_expanding_std(s, min_obs)).clip(-8.0, 8.0)


def daily_state(weekly: pd.Series, index: pd.Index) -> pd.Series:
    av = weekly.copy()
    av.index = av.index + pd.Timedelta(days=6)
    av = av[~av.index.duplicated(keep="last")].sort_index()
    idx = pd.DatetimeIndex(pd.to_datetime(index))
    return av.reindex(av.index.union(idx)).sort_index().ffill().reindex(idx)


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


def f4_sig(level: pd.Series) -> pd.Series:
    prev = level.shift(1)
    mean = prev.rolling(60, min_periods=30).mean()
    std = prev.rolling(60, min_periods=30).std()
    z = ((prev - mean) / std).replace([np.inf, -np.inf], np.nan)
    zz = z.to_numpy(dtype=float)
    vals = np.zeros(len(level), dtype=float)
    state = 0.0
    for i in range(len(level)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if state == 0.0:
            if zz[i] < -fb.F4_ENTRY:
                state = 1.0
            elif zz[i] > fb.F4_ENTRY:
                state = -1.0
        elif state == 1.0:
            if zz[i] >= fb.F4_EXIT:
                state = 0.0
        else:
            if zz[i] <= fb.F4_EXIT:
                state = 0.0
        vals[i] = state
    return pd.Series(vals, index=level.index)


def cross_once(levels, zdf, tilt, vt, sign_fn=None):
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
    net = b4.apply_costs({k: v[0] for k, v in parts.items()},
                         {k: v[1] for k, v in parts.items()},
                         turnover={k: v[2] for k, v in parts.items()})
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


def leg_stats(parts, name, oos_idx):
    net = b4.apply_costs({name: parts[0]}, {name: parts[1]}, turnover={name: parts[2]})
    return b4.stats(net[name].loc[oos_idx.intersection(net.index)])


def short_stretch_sig(z: pd.Series, conf: pd.Series) -> pd.Series:
    zz = z.to_numpy(dtype=float)
    cc = conf.shift(1).fillna(False).to_numpy(dtype=bool)
    vals = np.zeros(len(z), dtype=float)
    state = 0.0
    for i in range(len(z)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if state == 0.0 and zz[i] >= 0.75 and cc[i]:
            state = -1.0
        elif state == -1.0 and zz[i] <= 0.5:
            state = 0.0
        vals[i] = state
    return pd.Series(vals, index=z.index)


def cross_short_once(levels, zdf, conf, vt):
    arr = zdf.to_numpy(dtype=float)
    cols = list(zdf.columns)
    idx = zdf.index
    cc = conf.shift(1).fillna(False).to_numpy(dtype=bool)
    chosen = pd.Series(np.nan, index=idx, dtype=float)
    valid = zdf.notna().all(axis=1)
    for i in range(len(zdf)):
        if valid.iloc[i] and cc[i]:
            row = arr[i]
            if np.isnan(row).all():
                continue
            k = cols[int(np.nanargmax(row))]
            if row[int(np.nanargmax(row))] >= 0.75:
                chosen.iloc[i] = CROSS_LEGS.index(k)
    leg_p, leg_r, leg_t = {}, {}, {}
    for li, leg in enumerate(CROSS_LEGS):
        lvl = levels[leg]
        on = chosen == li
        raw = pd.Series(-1.0, index=lvl.index).where(on, 0.0) * b4.fixed_vol_scale(lvl, vt)
        p = b4.leg_risk(raw, lvl, trailing_stop=False).fillna(0.0)
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        leg_p[leg] = p
        leg_r[leg] = (p.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
        leg_t[leg] = p.diff().abs().fillna(0.0)
    return (pd.DataFrame(leg_p).sum(axis=1).rename("cross"),
            pd.DataFrame(leg_r).sum(axis=1).fillna(0.0).rename("cross"),
            pd.DataFrame(leg_t).sum(axis=1).rename("cross"))


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    isw_idx = b4.window(pd.DataFrame(index=full_idx), b4.IS_START, full_idx.max()).index
    oos_idx = b4.window(pd.DataFrame(index=full_idx), b4.OOS_START, b4.IS_START).index

    fac4, rets4, turn4 = b4.build_v4(levels, None)
    names4 = ["crack_321", "cross_sectional", "bzwti"]
    champ = {n: (fac4[n], rets4[n], turn4[n]) for n in names4}

    # features
    util_w = read_csv(EIA / "raw_WPULEUS3.csv")
    util_d = daily_state(util_w, full_idx)
    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)          # + = build
    crude_z = daily_state(sm_z(read_csv(EIA / "raw_WCESTUS1.csv")), full_idx)
    prop_z = daily_state(sm_z(read_csv(EIA / "raw_WPRSTUS1.csv")), full_idx)
    t2m = read_csv(WEA / "raw_T2M_NYC.csv").reindex(full_idx)
    hdd = pd.Series(np.maximum(0.0, 18.0 - t2m), index=full_idx)
    cdd = pd.Series(np.maximum(0.0, t2m - 18.0), index=full_idx)
    hdd_z = sm_z(hdd)
    cdd_z = sm_z(cdd)
    power = pd.Series((hdd_z >= 1.0) | (cdd_z >= 1.0), index=full_idx)

    rz, rs, rb, rd = leg_ready(levels["crack_321"], fb.VT_F1)
    crack_sig = state_machine(rz)
    z_ho, s_ho, b_ho, d_ho = leg_ready(levels["crack_ho"], fb.VT_F1)
    ho_sig = state_machine(z_ho)
    cross_z = pd.DataFrame({k: fb.seasonal_z(levels[k]) for k in CROSS_LEGS})
    bz, bs, bb, bd = leg_ready(levels["bzwti"], fb.VT_F4)
    f4_s = f4_sig(levels["bzwti"])

    rows = []

    # --------------------------------------------------------------
    log("=== L4: electrical load (HDD/CDD degree days) ===")
    tilt4 = pd.Series(np.where(power.to_numpy(), 1.25, 1.0), index=full_idx)
    cpos, cret, cturn = leg_pos(crack_sig, levels["crack_321"], rs, rb, rd,
                                fb.TRAILING_STOP_ON["crack_321"], extra=tilt4)
    xpos, xret, xturn = cross_once(levels, cross_z, tilt4, fb.VT_F2)
    parts = {"crack": (cpos, cret, cturn), "cross": (xpos, xret, xturn),
             "bzwti": champ["bzwti"]}
    si, so, siov, soov = stats_book(book_stats_positions(parts, oos_idx, isw_idx),
                                    list(parts), oos_idx, isw_idx)
    ref = stats_book(book_stats_positions(champ, oos_idx, isw_idx), names4, oos_idx, isw_idx)
    log(f"  L4 real: OOS ov {soov['sharpe']:.3f} (champion {ref[3]['sharpe']:.3f}), "
        f"IS ov {siov['sharpe']:.3f}")
    nc = []
    inv = pd.Series(np.where(power.to_numpy(), 0.75, 1.25), index=full_idx)
    cpi, cri, cti = leg_pos(crack_sig, levels["crack_321"], rs, rb, rd,
                            fb.TRAILING_STOP_ON["crack_321"], extra=inv)
    xpi, xri, xti = cross_once(levels, cross_z, inv, fb.VT_F2)
    so_i = stats_book(book_stats_positions({"crack": (cpi, cri, cti),
                                            "cross": (xpi, xri, xti),
                                            "bzwti": champ["bzwti"]}, oos_idx, isw_idx),
                      ["crack", "cross", "bzwti"], oos_idx, isw_idx)[3]
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        pw = pd.Series(power.to_numpy()[rng.permutation(len(full_idx))], index=full_idx)
        t = pd.Series(np.where(pw.to_numpy(), 1.25, 1.0), index=full_idx)
        cp, cr, ct = leg_pos(crack_sig, levels["crack_321"], rs, rb, rd,
                             fb.TRAILING_STOP_ON["crack_321"], extra=t)
        xp, xr, xt = cross_once(levels, cross_z, t, fb.VT_F2)
        sn = stats_book(book_stats_positions({"crack": (cp, cr, ct),
                                              "cross": (xp, xr, xt),
                                              "bzwti": champ["bzwti"]}, oos_idx, isw_idx),
                        ["crack", "cross", "bzwti"], oos_idx, isw_idx)[3]
        nc.append(sn["sharpe"] if not np.isnan(sn["sharpe"]) else 0.0)
    log(f"  L4 controls: inverted {so_i['sharpe']:.3f}, shuffled mean {np.mean(nc):.3f} "
        f"sd {np.std(nc):.3f}")
    rows += [{"section": "L4", "kind": "real", "value": soov["sharpe"]},
             {"section": "L4", "kind": "inverted", "value": so_i["sharpe"]},
             {"section": "L4", "kind": "shuffled_mean", "value": float(np.mean(nc))},
             {"section": "L4", "kind": "shuffled_sd", "value": float(np.std(nc))}]

    # --------------------------------------------------------------
    log("\n=== L5: other products ===")
    winter = pd.Series([m in (12, 1, 2) for m in full_idx.month], index=full_idx)
    tilt_w = pd.Series(np.where(winter.to_numpy(), 1.25, 1.0), index=full_idx)
    ho_plain = leg_pos(ho_sig, levels["crack_ho"], s_ho, b_ho, d_ho,
                       fb.TRAILING_STOP_ON["crack_ho"])
    ho_win = leg_pos(ho_sig, levels["crack_ho"], s_ho, b_ho, d_ho,
                     fb.TRAILING_STOP_ON["crack_ho"], extra=tilt_w)
    tilt_p = pd.Series(np.select([prop_z <= -1.0, prop_z >= 1.0], [1.25, 0.75], 1.0),
                       index=full_idx)
    ho_prop = leg_pos(ho_sig, levels["crack_ho"], s_ho, b_ho, d_ho,
                      fb.TRAILING_STOP_ON["crack_ho"], extra=tilt_p)
    for tag, legp in (("plain", ho_plain), ("winter", ho_win), ("propane", ho_prop)):
        st = leg_stats(legp, "ho", oos_idx)
        log(f"  L5 HO {tag:<8} OOS raw Sh {st['sharpe']:.3f} CAGR {st['cagr']*100:.2f}% "
            f"DD {st['maxdd']*100:.2f}%")
        rows.append({"section": "L5_" + tag, "kind": "oos_raw_sharpe", "value": st["sharpe"]})
    ho4 = {"crack_321": champ["crack_321"], "cross_sectional": champ["cross_sectional"],
           "bzwti": champ["bzwti"], "crack_ho": ho_win}
    si5, so5, siov5, soov5 = stats_book(book_stats_positions(ho4, oos_idx, isw_idx),
                                        list(ho4), oos_idx, isw_idx)
    log(f"  L5 champion+HO-winter 4-leg: OOS ov {soov5['sharpe']:.3f} "
        f"(champion {ref[3]['sharpe']:.3f})")
    rows.append({"section": "L5_book", "kind": "oos_ov_sharpe", "value": soov5["sharpe"]})

    # --------------------------------------------------------------
    log("\n=== L6: demand/supply confirmatory retest (building tilt) ===")
    tilt6 = pd.Series(np.select([prod_z >= 1.0, prod_z <= -1.0], [1.25, 0.75], 1.0),
                      index=full_idx)
    cpos6, cret6, cturn6 = leg_pos(crack_sig, levels["crack_321"], rs, rb, rd,
                                   fb.TRAILING_STOP_ON["crack_321"], extra=tilt6)
    xpos6, xret6, xturn6 = cross_once(levels, cross_z, tilt6, fb.VT_F2)
    parts6 = {"crack": (cpos6, cret6, cturn6), "cross": (xpos6, xret6, xturn6),
              "bzwti": champ["bzwti"]}
    si6, so6, siov6, soov6 = stats_book(book_stats_positions(parts6, oos_idx, isw_idx),
                                        list(parts6), oos_idx, isw_idx)
    log(f"  L6 real: OOS ov {soov6['sharpe']:.3f}, IS ov {siov6['sharpe']:.3f}")
    nc6 = []
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        t = pd.Series(tilt6.to_numpy()[rng.permutation(len(full_idx))], index=full_idx)
        cp, cr, ct = leg_pos(crack_sig, levels["crack_321"], rs, rb, rd,
                             fb.TRAILING_STOP_ON["crack_321"], extra=t)
        xp, xr, xt = cross_once(levels, cross_z, t, fb.VT_F2)
        sn = stats_book(book_stats_positions({"crack": (cp, cr, ct),
                                              "cross": (xp, xr, xt),
                                              "bzwti": champ["bzwti"]}, oos_idx, isw_idx),
                        ["crack", "cross", "bzwti"], oos_idx, isw_idx)[3]
        nc6.append(sn["sharpe"] if not np.isnan(sn["sharpe"]) else 0.0)
    log(f"  L6 control: shuffled mean {np.mean(nc6):.3f} sd {np.std(nc6):.3f}")
    rows += [{"section": "L6", "kind": "oos_ov", "value": soov6["sharpe"]},
             {"section": "L6", "kind": "is_ov", "value": siov6["sharpe"]},
             {"section": "L6", "kind": "shuffled_mean", "value": float(np.mean(nc6))},
             {"section": "L6", "kind": "shuffled_sd", "value": float(np.std(nc6))}]

    # --------------------------------------------------------------
    log("\n=== L8: tightness-ending short entry ===")
    lvl321 = levels["crack_321"]
    regime = (lvl321.shift(1) > lvl321.shift(1).rolling(252, min_periods=126).mean())
    built = prod_z >= 1.0
    confirm = (regime & (util_d >= UTIL_PIN) & built).fillna(False)
    csig = short_stretch_sig(rz, confirm)
    cpos8, cret8, cturn8 = leg_pos(csig, levels["crack_321"], rs, rb, rd,
                                   fb.TRAILING_STOP_ON["crack_321"], extra=None)
    xpos8, xret8, xturn8 = cross_short_once(levels, cross_z, confirm, fb.VT_F2)
    parts8 = {"crack": (cpos8, cret8, cturn8), "cross": (xpos8, xret8, xturn8),
              "bzwti": champ["bzwti"]}
    si8, so8, siov8, soov8 = stats_book(book_stats_positions(parts8, oos_idx, isw_idx),
                                        list(parts8), oos_idx, isw_idx)
    log(f"  L8 real: OOS raw {so8['sharpe']:.3f} (DD {so8['maxdd']*100:.2f}%), "
        f"ov {soov8['sharpe']:.3f} (DD {soov8['maxdd']*100:.2f}%); IS ov {siov8['sharpe']:.3f}")
    nc8 = []
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        cf = pd.Series(confirm.to_numpy()[rng.permutation(len(full_idx))], index=full_idx)
        cs = short_stretch_sig(rz, cf)
        cp, cr, ct = leg_pos(cs, levels["crack_321"], rs, rb, rd,
                             fb.TRAILING_STOP_ON["crack_321"], extra=None)
        xp, xr, xt = cross_short_once(levels, cross_z, cf, fb.VT_F2)
        sn = stats_book(book_stats_positions({"crack": (cp, cr, ct),
                                              "cross": (xp, xr, xt),
                                              "bzwti": champ["bzwti"]}, oos_idx, isw_idx),
                        ["crack", "cross", "bzwti"], oos_idx, isw_idx)[3]
        nc8.append(sn["sharpe"] if not np.isnan(sn["sharpe"]) else 0.0)
    log(f"  L8 control: shuffled confirmations mean {np.mean(nc8):.3f} sd {np.std(nc8):.3f}")
    rows += [{"section": "L8", "kind": "oos_ov", "value": soov8["sharpe"]},
             {"section": "L8", "kind": "is_ov", "value": siov8["sharpe"]},
             {"section": "L8", "kind": "shuffled_mean", "value": float(np.mean(nc8))},
             {"section": "L8", "kind": "shuffled_sd", "value": float(np.std(nc8))}]

    # --------------------------------------------------------------
    log("\n=== L12: Brent-WTI crude-glut conditioning ===")
    tilt12 = pd.Series(np.select([crude_z >= 1.0, crude_z <= -1.0], [1.25, 0.75], 1.0),
                       index=full_idx)
    bp, br, bt = leg_pos(f4_s, levels["bzwti"], bs, bb, bd,
                         fb.TRAILING_STOP_ON["bzwti"], extra=tilt12)
    parts12 = {"crack": champ["crack_321"], "cross": champ["cross_sectional"],
               "bzwti": (bp, br, bt)}
    si12, so12, siov12, soov12 = stats_book(book_stats_positions(parts12, oos_idx, isw_idx),
                                            list(parts12), oos_idx, isw_idx)
    log(f"  L12 real: OOS ov {soov12['sharpe']:.3f} (champion {ref[3]['sharpe']:.3f}), "
        f"IS ov {siov12['sharpe']:.3f}")
    nc12 = []
    inv12 = pd.Series(np.select([crude_z >= 1.0, crude_z <= -1.0], [0.75, 1.25], 1.0),
                      index=full_idx)
    bpi, bri, bti = leg_pos(f4_s, levels["bzwti"], bs, bb, bd,
                            fb.TRAILING_STOP_ON["bzwti"], extra=inv12)
    so_12i = stats_book(book_stats_positions({"crack": champ["crack_321"],
                                              "cross": champ["cross_sectional"],
                                              "bzwti": (bpi, bri, bti)}, oos_idx, isw_idx),
                        ["crack", "cross", "bzwti"], oos_idx, isw_idx)[3]
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        t = pd.Series(tilt12.to_numpy()[rng.permutation(len(full_idx))], index=full_idx)
        cp, cr, ct = leg_pos(f4_s, levels["bzwti"], bs, bb, bd,
                             fb.TRAILING_STOP_ON["bzwti"], extra=t)
        sn = stats_book(book_stats_positions({"crack": champ["crack_321"],
                                              "cross": champ["cross_sectional"],
                                              "bzwti": (cp, cr, ct)}, oos_idx, isw_idx),
                        ["crack", "cross", "bzwti"], oos_idx, isw_idx)[3]
        nc12.append(sn["sharpe"] if not np.isnan(sn["sharpe"]) else 0.0)
    log(f"  L12 controls: inverted {so_12i['sharpe']:.3f}, shuffled mean {np.mean(nc12):.3f} "
        f"sd {np.std(nc12):.3f}")
    rows += [{"section": "L12", "kind": "oos_ov", "value": soov12["sharpe"]},
             {"section": "L12", "kind": "is_ov", "value": siov12["sharpe"]},
             {"section": "L12", "kind": "inverted", "value": so_12i["sharpe"]},
             {"section": "L12", "kind": "shuffled_mean", "value": float(np.mean(nc12))},
             {"section": "L12", "kind": "shuffled_sd", "value": float(np.std(nc12))}]

    pd.DataFrame(rows).to_csv(ROOT / "results" / "batch2_results.csv", index=False)
    log("\nSaved results/batch2_results.csv")


if __name__ == "__main__":
    main()
