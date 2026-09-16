"""Phase 3 harness: directional flow tilts from EIA weekly data.

Preregistered in research/phase3_flow_model.md (concrete rules committed
before measuring). No parameters fitted here.

Tilts (position multipliers, never switches):
  T1 utilization (crack_321, cross): util_z <= -1 -> 1.25, >= +1 -> 0.75
  T2 demand via product draw (crack_321, cross): draw_z >= +1 -> 1.25,
     <= -1 -> 0.75
  T3 Cushing fullness (bzwti): fullness >= 0.85 and draw_z >= +1 -> 1.25;
     fullness >= 0.85 and draw_z <= -1 -> 0.75
  T4 combined

Feature pipeline: weekly changes -> same-month expanding z (min 12) ->
availability = week date + 6 days -> forward-fill onto daily panel ->
scale = tilt.shift(1).

Controls per tilt: shuffled timing (20 seeds) and sign flip.
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

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

MIN_OBS = 12
LAG_DAYS = 6
FULLNESS_WEEKS = 156
FULLNESS_HI = 0.85
NC_PERMS = 20
NC_SEED = 23
CROSS_LEGS = ["crack_321", "crack_gas", "crack_ho"]


def log(msg: str) -> None:
    print(msg, flush=True)


def same_month_z(series: pd.Series, min_obs: int = MIN_OBS) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for month in range(1, 13):
        dates = s.index[s.index.month == month]
        for date in dates:
            past = s[(s.index < date) & (s.index.month == month)]
            if len(past) < min_obs:
                continue
            sd = past.std(ddof=1)
            if pd.notna(sd) and sd > 1e-12:
                out.loc[date] = (s.loc[date] - past.mean()) / sd
    return out.clip(-8.0, 8.0)


def read_series(code: str) -> pd.Series:
    df = pd.read_csv(EIA / f"raw_{code}.csv", index_col=0, parse_dates=True)
    return df["close"].astype(float)


def daily_state(weekly: pd.Series, index: pd.Index) -> pd.Series:
    """Availability = week date + lag, forward-filled onto daily index."""
    av = weekly.copy()
    av.index = av.index + pd.Timedelta(days=LAG_DAYS)
    av = av[~av.index.duplicated(keep="last")].sort_index()
    idx = pd.DatetimeIndex(pd.to_datetime(index))
    expanded = av.reindex(av.index.union(idx)).sort_index().ffill()
    return expanded.reindex(idx)


def crack_sig(level: pd.Series) -> pd.Series:
    """v1 F1 state machine: enter long z <= -0.75, exit z >= -0.5."""
    z = fb.seasonal_z(level)
    zz = z.to_numpy(dtype=float)
    vals = np.zeros(len(level), dtype=float)
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
    return pd.Series(vals, index=level.index)


def f4_sig(level: pd.Series) -> pd.Series:
    """v1 F4 state machine: two-sided Brent-WTI z reversion."""
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


def build_tilted_leg(level, sig: pd.Series, tilt: pd.Series, vt: float,
                     trailing_stop: bool):
    scale = tilt.reindex(level.index).fillna(1.0).shift(1).fillna(1.0)
    raw = sig * b4.fixed_vol_scale(level, vt) * scale
    pos = b4.leg_risk(raw, level, trailing_stop=trailing_stop).fillna(0.0)
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    ret = (pos.shift(1).fillna(0.0) * level.diff() / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    return pos, ret, turn


def cross_tilted(levels, tilt: pd.Series, vt: float):
    """v1 F2 per-leg most-crushed with per-leg tilt."""
    zdf = pd.DataFrame({k: fb.seasonal_z(levels[k]) for k in CROSS_LEGS})
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
                chosen.iloc[i] = CROSS_LEGS.index(k)
    leg_pos, leg_ret, leg_turn = {}, {}, {}
    for li, leg in enumerate(CROSS_LEGS):
        lvl = levels[leg]
        on = chosen == li
        sc = tilt.reindex(lvl.index).fillna(1.0).shift(1).fillna(1.0)
        raw = (pd.Series(1.0, index=lvl.index).where(on, 0.0)
               * b4.fixed_vol_scale(lvl, vt) * sc)
        p = b4.leg_risk(raw, lvl, trailing_stop=False).fillna(0.0)
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        leg_pos[leg] = p
        leg_ret[leg] = (p.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
        leg_turn[leg] = p.diff().abs().fillna(0.0)
    total_pos = pd.DataFrame(leg_pos).sum(axis=1)
    total_ret = pd.DataFrame(leg_ret).sum(axis=1).fillna(0.0)
    total_turn = pd.DataFrame(leg_turn).sum(axis=1)
    return total_pos.rename("cross"), total_ret.rename("cross"), total_turn.rename("cross")


def book_stats(net: pd.DataFrame, names, oos_idx, isw_idx):
    w = b4.weight_scheme(net[names], "EQ")
    bk = b4.book_returns(net, names, w)
    si_raw = b4.stats(bk.loc[isw_idx.intersection(bk.index)])
    so_raw = b4.stats(bk.loc[oos_idx.intersection(bk.index)])
    si_ov = b4.stats(b4.apply_overlay(bk).loc[isw_idx.intersection(bk.index)])
    so_ov = b4.stats(b4.apply_overlay(bk).loc[oos_idx.intersection(bk.index)])
    return si_raw, so_raw, si_ov, so_ov


def build_book(c_tilt, x_tilt, b_tilt, oos_idx, isw_idx):
    cpos, cret, cturn = build_tilted_leg(levels["crack_321"], crack_s, c_tilt,
                                         fb.VT_F1, fb.TRAILING_STOP_ON["crack_321"])
    xpos, xret, xturn = cross_tilted(levels, x_tilt, fb.VT_F2)
    bpos, bret, bturn = build_tilted_leg(levels["bzwti"], f4_s, b_tilt,
                                         fb.VT_F4, fb.TRAILING_STOP_ON["bzwti"])
    net = b4.apply_costs({"crack": cpos, "cross": xpos, "bzwti": bpos},
                         {"crack": cret, "cross": xret, "bzwti": bret},
                         turnover={"crack": cturn, "cross": xturn, "bzwti": bturn})
    for col in net.columns:
        net[col] = net[col].fillna(0.0)
    return book_stats(net, ["crack", "cross", "bzwti"], oos_idx, isw_idx)


def label_tilts(label, flip=False):
    t1 = tilt1(flip)
    t2 = tilt2(flip)
    t3 = tilt3(flip)
    if label == "T1":
        return t1, t1, default_tilt
    if label == "T2":
        return t2, t2, default_tilt
    if label == "T3":
        return default_tilt, default_tilt, t3
    if label == "T4":
        return (t1 * t2), (t1 * t2), t3
    return default_tilt, default_tilt, default_tilt


def main() -> None:
    global levels, crack_s, f4_s, default_tilt, tilt1, tilt2, tilt3
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    isw_idx = b4.window(pd.DataFrame(index=full_idx), b4.IS_START, full_idx.max()).index
    oos_idx = b4.window(pd.DataFrame(index=full_idx), b4.OOS_START, b4.IS_START).index

    gas = read_series("WGTSTUS1")
    dist = read_series("WDISTUS1")
    util = read_series("WPULEUS3")
    cush = read_series("W_EPC0_SAX_YCUOK_MBBL")

    util_z_d = daily_state(same_month_z(util.diff()), full_idx)
    prod_draw_d = daily_state(-same_month_z((gas + dist).diff()), full_idx)
    cush_draw_d = daily_state(-same_month_z(cush.diff()), full_idx)
    fullness_d = daily_state(cush / cush.rolling(FULLNESS_WEEKS, min_periods=60).max(),
                             full_idx)

    def tilt1(t=False):
        z = util_z_d if not t else -util_z_d
        return pd.Series(np.select([z <= -1.0, z >= 1.0], [1.25, 0.75], default=1.0),
                         index=full_idx)

    def tilt2(t=False):
        z = prod_draw_d if not t else -prod_draw_d
        return pd.Series(np.select([z >= 1.0, z <= -1.0], [1.25, 0.75], default=1.0),
                         index=full_idx)

    def tilt3(t=False):
        full = fullness_d.fillna(0.0)
        z = cush_draw_d if not t else -cush_draw_d
        hi = full >= FULLNESS_HI
        up = hi & (z >= 1.0)
        dn = hi & (z <= -1.0)
        return pd.Series(np.select([up, dn], [1.25, 0.75], default=1.0), index=full_idx)

    default_tilt = pd.Series(1.0, index=full_idx)
    crack_s = crack_sig(levels["crack_321"])
    f4_s = f4_sig(levels["bzwti"])

    rows = []
    log(f"{'book':<4} {'var':<4} {'IS Sh':>7} {'IS DD':>8} | {'OOS Sh':>7} "
        f"{'OOS CAGR':>8} {'OOS DD':>8} {'OOS vol':>7} {'worst':>7}")
    for label in ("A", "T1", "T2", "T3", "T4"):
        c_t, x_t, b_t = label_tilts(label)
        si_raw, so_raw, si_ov, so_ov = build_book(c_t, x_t, b_t, oos_idx, isw_idx)
        for tag, (si, so) in (("raw", (si_raw, so_raw)), ("ov", (si_ov, so_ov))):
            rows.append({"book": label, "variant": tag, "window": "IS",
                         "sharpe": si["sharpe"], "cagr": si["cagr"],
                         "maxdd": si["maxdd"], "vol": si["vol"], "worst": si["worst_day"]})
            rows.append({"book": label, "variant": tag, "window": "OOS",
                         "sharpe": so["sharpe"], "cagr": so["cagr"],
                         "maxdd": so["maxdd"], "vol": so["vol"], "worst": so["worst_day"]})
        log(f"{label:<4} {'raw':<4} {si_raw['sharpe']:7.2f} {si_raw['maxdd']*100:7.2f}% | "
            f"{so_raw['sharpe']:7.2f} {so_raw['cagr']*100:7.2f}% {so_raw['maxdd']*100:7.2f}% "
            f"{so_raw['vol']*100:6.1f}% {so_raw['worst_day']*100:6.2f}%")
        log(f"{label:<4} {'ov':<4} {si_ov['sharpe']:7.2f} {si_ov['maxdd']*100:7.2f}% | "
            f"{so_ov['sharpe']:7.2f} {so_ov['cagr']*100:7.2f}% {so_ov['maxdd']*100:7.2f}% "
            f"{so_ov['vol']*100:6.1f}% {so_ov['worst_day']*100:6.2f}%")

    ref = next(r for r in rows if r["book"] == "A" and r["variant"] == "ov" and r["window"] == "OOS")
    log(f"\nBaseline A ov OOS Sharpe: {ref['sharpe']:.6f} (reference 0.8621579162152395)")

    log("\nControls (OOS overlaid book Sharpe):")
    for label in ("T1", "T2", "T3", "T4"):
        real = next(r for r in rows if r["book"] == label and r["variant"] == "ov" and r["window"] == "OOS")
        fc, fx, fb2 = label_tilts(label, flip=True)
        so_f = build_book(fc, fx, fb2, oos_idx, isw_idx)[3]
        rows.append({"book": label + "_flip", "variant": "ov", "window": "OOS",
                     "sharpe": so_f["sharpe"], "cagr": so_f["cagr"],
                     "maxdd": so_f["maxdd"], "vol": so_f["vol"], "worst": so_f["worst_day"]})
        rc, rx, rb = label_tilts(label)
        nc = []
        for i in range(NC_PERMS):
            rng = np.random.default_rng(NC_SEED + i)
            perm = rng.permutation(len(full_idx))
            c_p = pd.Series(rc.to_numpy()[perm], index=full_idx)
            x_p = pd.Series(rx.to_numpy()[perm], index=full_idx)
            b_p = pd.Series(rb.to_numpy()[perm], index=full_idx)
            so_n = build_book(c_p, x_p, b_p, oos_idx, isw_idx)[3]
            nc.append(so_n["sharpe"] if not np.isnan(so_n["sharpe"]) else 0.0)
        log(f"  {label}: real {real['sharpe']:.3f}  flip {so_f['sharpe']:.3f}  "
            f"shuffled mean {np.mean(nc):.3f} sd {np.std(nc):.3f}")
        rows.append({"book": label + "_nc", "variant": "ov", "window": "OOS",
                     "sharpe": float(np.mean(nc)), "cagr": float(np.std(nc)),
                     "maxdd": 0.0, "vol": 0.0, "worst": 0.0})

    with open(ROOT / "results" / "phase3_results.csv", "w", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=["book", "variant", "window",
                                             "sharpe", "cagr", "maxdd", "vol", "worst"])
        wcsv.writeheader()
        wcsv.writerows(rows)
    log("\nSaved results/phase3_results.csv")


if __name__ == "__main__":
    main()
