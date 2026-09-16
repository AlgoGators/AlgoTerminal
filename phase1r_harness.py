"""Phase 1R harness: mechanism-based short candidates S1-S4.

Preregistered in research/phase1r_short_side_mechanics.md. No parameters
fitted here.

Candidates (all causal):
  S1 easing-fade        short, 5d z change < -0.2
  S2 acceleration-ride  long,  5d z change > 0
  S3 regime-conditional short, level > trailing 252d mean (shifted)
  S4 seasonal-top fade  short, month in {3,4,9,10}

Each runs on crack_321 and on the most-stretched cross-sectional leg.
Book per candidate = crack leg + cross leg + bzwti, equal weight.
Negative control: time-shuffle each candidate signal, 20 permutations.

Performance: all level statistics (seasonal z, vol scale, base, diff)
are computed once. Only the signal depends on the permutation.
"""
from __future__ import annotations

import importlib.util
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
ENGINE = ROOT / "engine"
PANEL = ENGINE / "panel_v2.parquet"

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

ENTRY = 0.75
EXIT = 0.5
D5 = 0.2
SHOULDER_MONTHS = (3, 4, 9, 10)
REGIME_LOOKBACK = 252
VT_CRACK = fb.VT_F1
VT_XS = fb.VT_F2
NC_PERMS = 20
NC_SEED = 23
CROSS_LEGS = ["crack_321", "crack_gas", "crack_ho"]


def log(msg: str) -> None:
    print(msg, flush=True)


def crack_sig(z: pd.Series, level: pd.Series, mode: str) -> pd.Series:
    """State machine for one crack candidate. Values: -1, 0, +1."""
    zz = z.to_numpy(dtype=float)
    d5 = (z - z.shift(5)).to_numpy(dtype=float)
    idx = z.index
    months = np.array([m for m in idx.month], dtype=int)
    reg = (level.shift(1)
           > level.shift(1).rolling(REGIME_LOOKBACK, min_periods=126).mean())
    regv = reg.to_numpy(dtype=float)
    vals = np.zeros(len(z), dtype=float)
    state = 0.0
    for i in range(len(z)):
        if np.isnan(zz[i]) or np.isnan(d5[i]):
            vals[i] = 0.0
            continue
        r_ok = not np.isnan(regv[i]) and bool(regv[i])
        if mode == "S1":
            if state == 0.0 and zz[i] >= ENTRY and d5[i] < -D5:
                state = -1.0
            elif state == -1.0 and zz[i] <= EXIT:
                state = 0.0
        elif mode == "S2":
            if state == 0.0 and zz[i] >= ENTRY and d5[i] > 0.0:
                state = 1.0
            elif state == 1.0 and (d5[i] < 0.0 or zz[i] <= EXIT):
                state = 0.0
        elif mode == "S3":
            if state == 0.0 and zz[i] >= ENTRY and r_ok:
                state = -1.0
            elif state == -1.0 and zz[i] <= EXIT:
                state = 0.0
        elif mode == "S4":
            if state == 0.0 and zz[i] >= ENTRY and months[i] in SHOULDER_MONTHS:
                state = -1.0
            elif state == -1.0 and zz[i] <= EXIT:
                state = 0.0
        else:
            raise ValueError(mode)
        vals[i] = state
    return pd.Series(vals, index=z.index)


def cross_choice(zdf: dict, levels: dict, mode: str, idx) -> pd.Series:
    """Most-stretched leg with candidate condition. Returns sig (-1/0/+1)."""
    frame = pd.DataFrame(zdf)
    arr_z = frame.to_numpy(dtype=float)
    arr_d5 = (frame - frame.shift(5)).to_numpy(dtype=float)
    cols = list(frame.columns)
    regv = {}
    for leg in cols:
        lv = levels[leg]
        regv[leg] = (lv.shift(1)
                     > lv.shift(1).rolling(REGIME_LOOKBACK, min_periods=126).mean()
                     ).to_numpy(dtype=float)
    months = np.array([m for m in idx.month], dtype=int)
    out = np.zeros(len(frame), dtype=float)
    for i in range(len(frame)):
        row = arr_z[i]
        if np.isnan(row).all():
            continue
        col = int(np.nanargmax(row))
        if np.isnan(row[col]) or row[col] < ENTRY:
            continue
        cond = arr_d5[i][col]
        ok = False
        if mode == "S1":
            ok = not np.isnan(cond) and cond < -D5
        elif mode == "S2":
            ok = not np.isnan(cond) and cond > 0.0
        elif mode == "S3":
            rv = regv[cols[col]][i]
            ok = not np.isnan(rv) and bool(rv)
        elif mode == "S4":
            ok = months[i] in SHOULDER_MONTHS
        if ok:
            out[i] = -1.0 if mode != "S2" else 1.0
    return pd.Series(out, index=idx)


