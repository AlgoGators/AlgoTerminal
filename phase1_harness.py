"""Phase 1 harness: short-side and asymmetry OOS test on the frozen v2 engine.

Pre-registered in research/phase1_short_side.md. No parameters fitted here.

Books (equal weight over legs, 5bps/20roll, corrected v4 measured basis):
  A = v1 long-only reference (crack_321 + cross_sectional + bzwti)
  B = short-fade only (crack_short + cross_short + bzwti)
  C = balanced reversion (A legs + B legs, equal weight)
  D = split book (left reversion + right momentum)
  E = right-momentum only (crack_mom + cross_mom + bzwti)

Negative control: time-shuffle the short-side signals (20 seeded
permutations) and re-run book B.
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

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

ENTRY = 0.75          # |z| entry for side legs, symmetric with v1 SMR_ENTRY
EXIT = 0.5            # |z| exit, symmetric with v1 SMR_EXIT
XS_ENTRY = 0.5        # cross-side min |z|, symmetric with v1 XS_MIN_Z
VT_CRACK = fb.VT_F1   # 0.50
VT_XS = fb.VT_F2      # 0.50
NC_PERMS = 20
NC_SEED = 23


def side_state(z: pd.Series, mode: str) -> pd.Series:
    """Threshold state machine on seasonal z. Values: -1, 0, +1."""
    zz = z.to_numpy(dtype=float)
    vals = np.zeros(len(z), dtype=float)
    state = 0.0
    for i in range(len(z)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if mode == "long_crush":
            if state == 0.0 and zz[i] <= -ENTRY:
                state = 1.0
            elif state == 1.0 and zz[i] >= -EXIT:
                state = 0.0
        elif mode == "short_stretch":
            if state == 0.0 and zz[i] >= ENTRY:
                state = -1.0
            elif state == -1.0 and zz[i] <= EXIT:
                state = 0.0
        elif mode == "mom_stretch":
            if state == 0.0 and zz[i] >= ENTRY:
                state = 1.0
            elif state == 1.0 and zz[i] <= EXIT:
                state = 0.0
        else:
            raise ValueError(mode)
        vals[i] = state
    return pd.Series(vals, index=z.index)


def build_side_leg(level: pd.Series, vt: float, mode: str,
                   trailing_stop: bool = False):
    """One directional leg with v1 sizing and per-leg risk rules."""
    sig = side_state(fb.seasonal_z(level), mode)
    raw = sig * b4.fixed_vol_scale(level, vt)
    pos = b4.leg_risk(raw, level, trailing_stop=trailing_stop).fillna(0.0)
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    ret = (pos.shift(1).fillna(0.0) * level.diff() / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    return pos, ret, turn


def build_cross_side(levels, side: str, vt: float):
    """Most-crushed (long) or most-stretched (short/momentum) leg, per-leg."""
    legs = ["crack_321", "crack_gas", "crack_ho"]
    zdf = pd.DataFrame({k: fb.seasonal_z(levels[k]) for k in legs})
    arr = zdf.to_numpy(dtype=float)
    cols = list(zdf.columns)
    chosen = pd.Series(np.nan, index=zdf.index, dtype=float)
    valid = zdf.notna().all(axis=1)
    sign = 1.0
    for i in range(len(zdf)):
        if valid.iloc[i]:
            row = arr[i]
            if np.isnan(row).all():
                continue
            if side in ("short", "short_stretch", "mom"):
                k = cols[int(np.nanargmax(row))]
                thr = row[int(np.nanargmax(row))] > XS_ENTRY
            else:
                k = cols[int(np.nanargmin(row))]
                thr = row[int(np.nanargmin(row))] < -XS_ENTRY
            if thr:
                chosen.iloc[i] = legs.index(k)
    if side == "short":
        sign = -1.0
    leg_pos = {}
    leg_ret = {}
    leg_turn = {}
    for li, leg in enumerate(legs):
        lvl = levels[leg]
        on = chosen == li
        scale = b4.fixed_vol_scale(lvl, vt).where(on, 0.0)
        sig = pd.Series(sign, index=lvl.index).where(on, 0.0)
        p = b4.leg_risk(sig * scale, lvl, trailing_stop=False).fillna(0.0)
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        leg_pos[leg] = p
        leg_ret[leg] = (p.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
        leg_turn[leg] = p.diff().abs().fillna(0.0)
    total_pos = pd.DataFrame(leg_pos).sum(axis=1)
    total_ret = pd.DataFrame(leg_ret).sum(axis=1).fillna(0.0)
    total_turn = pd.DataFrame(leg_turn).sum(axis=1)
    return total_pos.rename(side), total_ret.rename(side), total_turn.rename(side)


def net_frame(pos: dict, ret: dict, turn: dict) -> pd.DataFrame:
    net = b4.apply_costs(pos, ret, turnover=turn)
    for c in net.columns:
        net[c] = net[c].fillna(0.0)
    return net


def stats_of(s: pd.Series) -> dict:
    st = b4.stats(s)
    return {"sharpe": st["sharpe"], "cagr": st["cagr"], "maxdd": st["maxdd"],
            "vol": st["vol"], "worst": st["worst_day"]}


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    isw_idx = b4.window(pd.DataFrame(index=df.index), b4.IS_START, df.index.max()).index
    oos_end = b4.IS_START
    oos_idx = b4.window(pd.DataFrame(index=df.index), b4.OOS_START, oos_end).index

    # v1 legs (corrected v4 engine)
    fac4, rets4, turn4 = b4.build_v4(levels, None)
    v1_pos = {k: fac4[k] for k in ("crack_321", "cross_sectional", "bzwti")}
    v1_ret = {k: rets4[k] for k in v1_pos}
    v1_turn = {k: turn4[k] for k in v1_pos}

    # side legs
    crack_long = build_side_leg(levels["crack_321"], VT_CRACK, "long_crush",
                                trailing_stop=fb.TRAILING_STOP_ON["crack_321"])
    crack_short = build_side_leg(levels["crack_321"], VT_CRACK, "short_stretch",
                                 trailing_stop=fb.TRAILING_STOP_ON["crack_321"])
    crack_mom = build_side_leg(levels["crack_321"], VT_CRACK, "mom_stretch",
                               trailing_stop=fb.TRAILING_STOP_ON["crack_321"])
    cross_long = build_cross_side(levels, "long", VT_XS)
    cross_short = build_cross_side(levels, "short", VT_XS)
    cross_mom = build_cross_side(levels, "mom", VT_XS)
    bw = (v1_pos["bzwti"], v1_ret["bzwti"], v1_turn["bzwti"])

    def book(label, legs):
        pos = {n: l[0] for n, l in legs.items()}
        ret = {n: l[1] for n, l in legs.items()}
        turn = {n: l[2] for n, l in legs.items()}
        net = net_frame(pos, ret, turn)
        w = b4.weight_scheme(net[list(legs)], "EQ")
        book = b4.book_returns(net, list(legs), w)
        return label, net, book

    books = {
        "A": book("A", {"crack_321": crack_long, "cross_sectional": cross_long, "bzwti": bw}),
        "B": book("B", {"crack_short": crack_short, "cross_short": cross_short, "bzwti": bw}),
        "C": book("C", {"crack_321": crack_long, "crack_short": crack_short,
                        "cross_sectional": cross_long, "cross_short": cross_short, "bzwti": bw}),
        "D": book("D", {"crack_321": crack_long, "crack_mom": crack_mom,
                        "cross_sectional": cross_long, "cross_mom": cross_mom, "bzwti": bw}),
        "E": book("E", {"crack_mom": crack_mom, "cross_mom": cross_mom, "bzwti": bw}),
    }

    rows = []
    print(f"{'book':<3} {'var':<8} {'IS Sh':>7} {'IS DD':>8} | {'OOS Sh':>7} {'OOS CAGR':>8} {'OOS DD':>8} {'OOS vol':>7} {'worst':>7}")
    for label, net, bk in books.values():
        for var, s in (("raw", bk), ("ov", b4.apply_overlay(bk))):
            si = stats_of(s.loc[isw_idx.intersection(s.index)])
            so = stats_of(s.loc[oos_idx.intersection(s.index)])
            rows.append({"book": label, "variant": var, "window": "IS",
                         **si})
            rows.append({"book": label, "variant": var, "window": "OOS",
                         **so})
            print(f"{label:<3} {var:<8} {si['sharpe']:7.2f} {si['maxdd']*100:7.2f}% | "
                  f"{so['sharpe']:7.2f} {so['cagr']*100:7.2f}% {so['maxdd']*100:7.2f}% "
                  f"{so['vol']*100:6.1f}% {so['worst']*100:6.2f}%")

    # regime drill on side legs (OOS 2011-2014 vs IS 2023-2026)
    print("\nRegime drill, side legs (annual sums):")
    drill = []
    for name, (pos, ret, turn) in {
        "crack_short": crack_short, "crack_mom": crack_mom,
        "cross_short": cross_short, "cross_mom": cross_mom,
    }.items():
        comp = ret.loc[oos_idx]
        comp_is = ret.loc[isw_idx.intersection(ret.index)]
        c14 = comp.loc["2011-01-01":"2014-12-31"].sum()
        c26 = comp_is.sum()
        drill.append({"leg": name, "oos_2011_2014": float(c14), "is_2023_2026": float(c26)})
        print(f"  {name:<13} OOS 2011-2014 {c14*100:+7.2f}%   IS 2023-2026 {c26*100:+7.2f}%")

    # negative control: shuffle short-side signals, rebuild B
    print("\nNegative control (time-shuffled short signals, book B):")
    nc_ov = []
    nc_raw = []
    z_crack = fb.seasonal_z(levels["crack_321"])
    for i in range(NC_PERMS):
        rng = np.random.default_rng(NC_SEED + i)
        idx = z_crack.index
        perm = rng.permutation(len(idx))
        sig = side_state(z_crack, "short_stretch")
        sig_shuf = pd.Series(sig.to_numpy()[perm], index=idx)
        # rebuild crack_short with shuffled signal
        raw = sig_shuf * b4.fixed_vol_scale(levels["crack_321"], VT_CRACK)
        pos = b4.leg_risk(raw, levels["crack_321"],
                          trailing_stop=fb.TRAILING_STOP_ON["crack_321"]).fillna(0.0)
        base = b4.base_of(levels["crack_321"]).shift(1).replace(0.0, np.nan)
        ret = (pos.shift(1).fillna(0.0) * levels["crack_321"].diff() / base).fillna(0.0)
        turn = pos.diff().abs().fillna(0.0)
        # cross_short legs: shuffle each leg's chosen-sig series
        legs = ["crack_321", "crack_gas", "crack_ho"]
        zdf = pd.DataFrame({k: fb.seasonal_z(levels[k]) for k in legs})
        cross_pos, cross_ret, cross_turn = {}, {}, {}
        for li, leg in enumerate(legs):
            lvl = levels[leg]
            zz = zdf[leg].to_numpy(dtype=float)
            on_leg = np.zeros(len(lvl))
            valid = zdf[leg].notna()
            for j in range(len(lvl)):
                if valid.iloc[j] and not np.isnan(zz[j]) and zz[j] > XS_ENTRY:
                    on_leg[j] = 1.0
            on_leg_s = pd.Series(on_leg[perm], index=lvl.index)
            scale = b4.fixed_vol_scale(lvl, VT_XS)
            sig_leg = -on_leg_s
            p = b4.leg_risk(sig_leg * scale, lvl, trailing_stop=False).fillna(0.0)
            b = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
            cross_pos[leg] = p
            cross_ret[leg] = (p.shift(1).fillna(0.0) * lvl.diff() / b).fillna(0.0)
            cross_turn[leg] = p.diff().abs().fillna(0.0)
        cp = pd.DataFrame(cross_pos).sum(axis=1)
        cr = pd.DataFrame(cross_ret).sum(axis=1).fillna(0.0)
        ct = pd.DataFrame(cross_turn).sum(axis=1)
        net = net_frame({"crack_short": pos, "cross_short": cp, "bzwti": bw[0]},
                        {"crack_short": ret, "cross_short": cr, "bzwti": bw[1]},
                        {"crack_short": turn, "cross_short": ct, "bzwti": bw[2]})
        w = b4.weight_scheme(net[["crack_short", "cross_short", "bzwti"]], "EQ")
        bk = b4.book_returns(net, ["crack_short", "cross_short", "bzwti"], w)
        so_raw = b4.stats(bk.loc[oos_idx.intersection(bk.index)])
        so_ov = b4.stats(b4.apply_overlay(bk).loc[oos_idx.intersection(bk.index)])
        nc_raw.append(so_raw["sharpe"] if not np.isnan(so_raw["sharpe"]) else 0.0)
        nc_ov.append(so_ov["sharpe"] if not np.isnan(so_ov["sharpe"]) else 0.0)
    real_b = next(x for x in rows if x["book"] == "B" and x["variant"] == "ov" and x["window"] == "OOS")
    print(f"  real B ov OOS Sharpe: {real_b['sharpe']:.3f}")
    print(f"  shuffled raw OOS Sharpe: mean {np.mean(nc_raw):.3f} sd {np.std(nc_raw):.3f}")
    print(f"  shuffled ov  OOS Sharpe: mean {np.mean(nc_ov):.3f} sd {np.std(nc_ov):.3f}")

    with open(ROOT / "results" / "phase1_results.csv", "w", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=["book", "variant", "window",
                                             "sharpe", "cagr", "maxdd", "vol", "worst"])
        wcsv.writeheader()
        wcsv.writerows(rows)
        for d in drill:
            wcsv.writerow({"book": "DRILL_" + d["leg"], "variant": "sum",
                           "window": "2011-2014", "sharpe": d["oos_2011_2014"],
                           "cagr": 0.0, "maxdd": 0.0, "vol": 0.0, "worst": 0.0})
        wcsv.writerow({"book": "NC_B", "variant": "shuffled_raw", "window": "OOS",
                       "sharpe": float(np.mean(nc_raw)), "cagr": float(np.std(nc_raw)),
                       "maxdd": 0.0, "vol": 0.0, "worst": 0.0})
        wcsv.writerow({"book": "NC_B", "variant": "shuffled_ov", "window": "OOS",
                       "sharpe": float(np.mean(nc_ov)), "cagr": float(np.std(nc_ov)),
                       "maxdd": 0.0, "vol": 0.0, "worst": 0.0})
    print("\nSaved results/phase1_results.csv")


if __name__ == "__main__":
    main()
