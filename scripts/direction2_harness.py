"""Direction 2: close the record with clean stats.

Preregistered in research/direction2_close_record.md (c57844b).
A weather gate, B1/B2 storage gates, C crash-put screen, D joint
crisis state. Non-overlap 20d blocks throughout.
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

BLOCK = 20
WARMUP = 90
OOS = slice("2007-07-30", "2023-09-08")


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


def blocks_of(s: pd.Series) -> pd.Series:
    s = s.dropna()
    pos = np.arange(len(s))
    blk = pos // BLOCK
    out = {}
    for b in range(blk.max() + 1):
        seg = s[blk == b]
        if len(seg) == BLOCK:
            out[s.index[blk == b][0]] = seg.sum()
    return pd.Series(out)


def block_stats(blocks: pd.Series):
    if len(blocks) < 3:
        return None
    n = len(blocks)
    m = blocks.mean()
    sd = blocks.std(ddof=1)
    se = sd / np.sqrt(n)
    return {"n": n, "ann": m * 252 / BLOCK, "t": m / se if se else np.nan,
            "lo90": m - 1.645 * se, "hi90": m + 1.645 * se}


def gated_leg(pos_raw, ret_raw, gate: pd.Series, oos_idx):
    """Apply multiplier 0 when gate active; recompute costs-free stats via blocks."""
    pos = pos_raw * (1 - gate).reindex(pos_raw.index).fillna(1.0)
    diff = pos_raw.diff() - pos.diff()
    # returns are from the raw engine; de-risked returns differ. Use raw positioned
    # returns scaled by the gate at t-1 (the standard convention in this repo).
    ret = ret_raw * (1 - gate.shift(1)).reindex(ret_raw.index).fillna(1.0)
    return ret


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    oos_idx = full_idx[(full_idx >= "2007-07-30") & (full_idx < "2023-09-08")]
    fac4, rets4, turn4 = b4.build_v4(levels, None)
    t2m = read_csv(WEA / "raw_T2M_NYC.csv").reindex(full_idx)
    hdd = pd.Series(np.maximum(0.0, 18.0 - t2m), index=full_idx)
    hdd_z = sm_z(hdd)

    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)
    ng_stor = read_csv(EIA / "raw_ng_storage_sum.csv")
    ng_z = daily_state(sm_z(ng_stor), full_idx)

    rows = []
    log("=== A weather gate (NG and HO legs, OOS blocks) ===")
    gate_w = pd.Series(hdd_z <= -1.0, index=full_idx)
    for leg, lvl in (("ng", levels["ng"]), ("crack_ho", levels["crack_ho"])):
        ret_raw = rets4[leg]
        ret_g = ret_raw * (1 - gate_w.shift(1)).reindex(ret_raw.index).fillna(1.0)
        for tag, ser in ((f"{leg}_raw", ret_raw), (f"{leg}_gated", ret_g)):
            seg = ser.loc[OOS].iloc[WARMUP:] if len(ser.loc[OOS]) > WARMUP else ser.loc[OOS]
            st = block_stats(blocks_of(seg))
            if st:
                log(f"  {tag:<14} ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f} "
                    f"CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]%")
                rows.append({"item": "weather", "leg": tag, **st})

    log("\n=== B1 product-stock gate (H1, OOS blocks) ===")
    gate_h1 = pd.Series(prod_z >= 1.0, index=full_idx)
    for leg in ("crack_321", "cross_sectional"):
        ret_raw = rets4[leg]
        ret_g = ret_raw * (1 - gate_h1.shift(1)).reindex(ret_raw.index).fillna(1.0)
        for tag, ser in ((f"{leg}_raw", ret_raw), (f"{leg}_gated", ret_g)):
            seg = ser.loc[OOS].iloc[WARMUP:] if len(ser.loc[OOS]) > WARMUP else ser.loc[OOS]
            st = block_stats(blocks_of(seg))
            if st:
                log(f"  {tag:<18} ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f} "
                    f"CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]%")
                rows.append({"item": "storage_h1", "leg": tag, **st})

    log("\n=== B2 natgas storage gate (H2, ng leg, 2010+ OOS blocks) ===")
    oos10 = oos_idx[oos_idx >= "2010-06-01"]
    gate_h2 = pd.Series(ng_z >= 1.0, index=full_idx)
    ret_raw = rets4["ng"]
    ret_g = ret_raw * (1 - gate_h2.shift(1)).reindex(ret_raw.index).fillna(1.0)
    for tag, ser in (("ng_raw", ret_raw), ("ng_gated", ret_g)):
        seg = ser.loc["2010-06-01":"2023-09-08"].iloc[WARMUP:]
        st = block_stats(blocks_of(seg))
        if st:
            log(f"  {tag:<14} ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f} "
                f"CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]%")
            rows.append({"item": "storage_h2", "leg": tag, **st})

    log("\n=== C crash-put cost screen (clean monthly blocks) ===")
    names = ["crack_321", "cross_sectional", "bzwti"]
    net = b4.apply_costs({k: fac4[k] for k in names}, {k: rets4[k] for k in names},
                         turnover={k: turn4[k] for k in names})
    book = b4.book_returns(net, names, b4.weight_scheme(net[names], "EQ"))
    book_ov = b4.apply_overlay(book)
    for tag, ser in (("raw", book), ("ov", book_ov)):
        seg = ser.loc[OOS].iloc[WARMUP:]
        months = seg.resample("ME").sum().dropna()
        vol_m = months.std(ddof=1)
        mean_m = months.mean()
        prem = 0.041 * seg.mean() * 252 / 12 / mean_m if mean_m else np.nan
        log(f"  {tag} monthly n={len(months)} mean {mean_m*100:+.2f}% std {vol_m*100:.2f}% "
            f"prem/mean {prem:.2f}x")
        rows.append({"item": "crashput", "series": tag, "monthly_mean": mean_m,
                     "monthly_std": vol_m, "prem_over_mean": prem})

    log("\n=== D joint crisis state (clean blocks) ===")
    zc = fb.seasonal_z(levels["crack_321"])
    crash5 = zc - zc.shift(5)
    cl = df["CL"]
    crude20 = (cl / cl.shift(20) - 1.0)
    joint = pd.Series((zc <= -1.25) & (crash5 >= 1.0) & (crude20 <= -0.15),
                      index=full_idx)
    crush = pd.Series(zc <= -0.75, index=full_idx)
    fwd20 = (levels["crack_321"].shift(-20) - levels["crack_321"]) / \
        b4.base_of(levels["crack_321"]).shift(1).replace(0.0, np.nan)
    for tag, mask in (("joint", joint), ("crush", crush)):
        m = mask & fwd20.notna()
        log(f"  {tag}: days {int(m.sum())} "
            f"(OOS {int(m.loc[OOS].sum())})")
        rows.append({"item": "joint", "state": tag, "n_full": int(m.sum()),
                     "n_oos": int(m.loc[OOS].sum())})
    # non-overlap: sample every 20th day, JOINT on that day
    sampled = full_idx[::20]
    for tout, (lo, hi) in (("OOS", ("2007-07-30", "2023-09-08")), ("FULL", (None, None))):
        for tag, mask in (("joint", joint), ("crush", crush)):
            sel = sampled[mask.reindex(sampled).fillna(False).to_numpy(dtype=bool)]
            if lo: sel = sel[(sel >= lo) & (sel < hi)]
            vals = fwd20.reindex(sel).dropna()
            if len(vals) >= 5:
                n = len(vals); m = vals.mean(); sd = vals.std(ddof=1); se = sd / np.sqrt(n)
                log(f"  {tag} {tout}: n={n} fwd20 {m*100:+6.2f}% t={m/se:+5.2f} "
                    f"CI [{m-1.645*se:.4f},{m+1.645*se:.4f}]")
                rows.append({"item": "joint_block", "state": tag, "window": tout,
                             "n": n, "mean": m, "t": m / se if se else np.nan})

    with open(ROOT / "results" / "direction2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    log("\nSaved results/direction2.csv")


if __name__ == "__main__":
    main()
