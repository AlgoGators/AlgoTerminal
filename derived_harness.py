"""Derived thresholds: curve-driven exposure, thresholds removed.

Preregistered in research/derived_thresholds.md (02ceccb). The
conditional-mean curve is estimated on TRAIN only. Exposure is
continuous: w(z)=clip(curve/max,0,1) on comp/norm days. H1 gate and
ES gear stay. No 0.75, no -0.5.
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

BLOCK = 20
WARMUP = 90
GEAR = 0.365
TRAIN_LO, TRAIN_HI = "2007-01-01", "2018-12-31"
OOS_LO, OOS_HI = "2007-07-30", "2023-09-08"
VAL_LO, VAL_HI = "2019-01-01", "2026-09-09"
FULL_LO, FULL_HI = "2007-07-30", "2026-09-09"
NBINS = 24
ZLO, ZHI = -4.0, 1.5


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
        mean = (sub.cumsum() / sub.notna().cumsum()).shift(1)
        mean[sub.notna().cumsum().shift(1) < min_obs] = np.nan
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
    n = len(blocks)
    m = blocks.mean()
    sd = blocks.std(ddof=1)
    se = sd / np.sqrt(n)
    return {"n": n, "ann": m * 252 / BLOCK, "t": m / se if se else np.nan,
            "lo90": m - 1.645 * se, "hi90": m + 1.645 * se, "neg": float((blocks < 0).mean()),
            "worst": float(blocks.min())}


def report(tag, ser, rows):
    for wname, lo, hi in (("TRAIN", TRAIN_LO, TRAIN_HI), ("VALIDATE", VAL_LO, VAL_HI),
                          ("OOS", OOS_LO, OOS_HI), ("FULL", FULL_LO, FULL_HI)):
        seg = ser.loc[lo:hi].iloc[WARMUP:] if len(ser.loc[lo:hi]) > WARMUP else ser.loc[lo:hi]
        st = block_stats(blocks_of(seg))
        log(f"  {tag:<22} {wname:<9} ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f} "
            f"CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]% neg {st['neg']*100:.0f}% "
            f"worst {st['worst']*100:+.1f}%")
        rows.append({"variant": tag, "window": wname, **st})


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    z = fb.seasonal_z(lvl)
    fwd20 = (lvl.shift(-20) - lvl) / b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    base_r = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base_r).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    rel = lvl - base_r
    r2 = pd.Series(np.select([rel < -band, rel > band], ["comp", "exp"], default="norm"),
                   index=full_idx)
    regime_ok = r2.isin(["comp", "norm"]).to_numpy(dtype=bool)
    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)
    h1_gate = pd.Series(prod_z >= 1.0, index=full_idx)

    # ---- derive curve on TRAIN only ----
    train = (full_idx >= TRAIN_LO) & (full_idx <= TRAIN_HI)
    on = train & regime_ok & z.notna() & fwd20.notna()
    zb = np.clip((z.to_numpy()[on] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1).astype(int)
    rows_out = []
    curve = np.full(NBINS, np.nan)
    winp = np.full(NBINS, np.nan)
    for b in range(NBINS):
        sel = zb == b
        if sel.sum() >= 20:
            curve[b] = fwd20.to_numpy()[on][sel].mean()
            winp[b] = (fwd20.to_numpy()[on][sel] > 0).mean()
    # smooth with 5-bin rolling mean (finite only)
    for b in range(NBINS):
        lo = max(0, b - 2)
        hi = min(NBINS, b + 3)
        seg = curve[lo:hi]
        if np.isfinite(seg).sum() >= 3:
            curve[b] = np.nanmean(seg)
    zcents = ZLO + (np.arange(NBINS) + 0.5) * (ZHI - ZLO) / NBINS
    pos = np.isfinite(curve)
    maxc = np.nanmax(curve)
    # zero crossing: largest z with curve positive to the left, negative to the right
    zcross = None
    for b in range(1, NBINS):
        if np.isfinite(curve[b - 1]) and np.isfinite(curve[b]) and curve[b - 1] > 0 >= curve[b]:
            zcross = (zcents[b - 1] + zcents[b]) / 2
            break
    log("derived curve (z_bin -> E[fwd20], P(win)):")
    for i, b in enumerate(np.flatnonzero(pos)):
        log(f"  z={zcents[b]:+.2f} E={curve[b]*100:+.1f}% P={winp[b]*100:.0f}%")
    log(f"  max curve {maxc*100:.1f}% at z={zcents[np.nanargmax(curve)]:+.2f}; "
        f"zero crossing ~ z={zcross:+.2f}" if zcross is not None else
        f"  max curve {maxc*100:.1f}%; zero crossing not found")
    rows_out.append({"max_curve": maxc, "zcross": zcross})

    # ---- exposure function from the curve ----
    zarr = z.to_numpy(dtype=float)
    rarr = regime_ok
    def w_of(zv):
        b = int(np.clip((zv - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1))
        if not np.isfinite(curve[b]):
            return 0.0
        return float(np.clip(curve[b] / maxc, 0.0, 1.0))
    wv = np.zeros(len(full_idx), dtype=float)
    for i in range(len(full_idx)):
        if rarr[i] and np.isfinite(zarr[i]):
            wv[i] = w_of(zarr[i])
    w = pd.Series(wv, index=full_idx)
    h1_m = (1 - h1_gate.shift(1).fillna(0.0))
    raw = w * b4.fixed_vol_scale(lvl, fb.VT_F1) * h1_m.shift(1).fillna(1.0)
    pos_leg = b4.leg_risk(raw.fillna(0.0), lvl, trailing_stop=fb.TRAILING_STOP_ON["crack_321"]).fillna(0.0)
    base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    ret = (pos_leg.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
    turn = pos_leg.diff().abs().fillna(0.0)
    net = b4.apply_costs({"F1": pos_leg}, {"F1": ret}, turnover={"F1": turn})["F1"]
    book_raw = net
    book_gear = book_raw * GEAR

    rows = []
    log("\n=== curve-driven exposure (no 0.75/-0.5) ===")
    report("Curve book raw", book_raw, rows)
    report("Curve book + gear", book_gear, rows)

    # bar variant: keep exposure only where TRAIN curve E[fwd20] >= BAR; cutoff read from curve
    BAR = 0.05
    zcut_idx = None
    for b in range(NBINS - 1, -1, -1):
        if np.isfinite(curve[b]) and curve[b] >= BAR:
            zcut_idx = b
            break
    zcut = zcents[zcut_idx] if zcut_idx is not None else np.nan
    log(f"\n=== bar variant: E[fwd20|z] >= {BAR*100:.0f}% => z <= {zcut:+.2f} (read from curve) ===")
    wv2 = np.zeros(len(full_idx), dtype=float)
    for i in range(len(full_idx)):
        if rarr[i] and np.isfinite(zarr[i]):
            wv2[i] = w_of(zarr[i]) if zarr[i] <= zcut else 0.0
    w2 = pd.Series(wv2, index=full_idx)
    raw2 = w2 * b4.fixed_vol_scale(lvl, fb.VT_F1) * h1_m.shift(1).fillna(1.0)
    pos2 = b4.leg_risk(raw2.fillna(0.0), lvl, trailing_stop=fb.TRAILING_STOP_ON["crack_321"]).fillna(0.0)
    ret2 = (pos2.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
    turn2 = pos2.diff().abs().fillna(0.0)
    net2 = b4.apply_costs({"F1": pos2}, {"F1": ret2}, turnover={"F1": turn2})["F1"]
    report("Bar5 raw", net2, rows)
    report("Bar5 + gear", net2 * GEAR, rows)

    with open(ROOT / "results" / "derived_thresholds.csv", "w", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=["variant", "window", "n", "ann", "t",
                                             "lo90", "hi90", "neg", "worst"])
        wcsv.writeheader()
        for r in rows:
            wcsv.writerow(r)
        wcsv.writerow({"variant": "curve_meta", "n": NBINS, "ann": maxc, "t": zcross or np.nan})
    log("\nSaved results/derived_thresholds.csv")


if __name__ == "__main__":
    main()
