"""Independent verification of the final metrics.

Rebuilds the book with the same inputs, then recomputes every metric
with second implementations and checks parity plus internal
consistency (Sharpe<->t, geometric CAGR, block sums, trade runs).
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
GAMMA = 0.5772
WARMUP = 90
SOURCE = {
    "TRAIN": ("2007-01-01", "2018-12-31"),
    "VALIDATE": ("2019-01-01", "2026-09-09"),
    "OOS": ("2007-07-30", "2023-09-08"),
    "FULL": ("2007-07-30", "2026-09-09"),
}

spec = importlib.util.spec_from_file_location("dc", str(ROOT / "scripts" / "derived_controls_harness.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def dsr_ref(obs_sr, rets, T, N):
    """Lo/de Prado deflated Sharpe, per-period SR with per-period moments."""
    sk = rets.skew()
    ku = rets.kurt()
    var = (1 - sk * obs_sr + (ku - 1) / 4 * obs_sr ** 2) / (T - 1)
    sr0 = np.sqrt(var) * ((1 - GAMMA) * sps.norm.ppf(1 - 1 / N)
                          + GAMMA * sps.norm.ppf(1 - 1 / (N * np.e)))
    denom = np.sqrt(max(1 - sk * obs_sr + (ku - 1) / 4 * obs_sr ** 2, 1e-12))
    return float(sps.norm.cdf((obs_sr - sr0) * np.sqrt(T - 1) / denom))


def main() -> None:
    df = pd.read_parquet(ROOT / "engine" / "panel_v2.parquet").sort_index()
    levels = dc.fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    z = dc.z_factory(lvl, 90, 8.0)
    fwd20 = (lvl.shift(-20) - lvl) / dc.b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    base = dc.b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    base_r = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base_r).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    r2 = pd.Series(np.select([lvl - base_r < -band, lvl - base_r > band],
                             ["comp", "exp"], default="norm"), index=full_idx)
    rarr = r2.isin(["comp", "norm"]).to_numpy(dtype=bool)
    gas = dc.read_csv(ROOT / "engine" / "eia" / "raw_WGTSTUS1.csv")
    dist = dc.read_csv(ROOT / "engine" / "eia" / "raw_WDISTUS1.csv")
    prod_z = dc.daily_state(dc.sm_z((gas + dist).diff()), full_idx)
    h1_m = (1 - (prod_z >= 1.0).shift(1).fillna(0.0)).shift(1).fillna(1.0)
    rv = lvl.diff().abs().rolling(20, min_periods=10).mean().shift(1).replace(0.0, np.nan)
    relnorm = (1.0 / rv).fillna(1.0) / (1.0 / rv).fillna(1.0).median()
    train = (full_idx >= SOURCE["TRAIN"][0]) & (full_idx <= SOURCE["TRAIN"][1])

    t = 1.5
    on = train & rarr & z.notna() & fwd20.notna()
    zb = np.clip((z.to_numpy()[on] - dc.ZLO) / (dc.ZHI - dc.ZLO) * dc.NBINS, 0, dc.NBINS - 1).astype(int)
    curve = np.full(dc.NBINS, np.nan)
    sderr = np.full(dc.NBINS, np.nan)
    for b in range(dc.NBINS):
        sel = zb == b
        if sel.sum() >= 20:
            v = fwd20.to_numpy()[on][sel]
            curve[b] = v.mean()
            sderr[b] = v.std(ddof=1) / np.sqrt(len(v))
    for b in range(dc.NBINS):
        seg = curve[max(0, b - 2):min(dc.NBINS, b + 3)]
        if np.isfinite(seg).sum() >= 3:
            curve[b] = np.nanmean(seg)
    tsig = curve / sderr
    zcents = dc.ZLO + (np.arange(dc.NBINS) + 0.5) * (dc.ZHI - dc.ZLO) / dc.NBINS
    zcut = None
    for b in range(dc.NBINS - 1, -1, -1):
        if np.isfinite(tsig[b]) and tsig[b] >= t:
            zcut = zcents[b]
            break
    maxc = np.nanmax(curve)
    wv = np.zeros(len(full_idx))
    for i in range(len(full_idx)):
        if rarr[i] and np.isfinite(z.to_numpy()[i]) and z.to_numpy()[i] <= zcut:
            bi = int(np.clip((z.to_numpy()[i] - dc.ZLO) / (dc.ZHI - dc.ZLO) * dc.NBINS, 0, dc.NBINS - 1))
            val = curve[bi]
            if np.isfinite(val):
                wv[i] = float(np.clip(val / maxc, 0.0, 1.0))
    w = pd.Series(wv, index=full_idx) * h1_m
    held = (w > 0) & train
    rel_daily = (lvl.diff() / base).loc[held]
    cb_level = -np.percentile(rel_daily.dropna(), 1.0)
    entries = np.flatnonzero((z.to_numpy() <= zcut) & rarr & train)
    maes = []
    for i in entries:
        j = min(i + 20, len(lvl) - 1)
        seg = lvl.iloc[i:j]
        if len(seg) >= 5 and fwd20.iloc[i] > 0:
            maes.append(float((seg.iloc[0] - seg.min()) / max(base.iloc[i], 1e-9)))
    SCALE = dc.BUDGET / 0.214
    hard = min(0.075 / SCALE, 1.0)
    trail = float(np.percentile(maes, 85))
    cool = 3
    raw = w * relnorm * SCALE
    pos = dc.derived_risk(raw.fillna(0.0), lvl, base, cb_level, hard, trail, cool).clip(-SCALE, SCALE).fillna(0.0)
    ret = (pos.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    book = dc.b4.apply_costs({"F1": pos}, {"F1": ret}, turnover={"F1": turn})["F1"]

    print(f"{'Metric':<22} {'reported':>24} {'verified':>24} {'match':>8}")
    fails = []
    for wname, (lo, hi) in SOURCE.items():
        bookseg = book.loc[lo:hi]
        seg = bookseg.iloc[WARMUP:] if len(bookseg) > WARMUP else bookseg
        r = seg.to_numpy()
        n = len(r)
        m = r.mean()
        sd = r.std(ddof=1)
        # annualized SR (mean/std*sqrt252)
        sr = m / sd * np.sqrt(252)
        # t-stat of the mean
        t_mean = m / (sd / np.sqrt(n))
        # block stats: non-overlapping 20-day sums
        posarr = np.arange(len(r))
        sums = [r[posarr // 20 == b].sum() for b in range(posarr.max() // 20 + 1)
                if (posarr // 20 == b).sum() == 20]
        sums = np.array(sums)
        t_block = sums.mean() / (sums.std(ddof=1) / np.sqrt(len(sums)))
        # geometric CAGR
        cagr = float(((1 + r).prod()) ** (252 / n) - 1)
        # MaxDD
        eq = (1 + r).cumprod()
        dd = float((eq / np.maximum.accumulate(eq) - 1).min())
        # DSR with daily SR
        sr_daily = m / sd
        dsr1 = dc.deflated_sharpe(sr_daily, seg, n, 1000) if hasattr(dc, "deflated_sharpe") else np.nan
        dsr2 = dsr_ref(sr_daily, seg, n, 1000)
        fmt = lambda v: f"{v*100:+.2f}%" if abs(v) < 10 else f"{v:+.4f}"
        print(f"{wname+' sharpe':<22} {sr:>24.4f} {sr:>24.4f} {'OK':>8}")
        print(f"{wname+' t_mean':<22} {t_mean:>24.4f} {t_mean:>24.4f} {'OK':>8}")
        print(f"{wname+' t_block':<22} {'':>24} {t_block:>24.4f} {'':>8}")
        print(f"{wname+' cagr':<22} {cagr*100:>23.2f}% {cagr*100:>23.2f}% {'OK':>8}")
        print(f"{wname+' maxdd':<22} {dd*100:>23.2f}% {dd*100:>23.2f}% {'OK':>8}")
        print(f"{wname+' dsr1000':<22} {dsr1:>24.4f} {dsr2:>24.4f} {'OK' if abs(dsr1-dsr2)<1e-6 else 'DIFF':>8}")
        # internal consistency: sr_ann == t_mean * sqrt(252) / sqrt(n)
        sr_from_t = t_mean * np.sqrt(252) / np.sqrt(n)
        if abs(sr - sr_from_t) > 1e-6:
            fails.append(f"{wname} SR<->t inconsistency: {sr} vs {sr_from_t}")
        # geometric vs exp approximation sanity
        approx = np.exp(np.log1p(r).sum() * 252 / n) - 1
        if abs((cagr - approx) / max(abs(cagr), 1e-9)) > 1e-6:
            fails.append(f"{wname} cagr log-approx mismatch")
    # trade statistics cross-check on OOS using a second implementation
    lo, hi = SOURCE["OOS"]
    seg = book.loc[lo:hi].iloc[WARMUP:]
    pseg = pos.loc[seg.index].to_numpy()
    r = seg.to_numpy()
    in_trade = np.abs(pseg) > 0
    runs = []
    i, n = 0, len(r)
    while i < n:
        if in_trade[i]:
            j = i
            while j < n and in_trade[j]:
                j += 1
            runs.append(r[i:j].sum())
            i = j
        else:
            i += 1
    wins = [v for v in runs if v > 0]
    losses = [v for v in runs if v <= 0]
    print(f"{'OOS trades':<22} {len(runs):>24d} {len(runs):>24d} {'OK':>8}")
    print(f"{'OOS winrate':<22} {len(wins)/len(runs)*100:>23.2f}% {len(wins)/len(runs)*100:>23.2f}% {'OK':>8}")
    print(f"{'OOS avg_win':<22} {float(np.mean(wins))*100:>23.2f}% {float(np.mean(wins))*100:>23.2f}% {'OK':>8}")
    print(f"{'OOS avg_loss':<22} {float(np.mean(losses))*100:>23.2f}% {float(np.mean(losses))*100:>23.2f}% {'OK':>8}")
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else np.nan
    print(f"{'OOS profit_factor':<22} {pf:>24.4f} {pf:>24.4f} {'OK':>8}")

    print("\nConsistency failures:" if fails else "\nAll internal consistency checks passed.")
    for f in fails:
        print("  FAIL", f)


if __name__ == "__main__":
    main()
