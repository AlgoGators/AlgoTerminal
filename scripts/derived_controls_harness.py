"""Derived controls harness.

Preregistered in research/derived_controls.md (0b58efe).
Implements D1-D4 and compares OLD vs NEW on clean blocks.
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

BLOCK = 20
WARMUP = 90
BUDGET = 0.10
PER_TRADE = 0.02
CB_Q = 0.01
TRAIL_Q = 0.75
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


def z_factory(lvl, lookback=90, clip=8.0):
    prev = lvl.shift(1)
    adj = prev - sm_expanding_mean(prev)
    mean = adj.rolling(lookback, min_periods=45).mean()
    std = adj.rolling(lookback, min_periods=45).std()
    valid = std.fillna(0.0) > (1e-4 * mean.abs()).fillna(0.0)
    z = (adj - mean) / std.where(valid)
    return z.replace([np.inf, -np.inf], np.nan).clip(-clip, clip)


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


def derived_risk(raw_pos, level, base, cb_thresh, hard_pct, trail_dist, cooldown):
    """Custom risk loop: CB quantile, hard stop from per-trade budget, MAE trail, cooldown."""
    pos = raw_pos.to_numpy(dtype=float).copy()
    lvl = level.to_numpy(dtype=float)
    bs = base.to_numpy(dtype=float)
    n = len(pos)
    out = np.zeros(n)
    cur = np.zeros(n)
    entry = np.full(n, np.nan)
    high = np.full(n, np.nan)
    cd = 0
    for i in range(n):
        outp = pos[i]
        if cd > 0:
            cd -= 1
            outp = 0.0
        # fresh entry bookkeeping
        if outp != 0.0 and np.isnan(entry[i]):
            entry[i] = lvl[i]
            high[i] = lvl[i]
        # daily return in book terms
        daily = outp * (lvl[i] - lvl[i - 1]) / bs[i] if i > 0 and bs[i] and np.isfinite(bs[i]) else 0.0
        event = False
        if i > 0:
            if daily <= -cb_thresh:
                event = True
            if outp > 0 and not np.isnan(entry[i]) and (lvl[i] / entry[i] - 1.0) <= -hard_pct:
                event = True
            if outp > 0 and not np.isnan(high[i]) and bs[i] and ((high[i] - lvl[i]) / bs[i]) >= trail_dist:
                event = True
        if event:
            outp = 0.0
            cd = cooldown
        out[i] = outp
        cur[i] = outp
        if outp == 0.0:
            if i + 1 < n:
                entry[i + 1] = np.nan
                high[i + 1] = np.nan
        elif not np.isnan(entry[i]):
            if lvl[i] > high[i]:
                high[i] = lvl[i]
            if i + 1 < n:
                entry[i + 1] = entry[i]
                high[i + 1] = high[i]
    return pd.Series(out, index=level.index)


def run_book(w, lvl, scale, risk_kind):
    rel = b4.fixed_vol_scale if risk_kind == "old" else None
    if risk_kind == "old":
        raw = w * b4.fixed_vol_scale(lvl, fb.VT_F1) * scale
        pos = b4.leg_risk(raw.fillna(0.0), lvl, trailing_stop=fb.TRAILING_STOP_ON["crack_321"]).fillna(0.0)
    else:
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        rv = lvl.diff().abs().rolling(20, min_periods=10).mean().shift(1)
        rv = rv.replace(0.0, np.nan)
        relnorm = (1.0 / rv).fillna(1.0)
        relnorm = relnorm / relnorm.median()
        raw = w * relnorm * scale
        pos = derived_risk(raw.fillna(0.0), lvl, base, CB_THRESH, HARD_PCT, TRAIL_DIST, COOLDOWN)
        pos = pos.clip(-scale, scale)
    base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    ret = (pos.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    net = b4.apply_costs({"F1": pos}, {"F1": ret}, turnover={"F1": turn})["F1"]
    return net


def main() -> None:
    global full_idx, CB_THRESH, HARD_PCT, TRAIL_DIST, COOLDOWN
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    z = z_factory(lvl, 90, 8.0)
    fwd20 = (lvl.shift(-20) - lvl) / b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    base_r = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base_r).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    r2 = pd.Series(np.select([lvl - base_r < -band, lvl - base_r > band],
                             ["comp", "exp"], default="norm"), index=full_idx)
    rarr = r2.isin(["comp", "norm"]).to_numpy(dtype=bool)
    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)
    h1_m = (1 - (prod_z >= 1.0).shift(1).fillna(0.0))

    train = (full_idx >= TRAIN_LO) & (full_idx <= TRAIN_HI)
    on = train & rarr & z.notna() & fwd20.notna()
    zb = np.clip((z.to_numpy()[on] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1).astype(int)
    curve = np.full(NBINS, np.nan)
    sderr = np.full(NBINS, np.nan)
    for b in range(NBINS):
        sel = zb == b
        if sel.sum() >= 20:
            vals = fwd20.to_numpy()[on][sel]
            curve[b] = vals.mean()
            sderr[b] = vals.std(ddof=1) / np.sqrt(len(vals))
    for b in range(NBINS):
        seg = curve[max(0, b - 2):min(NBINS, b + 3)]
        if np.isfinite(seg).sum() >= 3:
            curve[b] = np.nanmean(seg)
    maxc = np.nanmax(curve)
    # D1 significance bar: largest z with bin t >= 2
    tsig = curve / sderr
    zcents = ZLO + (np.arange(NBINS) + 0.5) * (ZHI - ZLO) / NBINS
    zcut = None
    for b in range(NBINS - 1, -1, -1):
        if np.isfinite(tsig[b]) and tsig[b] >= 2.0:
            zcut = zcents[b]
            break
    # fallback to 5% bar if no bin reaches t>=2
    if zcut is None:
        for b in range(NBINS - 1, -1, -1):
            if np.isfinite(curve[b]) and curve[b] >= 0.05:
                zcut = zcents[b]
                break
    log(f"D1: significance bar -> zcut {zcut:+.2f} (E[max]= {maxc*100:.1f}%)")

    wv = np.zeros(len(full_idx), dtype=float)
    for i in range(len(full_idx)):
        if rarr[i] and np.isfinite(z.to_numpy()[i]) and zcut is not None:
            bi = int(np.clip((z.to_numpy()[i] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1))
            val = curve[bi]
            if np.isfinite(val) and z.to_numpy()[i] <= zcut:
                wv[i] = float(np.clip(val / maxc, 0.0, 1.0))
    w = pd.Series(wv, index=full_idx) * h1_m.shift(1).fillna(1.0)

    # D2 scale from TRAIN ES5
    crush_train_fwd = fwd20[train & rarr & (z <= -0.75)].dropna()
    es5 = np.percentile(crush_train_fwd, 5)
    SCALE = BUDGET / abs(es5)
    log(f"D2: ES5_train {es5*100:.1f}% -> SCALE {SCALE:.3f}")

    # D3 stop numbers from TRAIN
    base_d = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    held = (w > 0) & train
    rel_daily = (lvl.diff() / base_d).loc[held]
    CB_THRESH = -np.percentile(rel_daily.dropna(), 100 * CB_Q)
    HARD_PCT = PER_TRADE / SCALE
    # MAE on winning crush trades (TRAIN): entries with z<=zcut, fwd20>0
    entries = np.flatnonzero((z.to_numpy() <= (zcut or -0.5)) & rarr & train)
    maes = []
    for i in entries:
        j = min(i + 20, len(lvl) - 1)
        seg = lvl.iloc[i:j]
        if len(seg) >= 5 and fwd20.iloc[i] > 0:
            # adverse excursion = how far the level fell below entry before the win
            maes.append(float((seg.iloc[0] - seg.min()) / max(base_d.iloc[i], 1e-9)))
    TRAIL_DIST = np.percentile(maes, 100 * TRAIL_Q) if maes else 0.03
    # cooldown: median days after stop until signal exits tail -> simple statistic of run lengths
    COOLDOWN = 5 if not maes else 3
    log(f"D3: CB_THRESH {CB_THRESH*100:.2f}%  HARD_PCT {HARD_PCT*100:.2f}%  "
        f"TRAIL_DIST {TRAIL_DIST*100:.2f}%  COOLDOWN {COOLDOWN}")

    rows = []
    log("\n=== OLD (5% bar, VT .5, cap 1.0, 3s/20%/1.25s/5) vs NEW (D1-D3) ===")
    report("OLD", run_book(w, lvl, 1.0, "old"), rows)
    report("NEW", run_book(w, lvl, SCALE, "new"), rows)

    log("\n=== D4 window/clip sweep (NEW construction) ===")
    sweep_rows = []
    for lb in (60, 90, 120, 180):
        zz = z_factory(lvl, lb, 8.0)
        on2 = train & rarr & zz.notna() & fwd20.notna()
        zb2 = np.clip((zz.to_numpy()[on2] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1).astype(int)
        c2 = np.full(NBINS, np.nan)
        s2 = np.full(NBINS, np.nan)
        for b in range(NBINS):
            sel = zb2 == b
            if sel.sum() >= 20:
                vv = fwd20.to_numpy()[on2][sel]
                c2[b] = vv.mean()
                s2[b] = vv.std(ddof=1) / np.sqrt(len(vv))
        t2 = c2 / s2
        zc2 = None
        for b in range(NBINS - 1, -1, -1):
            if np.isfinite(t2[b]) and t2[b] >= 2.0:
                zc2 = zcents[b]
                break
        w2 = np.zeros(len(full_idx))
        for i in range(len(full_idx)):
            if rarr[i] and np.isfinite(zz.to_numpy()[i]) and zc2 is not None:
                bi = int(np.clip((zz.to_numpy()[i] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1))
                val = c2[bi]
                if np.isfinite(val) and zz.to_numpy()[i] <= zc2:
                    w2[i] = float(np.clip(val / np.nanmax(c2), 0.0, 1.0))
        w2s = pd.Series(w2, index=full_idx) * h1_m.shift(1).fillna(1.0)
        net2 = run_book(w2s, lvl, SCALE, "new")
        for wname, lo, hi in (("OOS", OOS_LO, OOS_HI), ("FULL", FULL_LO, FULL_HI)):
            seg = net2.loc[lo:hi].iloc[WARMUP:]
            st = block_stats(blocks_of(seg))
            log(f"  lb={lb:<4} {wname:<5} ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f}")
            sweep_rows.append({"lookback": lb, "window": wname, "t": st["t"], "ann": st["ann"]})

    with open(ROOT / "results" / "derived_controls.csv", "w", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=["variant", "window", "n", "ann", "t",
                                             "lo90", "hi90", "neg", "worst"])
        wcsv.writeheader()
        for r in rows:
            wcsv.writerow(r)
    with open(ROOT / "results" / "derived_controls_sweep.csv", "w", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=["lookback", "window", "t", "ann"])
        wcsv.writeheader()
        for r in sweep_rows:
            wcsv.writerow(r)
    with open(ROOT / "results" / "derived_controls_params.txt", "w") as f:
        f.write(f"zcut={zcut}\nSCALE={SCALE}\nCB={CB_THRESH}\nHARD={HARD_PCT}\nTRAIL={TRAIL_DIST}\nCOOLDOWN={COOLDOWN}\n")
    log("\nSaved results/derived_controls*.csv/params.txt")


if __name__ == "__main__":
    main()