def cross_leg_from_sig(sig: pd.Series, levels: dict, cross_z: dict, scales: dict,
                       bases: dict, diffs: dict, vt: float):
    """Per-leg risk/returns from a daily cross signal placed on the
    most-stretched leg of that day."""
    idx = sig.index
    s = sig.to_numpy(dtype=float)
    arr = pd.DataFrame(cross_z).to_numpy(dtype=float)
    leg_pos = {}
    leg_ret = {}
    leg_turn = {}
    for li, leg in enumerate(CROSS_LEGS):
        lvl = levels[leg]
        pos_arr = np.zeros(len(sig))
        for i in range(len(sig)):
            if s[i] == 0.0:
                continue
            if np.isnan(arr[i]).all():
                continue
            if int(np.nanargmax(arr[i])) == li:
                pos_arr[i] = s[i]
        raw = pd.Series(pos_arr, index=idx) * scales[leg]
        p = b4.leg_risk(raw, lvl, trailing_stop=False).fillna(0.0)
        leg_pos[leg] = p
        leg_ret[leg] = (p.shift(1).fillna(0.0) * diffs[leg] / bases[leg]).fillna(0.0)
        leg_turn[leg] = p.diff().abs().fillna(0.0)
    total_pos = pd.DataFrame(leg_pos).sum(axis=1)
    total_ret = pd.DataFrame(leg_ret).sum(axis=1).fillna(0.0)
    total_turn = pd.DataFrame(leg_turn).sum(axis=1)
    return total_pos.rename("cross"), total_ret.rename("cross"), total_turn.rename("cross")


