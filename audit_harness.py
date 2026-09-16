"""Component audit: gear TRAIN fix + rebuilt-norm variant.

Preregistered in research/component_audit.md (ac7b82a).
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
BUDGET = 0.10
TRAIN_LO, TRAIN_HI = "2007-01-01", "2018-12-31"
OOS_LO, OOS_HI = "2007-07-30", "2023-09-08"
VAL_LO, VAL_HI = "2019-01-01", "2026-09-09"
FULL_LO, FULL_HI = "2007-07-30", "2026-09-09"
NBINS = 24
ZLO, ZHI = -4.0, 1.5
BAR = 0.05


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


def sm_expanding_median(s: pd.Series, min_obs: int = 30) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        med = sub.expanding().median().shift(1)
        med[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = med
    return out


def rob_std_by_month(s: pd.Series, min_obs: int = 30) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        dev = (sub - sub.expanding().median().shift(1)).abs()
        mad = (dev * 1.4826).expanding().median().shift(1)
        mad[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = mad
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
            f"CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]% neg {st['neg']*100:.0f}%")
        rows.append({"variant": tag, "window": wname, **st})


def build_curve(lvl, z, fwd20, rarr, zcents, curve_out, wout):
    train = (full_idx >= TRAIN_LO) & (full_idx <= TRAIN_HI)
    on = train & rarr & z.notna() & fwd20.notna()
    zb = np.clip((z.to_numpy()[on] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1).astype(int)
    curve = np.full(NBINS, np.nan)
    for b in range(NBINS):
        sel = zb == b
        if sel.sum() >= 20:
            curve[b] = fwd20.to_numpy()[on][sel].mean()
    for b in range(NBINS):
        seg = curve[max(0, b - 2):min(NBINS, b + 3)]
        if np.isfinite(seg).sum() >= 3:
            curve[b] = np.nanmean(seg)
    maxc = np.nanmax(curve)
    zcut = None
    for b in range(NBINS - 1, -1, -1):
        if np.isfinite(curve[b]) and curve[b] >= BAR:
            zcut = zcents[b]
            break
    wv = np.zeros(len(full_idx), dtype=float)
    for i in range(len(full_idx)):
        if rarr[i] and np.isfinite(z.to_numpy()[i]):
            bi = int(np.clip((z.to_numpy()[i] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1))
            val = curve[bi]
            if np.isfinite(val) and zcut is not None and z.to_numpy()[i] <= zcut:
                wv[i] = float(np.clip(val / maxc, 0.0, 1.0))
    curve_out.clear(); curve_out.update({float(zcents[b]): float(curve[b]) for b in range(NBINS) if np.isfinite(curve[b])})
    wout[:] = wv
    return maxc, zcut


def run_book(w, h1_m, lvl, z, gear):
    raw = w * b4.fixed_vol_scale(lvl, fb.VT_F1) * h1_m.shift(1).fillna(1.0)
    pos = b4.leg_risk(raw.fillna(0.0), lvl, trailing_stop=fb.TRAILING_STOP_ON["crack_321"]).fillna(0.0)
    base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    ret = (pos.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    net = b4.apply_costs({"F1": pos}, {"F1": ret}, turnover={"F1": turn})["F1"]
    return net * gear


def main() -> None:
    global full_idx
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    fwd20 = (lvl.shift(-20) - lvl) / b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    base_r = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base_r).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    r2 = pd.Series(np.select([lvl - base_r < -band, lvl - base_r > band],
                             ["comp", "exp"], default="norm"), index=full_idx)
    rarr = r2.isin(["comp", "norm"]).to_numpy(dtype=bool)
    z_old = fb.seasonal_z(lvl)
    med = sm_expanding_median(lvl)
    rstd = rob_std_by_month(lvl)
    z_new = ((lvl - med) / rstd).clip(-8, 8)
    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)
    h1_gate = pd.Series(prod_z >= 1.0, index=full_idx)
    h1_m = (1 - h1_gate.shift(1).fillna(0.0))
    zcents = ZLO + (np.arange(NBINS) + 0.5) * (ZHI - ZLO) / NBINS

    # gear from TRAIN-only crush-state ES5
    train = (full_idx >= TRAIN_LO) & (full_idx <= TRAIN_HI)
    crush_train = train & rarr & (z_old <= -0.75) & fwd20.notna()
    es5 = np.percentile(fwd20[crush_train], 5)
    gear_train = BUDGET / abs(es5)
    es5_full = 0.274
    log(f"ES5 TRAIN {es5*100:.1f}% -> gear_train {gear_train:.3f} "
        f"(old full-sample gear {BUDGET/es5_full:.3f})")

    rows = []
    for name, zz in (("old_norm", z_old), ("new_norm", z_new)):
        c = {}
        w = np.zeros(len(full_idx))
        maxc, zcut = build_curve(lvl, zz, fwd20, rarr, zcents, c, w)
        log(f"\n=== {name}: maxc {maxc*100:.1f}% zcut {zcut:+.2f} ===")
        rep_key = f"{name}_raw"
        net_raw = run_book(pd.Series(w, index=full_idx), h1_m, lvl, zz, 1.0)
        report(rep_key, net_raw, rows)
        report(f"{name}_gear_train", run_book(pd.Series(w, index=full_idx), h1_m, lvl, zz, gear_train), rows)

    with open(ROOT / "results" / "component_audit.csv", "w", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=["variant", "window", "n", "ann", "t",
                                             "lo90", "hi90", "neg", "worst"])
        wcsv.writeheader()
        for r in rows:
            wcsv.writerow(r)
        wcsv.writerow({"variant": "gear_meta_train", "window": "TRAIN", "t": gear_train,
                       "ann": es5})
    log("\nSaved results/component_audit.csv")


def sm_z(s, min_obs=12):
    return ((s - sm_expanding_mean(s, min_obs)) / sm_expanding_std(s, min_obs)).clip(-8, 8)


if __name__ == "__main__":
    main()
