"""Hypothesis pass: Tier 1 phenomenon evidence for re-opened items.

Bucket the forcing variable, measure forward level behavior per bucket,
report monotonicity and one shuffle control. No positions, no costs,
no overlay. Forward basis = diff / rolling mean |level| (engine basis).

Items:
  P1 cold weather severity vs gasoline crack (source 2)
  P2 blend switch distance vs gasoline crack (source 3)
  P3 product stock change z vs crack reversion (sources 6/10)
  P4 utilization seasonal position vs crack (source 1)
  P5 stretched margins by regime, forward path (source 8)
  P6 cooling degree days vs crack (source 4)
  P7 crude stock glut vs Brent-WTI path (source 12)
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


def bucket_table(feat: pd.Series, fwd: pd.Series, n_q: int = 5,
                 mask: pd.Series | None = None):
    idx = fwd.index.intersection(feat.dropna().index)
    if mask is not None:
        idx = idx.intersection(mask[mask].index)
    f = feat.loc[idx]
    r = fwd.loc[idx]
    if len(f) < 50:
        return None
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
        log(f"  {name}: insufficient data")
        return
    log(f"  {name}:")
    for r in rows:
        log(f"    bucket {r['bucket']} n={r['n']:>5} feat {r['feat_mean']:+.2f} "
            f"fwd {r['fwd_mean']*100:+.2f}%")


def top_minus_bottom(rows):
    if not rows or len(rows) < 2:
        return np.nan
    return rows[-1]["fwd_mean"] - rows[0]["fwd_mean"]


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index

    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    util_w = read_csv(EIA / "raw_WPULEUS3.csv")
    crude_w = read_csv(EIA / "raw_WCESTUS1.csv")
    t2m_nyc = read_csv(WEA / "raw_T2M_NYC.csv").reindex(full_idx)
    t2m_hou = read_csv(WEA / "raw_T2M_HOUSTON.csv").reindex(full_idx)

    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)
    util_d = daily_state(util_w, full_idx)
    util_seas = (util_d - sm_expanding_mean(util_d)) / sm_expanding_std(util_d)
    crude_z = daily_state(sm_z(crude_w), full_idx)
    hdd_nyc = pd.Series(np.maximum(0.0, 18.0 - t2m_nyc), index=full_idx)
    cdd_nyc = pd.Series(np.maximum(0.0, t2m_nyc - 18.0), index=full_idx)
    hdd_hou = pd.Series(np.maximum(0.0, 18.0 - t2m_hou), index=full_idx)

    fwd_gas20 = forward(levels["crack_gas"], 20)
    fwd_gas10 = forward(levels["crack_gas"], 10)
    fwd_321_20 = forward(levels["crack_321"], 20)
    fwd_321_10 = forward(levels["crack_321"], 10)
    fwd_bz20 = forward(levels["bzwti"], 20)

    rows_out = []

    # P1 cold severity --------------------------------------------------
    log("=== P1 cold severity (HDD NYC) vs gasoline crack ===")
    hdd_z_all = sm_z(hdd_nyc)
    b = bucket_table(hdd_z_all, fwd_gas20)
    print_buckets("HDD z (all days) > fwd20 crack_gas", b)
    rows_out.append(("P1_hdd_all", top_minus_bottom(b)))
    winter = pd.Series([m in (11, 12, 1, 2, 3) for m in full_idx.month], index=full_idx)
    bw = bucket_table(hdd_z_all, fwd_gas20, mask=winter)
    print_buckets("HDD z (winter days) > fwd20 crack_gas", bw)
    rows_out.append(("P1_hdd_winter", top_minus_bottom(bw)))
    # onset: 5-day change in HDD
    onset = sm_z(hdd_nyc.diff(5))
    bo = bucket_table(onset, fwd_gas20, mask=winter)
    print_buckets("HDD 5d change z (winter) > fwd20 crack_gas", bo)
    rows_out.append(("P1_onset", top_minus_bottom(bo)))
    # Houston cooling-focus: HDD Houston on crack_gas
    bh = bucket_table(sm_z(hdd_hou), fwd_gas20)
    print_buckets("HDD z HOUSTON (all days) > fwd20 crack_gas", bh)
    rows_out.append(("P1_houston", top_minus_bottom(bh)))
    # control on the headline bucket
    if bw and len(bw) >= 2:
        real = top_minus_bottom(bw)
        nc = []
        for i in range(NC):
            rng = np.random.default_rng(NC_SEED + i)
            lab = rng.random(len(full_idx)) < 0.2
            sel = fwd_gas20[lab].dropna()
            nc.append(sel.mean())
        log(f"  control: top-minus-bottom {real*100:+.2f}% vs random-20% slices "
            f"mean {np.mean(nc)*100:+.2f}% sd {np.std(nc)*100:.2f}%")
        rows_out.append(("P1_control_delta", real))
        rows_out.append(("P1_shuffled_mean", float(np.mean(nc))))

    # P2 blend distance -------------------------------------------------
    log("\n=== P2 blend switch distance (crack_gas) ===")
    apr = pd.Timestamp(full_idx[0].year, 4, 1)
    sep = pd.Timestamp(full_idx[0].year, 9, 15)
    dist = pd.Series(np.minimum(
        np.abs((full_idx - pd.to_datetime(
            [pd.Timestamp(y, 4, 1) for y in full_idx.year]).to_numpy()).days),
        np.abs((full_idx - pd.to_datetime(
            [pd.Timestamp(y, 9, 15) for y in full_idx.year]).to_numpy()).days)),
        index=full_idx)
    for tag, m in (("dist<=7", dist <= 7), ("8..21", (dist > 7) & (dist <= 21)),
                   (">21", dist > 21)):
        sel = m & fwd_gas20.notna()
        zmean = sm_z(levels["crack_gas"])[sel].mean()
        vol = (levels["crack_gas"].diff() / b4.base_of(levels["crack_gas"]).shift(1)
               .replace(0, np.nan)).rolling(20, min_periods=10).std().shift(-19)
        log(f"  {tag:<7} n={int(sel.sum()):>4} fwd20 {fwd_gas20[sel].mean()*100:+.2f}% "
            f"z {zmean:+.2f} vol20 {vol[sel].mean()*100:.0f}%")
        rows_out.append((f"P2_{tag}", fwd_gas20[sel].mean() if sel.sum() else np.nan))

    # P3 product change z buckets --------------------------------------
    log("\n=== P3 product stock change z vs crack fwd20 ===")
    b3 = bucket_table(prod_z, fwd_321_20)
    print_buckets("product change z > fwd20 crack_321 (all)", b3)
    rows_out.append(("P3_all", top_minus_bottom(b3)))
    crush = fb.seasonal_z(levels["crack_321"]) <= -0.5
    b3c = bucket_table(prod_z, fwd_321_20, mask=crush)
    print_buckets("product change z > fwd20 crack_321 (crush state only)", b3c)
    rows_out.append(("P3_crush", top_minus_bottom(b3c)))

    # P4 utilization seasonal position ----------------------------------
    log("\n=== P4 utilization seasonal position vs crack fwd20 ===")
    b4t = bucket_table(util_seas, fwd_321_20)
    print_buckets("util seasonal z > fwd20 crack_321", b4t)
    rows_out.append(("P4", top_minus_bottom(b4t)))

    # P5 stretched by regime -------------------------------------------
    log("\n=== P5 stretched margins by regime (fwd path) ===")
    lvl = levels["crack_321"]
    zc = fb.seasonal_z(lvl)
    regime = lvl.shift(1) > lvl.shift(1).rolling(252, min_periods=126).mean()
    stretched = zc >= 0.75
    for tag, m in (("expansion", stretched & regime.fillna(False)),
                   ("compression", stretched & ~regime.fillna(False))):
        sel = m & fwd_321_20.notna()
        if sel.sum():
            log(f"  stretched {tag:<11} n={int(sel.sum()):>4} "
                f"fwd10 {fwd_321_10[sel].mean()*100:+.2f}% "
                f"fwd20 {fwd_321_20[sel].mean()*100:+.2f}%")
            rows_out.append((f"P5_{tag}_fwd20", fwd_321_20[sel].mean()))
    # control: shuffle regime labels among stretched days
    sel_all = stretched & fwd_321_20.notna()
    if sel_all.sum():
        real_d = (fwd_321_20[stretched & regime.fillna(False) & fwd_321_20.notna()].mean()
                  - fwd_321_20[stretched & ~regime.fillna(False) & fwd_321_20.notna()].mean())
        nc = []
        for i in range(NC):
            rng = np.random.default_rng(NC_SEED + i)
            idxs = fwd_321_20[sel_all].index.to_numpy()
            lab = rng.random(len(idxs)) < (regime[sel_all].mean())
            a = fwd_321_20.loc[idxs][lab].mean()
            b5 = fwd_321_20.loc[idxs][~lab].mean()
            nc.append(a - b5)
        log(f"  control: expansion-minus-compression delta {real_d*100:+.2f}% vs "
            f"shuffled mean {np.mean(nc)*100:+.2f}% sd {np.std(nc)*100:.2f}%")
        rows_out.append(("P5_delta", real_d))
        rows_out.append(("P5_shuffled_mean", float(np.mean(nc))))

    # P6 cooling degree days -------------------------------------------
    log("\n=== P6 CDD z vs crack fwd20 ===")
    b6 = bucket_table(sm_z(cdd_nyc), fwd_321_20)
    print_buckets("CDD z (all days) > fwd20 crack_321", b6)
    rows_out.append(("P6", top_minus_bottom(b6)))

    # P7 crude glut vs Brent-WTI path ----------------------------------
    log("\n=== P7 crude stock glut vs Brent-WTI fwd20 ===")
    b7 = bucket_table(crude_z, fwd_bz20)
    print_buckets("crude z > fwd20 bzwti (level change)", b7)
    rows_out.append(("P7", top_minus_bottom(b7)))

    with open(ROOT / "results" / "hypothesis_pass.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["test", "top_minus_bottom_delta"])
        for k, v in rows_out:
            w.writerow([k, "" if (v is None or np.isnan(v)) else f"{v:.6f}"])
    log("\nSaved results/hypothesis_pass.csv")


if __name__ == "__main__":
    main()