def build_leg(level: pd.Series, sig: pd.Series, scale: pd.Series, base: pd.Series,
              diff: pd.Series, trailing_stop: bool):
    raw = sig * scale
    pos = b4.leg_risk(raw, level, trailing_stop=trailing_stop).fillna(0.0)
    ret = (pos.shift(1).fillna(0.0) * diff / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    return pos, ret, turn


def net_frame(pos: dict, ret: dict, turn: dict) -> pd.DataFrame:
    net = b4.apply_costs(pos, ret, turnover=turn)
    for c in net.columns:
        net[c] = net[c].fillna(0.0)
    return net


def book_stats(net: pd.DataFrame, names, oos_idx) -> tuple[dict, dict]:
    w = b4.weight_scheme(net[names], "EQ")
    bk = b4.book_returns(net, names, w)
    so_raw = b4.stats(bk.loc[oos_idx.intersection(bk.index)])
    so_ov = b4.stats(b4.apply_overlay(bk).loc[oos_idx.intersection(bk.index)])
    return so_raw, so_ov


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    isw_idx = b4.window(pd.DataFrame(index=full_idx), b4.IS_START, full_idx.max()).index
    oos_idx = b4.window(pd.DataFrame(index=full_idx), b4.OOS_START, b4.IS_START).index

    fac4, rets4, turn4 = b4.build_v4(levels, None)
    bw = (fac4["bzwti"], rets4["bzwti"], turn4["bzwti"])

    # precompute once
    crack_z = fb.seasonal_z(levels["crack_321"])
    crack_scale = b4.fixed_vol_scale(levels["crack_321"], VT_CRACK)
    crack_base = b4.base_of(levels["crack_321"]).shift(1).replace(0.0, np.nan)
    crack_diff = levels["crack_321"].diff()
    cross_z = {k: fb.seasonal_z(levels[k]) for k in CROSS_LEGS}
    cross_scales = {k: b4.fixed_vol_scale(levels[k], VT_XS) for k in CROSS_LEGS}
    cross_bases = {k: b4.base_of(levels[k]).shift(1).replace(0.0, np.nan) for k in CROSS_LEGS}
    cross_diffs = {k: levels[k].diff() for k in CROSS_LEGS}

    rows = []
    log(f"{'cand':<4} {'leg':<8} {'OOS Sh':>7} {'OOS CAGR':>8} {'OOS DD':>8} | "
        f"{'book raw':>8} {'book ov':>8} {'ov DD':>8} {'worst':>7}")
    for mode in ("S1", "S2", "S3", "S4"):
        crack_s = crack_sig(crack_z, levels["crack_321"], mode)
        cross_s = cross_choice(cross_z, levels, mode, full_idx)
        cpos, cret, cturn = build_leg(levels["crack_321"], crack_s, crack_scale,
                                      crack_base, crack_diff,
                                      trailing_stop=fb.TRAILING_STOP_ON["crack_321"])
        xpos, xret, xturn = cross_leg_from_sig(cross_s, levels, cross_z, cross_scales,
                                               cross_bases, cross_diffs, VT_XS)
        for label, (p, r, t) in {"crack": (cpos, cret, cturn),
                                 "cross": (xpos, xret, xturn)}.items():
            net_leg = b4.apply_costs({label: p}, {label: r}, turnover={label: t})
            st = b4.stats(net_leg[label].loc[oos_idx.intersection(net_leg.index)])
            rows.append({"candidate": mode, "leg": label, "window": "OOS",
                         "sharpe": st["sharpe"], "cagr": st["cagr"],
                         "maxdd": st["maxdd"], "vol": st["vol"], "worst": st["worst_day"]})
            log(f"{mode:<4} {label:<8} {st['sharpe']:7.2f} {st['cagr']*100:7.2f}% "
                f"{st['maxdd']*100:7.2f}%")
        net = net_frame({"crack": cpos, "cross": xpos, "bzwti": bw[0]},
                        {"crack": cret, "cross": xret, "bzwti": bw[1]},
                        {"crack": cturn, "cross": xturn, "bzwti": bw[2]})
        so_raw, so_ov = book_stats(net, ["crack", "cross", "bzwti"], oos_idx)
        rows.append({"candidate": mode, "leg": "book_raw", "window": "OOS",
                     "sharpe": so_raw["sharpe"], "cagr": so_raw["cagr"],
                     "maxdd": so_raw["maxdd"], "vol": so_raw["vol"],
                     "worst": so_raw["worst_day"]})
        rows.append({"candidate": mode, "leg": "book_ov", "window": "OOS",
                     "sharpe": so_ov["sharpe"], "cagr": so_ov["cagr"],
                     "maxdd": so_ov["maxdd"], "vol": so_ov["vol"],
                     "worst": so_ov["worst_day"]})
        log(f"{mode:<4} {'book':<8} {so_raw['sharpe']:7.2f} {so_raw['cagr']*100:7.2f}% "
            f"{so_raw['maxdd']*100:7.2f}% | {so_ov['sharpe']:8.2f} "
            f"{so_ov['maxdd']*100:7.2f}% {so_ov['worst_day']*100:6.2f}%")

    log("\nNegative controls (shuffled signals, OOS overlaid):")
    for mode in ("S1", "S2", "S3", "S4"):
        base_crack_sig = crack_sig(crack_z, levels["crack_321"], mode)
        base_cross_sig = cross_choice(cross_z, levels, mode, full_idx)
        nc = []
        for i in range(NC_PERMS):
            rng = np.random.default_rng(NC_SEED + i)
            perm = rng.permutation(len(full_idx))
            crack_s = pd.Series(base_crack_sig.to_numpy()[perm], index=full_idx)
            cross_s = pd.Series(base_cross_sig.to_numpy()[perm], index=full_idx)
            cpos, cret, cturn = build_leg(levels["crack_321"], crack_s, crack_scale,
                                          crack_base, crack_diff,
                                          trailing_stop=fb.TRAILING_STOP_ON["crack_321"])
            xpos, xret, xturn = cross_leg_from_sig(cross_s, levels, cross_z, cross_scales,
                                                   cross_bases, cross_diffs, VT_XS)
            net = net_frame({"crack": cpos, "cross": xpos, "bzwti": bw[0]},
                            {"crack": cret, "cross": xret, "bzwti": bw[1]},
                            {"crack": cturn, "cross": xturn, "bzwti": bw[2]})
            so = book_stats(net, ["crack", "cross", "bzwti"], oos_idx)[1]
            nc.append(so["sharpe"] if not np.isnan(so["sharpe"]) else 0.0)
        real = next(r for r in rows if r["candidate"] == mode and r["leg"] == "book_ov")
        log(f"  {mode}: real {real['sharpe']:.3f}  shuffled mean {np.mean(nc):.3f} "
            f"sd {np.std(nc):.3f}")
        rows.append({"candidate": mode, "leg": "nc_shuffled", "window": "OOS",
                     "sharpe": float(np.mean(nc)), "cagr": float(np.std(nc)),
                     "maxdd": 0.0, "vol": 0.0, "worst": 0.0})

    with open(ROOT / "results" / "phase1r_results.csv", "w", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=["candidate", "leg", "window",
                                             "sharpe", "cagr", "maxdd", "vol", "worst"])
        wcsv.writeheader()
        wcsv.writerows(rows)
    log("\nSaved results/phase1r_results.csv")


if __name__ == "__main__":
    main()
