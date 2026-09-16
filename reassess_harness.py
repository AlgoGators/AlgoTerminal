"""Reassessment probes: Tier 1 phenomenon tests for ch27/ch29/ch30.

Preregistered in research/reassessment_probes.md. Bucket tests are
position-free. M1 adds one light construction check with costs but no
book and no overlay.
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

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

NC = 20
NC_SEED = 23
CROSS_LEGS = ["crack_321", "crack_gas", "crack_ho"]
WINTER = (11, 12, 1, 2, 3)
SUMMER = (5, 6, 7, 8, 9)


def log(msg: str) -> None:
    print(msg, flush=True)


def read_csv(path: Path, col: str = "close") -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[col].astype(float)


def sm_expanding_mean(s: pd.Series, min_obs: int = 30) -> pd.Series:
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


def sm_expanding_std(s: pd.Series, min_obs: int = 30) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        var = ((sub - sub.expanding().mean().shift(1)).pow(2)).expanding().mean().shift(1)
        sd = var.pow(0.5)
        sd[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = sd
    return out


def sm_z(s: pd.Series, min_obs: int = 30) -> pd.Series:
    return ((s - sm_expanding_mean(s, min_obs)) / sm_expanding_std(s, min_obs)).clip(-8, 8)


def daily_state(weekly: pd.Series, index: pd.Index) -> pd.Series:
    av = weekly.copy()
    av.index = av.index + pd.Timedelta(days=6)
    av = av[~av.index.duplicated(keep="last")].sort_index()
    idx = pd.DatetimeIndex(pd.to_datetime(index))
    return av.reindex(av.index.union(idx)).sort_index().ffill().reindex(idx)


def forward(level: pd.Series, h: int) -> pd.Series:
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    return ((level.shift(-h) - level) / base).rename(f"fwd{h}")


def bucket_means(feat: pd.Series, fwd: pd.Series, mask: pd.Series | None = None, n_q: int = 5):
    idx = fwd.index.intersection(feat.dropna().index)
    if mask is not None:
        am = mask[mask].index
        idx = idx.intersection(am)
    if len(idx) < 60:
        return None
    f = feat.loc[idx]
    r = fwd.loc[idx]
    try:
        q = pd.qcut(f, n_q, labels=False, duplicates="drop")
    except ValueError:
        return None
    out = []
    for b in sorted(set(q.dropna())):
        sel = q == b
        out.append({"bucket": int(b), "n": int(sel.sum()),
                    "feat_mean": float(f[sel].mean()),
                    "fwd_mean": float(r[sel].mean())})
    return out


def print_buckets(name: str, rows):
    if not rows:
        log(f"  {name}: insufficient")
        return
    log(f"  {name}:")
    for r in rows:
        log(f"    b{r['bucket']} n={r['n']:>4} feat {r['feat_mean']:+.2f} "
            f"fwd {r['fwd_mean']*100:+.2f}%")


def top_minus_bottom(rows):
    if not rows or len(rows) < 2:
        return np.nan
    return rows[-1]["fwd_mean"] - rows[0]["fwd_mean"]


def main() -> None:
    global fac4, rets4, turn4
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    mon = np.array([m for m in full_idx.month], dtype=int)
    oos_idx = b4.window(pd.DataFrame(index=full_idx), b4.OOS_START, b4.IS_START).index
    fac4, rets4, turn4 = b4.build_v4(levels, None)

    cush = read_csv(EIA / "raw_W_EPC0_SAX_YCUOK_MBBL.csv")
    propane = read_csv(EIA / "raw_WPRSTUS1.csv")
    prop_z = daily_state(sm_z(propane), full_idx)
    cushion_d = daily_state(cush, full_idx)
    cushion_draw_z = daily_state(-sm_z(cush.diff()), full_idx)
    fullness = daily_state((cush / cush.rolling(156, min_periods=60).max()).fillna(0.0), full_idx)

    fwd_gas20 = forward(levels["crack_gas"], 20)
    fwd_ng20 = forward(levels["ng"], 20)
    fwd_bz20 = forward(levels["bzwti"], 20)

    winter = pd.Series([m in WINTER for m in mon], index=full_idx)
    summer = pd.Series([m in SUMMER for m in mon], index=full_idx)
    rows = []

    # ---------------- N1 propane ----------------
    log("=== N1 propane/NGL winter ===")
    bw = bucket_means(prop_z, fwd_gas20, mask=winter)
    print_buckets("propane z (winter) > fwd20 crack_gas", bw)
    bs = bucket_means(prop_z, fwd_gas20, mask=summer)
    print_buckets("propane z (summer) > fwd20 crack_gas", bs)
    bn = bucket_means(prop_z, fwd_ng20, mask=winter)
    print_buckets("propane z (winter) > fwd20 NG", bn)
    if bw and len(bw) >= 2:
        real = top_minus_bottom(bw)
        nc = []
        for i in range(NC):
            rng = np.random.default_rng(NC_SEED + i)
            idxs = fwd_gas20[winter & fwd_gas20.notna()].index.to_numpy()
            lab = rng.random(len(idxs)) < 0.2
            a = fwd_gas20.loc[idxs][lab].mean()
            c = fwd_gas20.loc[idxs][~lab].mean()
            picks = sorted(fwd_gas20.loc[idxs][lab].quantile([0.0, 1.0]).index)
            nc.append(np.nan)
        log(f"  N1 winter top-minus-bottom {real*100:+.2f}%")
        rows.append(("N1_gas_winter_delta", real))
    if bn and len(bn) >= 2:
        rows.append(("N1_ng_winter_delta", top_minus_bottom(bn)))
    if bs and len(bs) >= 2:
        rows.append(("N1_gas_summer_delta", top_minus_bottom(bs)))

    # ---------------- C1 Cushing ratio ----------------
    log("\n=== C1 Cushing utilization ratio ===")
    bf = bucket_means(fullness, fwd_bz20)
    print_buckets("fullness > fwd20 bzwti", bf)
    if bf and len(bf) >= 2:
        rows.append(("C1_fullness_delta", top_minus_bottom(bf)))
    comb = (fullness >= 0.85) & (cushion_draw_z >= 1.0)
    sel = comb & fwd_bz20.notna()
    other = (~comb) & fwd_bz20.notna()
    log(f"  C1 combined (full>=0.85 & draw) n={int(sel.sum())} fwd20 "
        f"{fwd_bz20[sel].mean()*100:+.2f}% vs other {fwd_bz20[other].mean()*100:+.2f}%")
    rows.append(("C1_combined_mean", fwd_bz20[sel].mean() if sel.sum() else np.nan))
    rows.append(("C1_other_mean", fwd_bz20[other].mean() if other.sum() else np.nan))
    nc = []
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        lab = rng.random(len(full_idx)) < (sel.sum() / len(full_idx))
        nc.append(fwd_bz20[lab & fwd_bz20.notna()].mean())
    if np.isfinite(nc).sum():
        log(f"  C1 control: combined {fwd_bz20[sel].mean()*100:+.2f}% vs "
            f"shuffled mean {np.nanmean(nc)*100:+.2f}% sd {np.nanstd(nc)*100:.2f}%")
        rows.append(("C1_shuffled_mean", float(np.nanmean(nc))))

    # ---------------- M1 multi-leg F2 ----------------
    log("\n=== M1 multi-leg F2 depth ===")
    zl = {k: fb.seasonal_z(levels[k]) for k in CROSS_LEGS}
    pool_z = []
    pool_fwd10 = []
    pool_fwd20 = []
    for k in CROSS_LEGS:
        on = zl[k] <= -0.5
        depth = zl[k][on].abs()
        for h, arr in ((10, pool_fwd10), (20, pool_fwd20)):
            f = forward(levels[k], h)[on]
            m = depth.index.intersection(f.dropna().index)
            arr.append(pd.DataFrame({"depth": depth.reindex(m), "fwd": f.reindex(m)}))
    f10 = pd.concat(pool_fwd10).dropna()
    f20 = pd.concat(pool_fwd20).dropna()
    for tag, frame in (("fwd10", f10), ("fwd20", f20)):
        if len(frame) >= 60:
            q = pd.qcut(frame["depth"], 5, labels=False, duplicates="drop")
            for b in sorted(set(q.dropna())):
                sel = q == b
                log(f"  {tag} depth b{b} n={int(sel.sum()):>4} "
                    f"mean {frame.loc[sel,'fwd'].mean()*100:+.2f}%")
    # light construction: multi-leg depth F2
    vt = fb.VT_F2
    ml_pos, ml_ret, ml_turn = {}, {}, {}
    for k in CROSS_LEGS:
        lvl = levels[k]
        z = zl[k]
        on = (z <= -0.5).to_numpy(dtype=bool)
        zz = z.abs().to_numpy(dtype=float)
        mult = np.where(on, np.clip(1 + 0.5 * (zz - 0.5), 1.0, 2.0), 1.0)
        raw = pd.Series(np.where(on, 1.0, 0.0), index=lvl.index) * b4.fixed_vol_scale(lvl, vt)
        raw = raw * pd.Series(mult, index=lvl.index).shift(1).fillna(1.0)
        p = b4.leg_risk(raw, lvl, trailing_stop=False).fillna(0.0)
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        ml_pos[k] = p
        ml_ret[k] = (p.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
        ml_turn[k] = p.diff().abs().fillna(0.0)
    net_ml = b4.apply_costs(ml_pos, ml_ret, turnover=ml_turn)
    tot = net_ml.sum(axis=1)
    v1 = b4.apply_costs({"cross": fac4["cross_sectional"]}, {"cross": rets4["cross_sectional"]},
                        turnover={"cross": turn4["cross_sectional"]})["cross"]
    so_ml = b4.stats(tot.loc[oos_idx.intersection(tot.index)])
    so_v1 = b4.stats(v1.loc[oos_idx.intersection(v1.index)])
    log(f"  M1 construction OOS raw: multi-leg depth Sh {so_ml['sharpe']:.3f} "
        f"CAGR {so_ml['cagr']*100:.2f}% DD {so_ml['maxdd']*100:.2f}%")
    log(f"  M1 v1 single-most-crushed: Sh {so_v1['sharpe']:.3f} "
        f"CAGR {so_v1['cagr']*100:.2f}% DD {so_v1['maxdd']*100:.2f}%")
    rows.append(("M1_multileg_sharpe", so_ml["sharpe"]))
    rows.append(("M1_singleleg_sharpe", so_v1["sharpe"]))

    with open(ROOT / "results" / "reassessment_probes.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["test", "value"])
        for k, v in rows:
            w.writerow([k, "" if (v is None or (isinstance(v, float) and np.isnan(v))) else f"{v:.6f}"])
    log("\nSaved results/reassessment_probes.csv")


if __name__ == "__main__":
    main()
