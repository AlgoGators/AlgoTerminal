"""Full metrics breakdown for the final derived configuration."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
GAMMA = 0.5772

spec = importlib.util.spec_from_file_location("dc", str(ROOT / "scripts" / "derived_controls_harness.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def deflated_sharpe(sr, rets, T, N):
    sk = rets.skew()
    ku = rets.kurt()
    V = (1 - sk * sr + (ku - 1) / 4 * sr ** 2) / (T - 1)
    if V <= 0:
        return np.nan
    sr0 = np.sqrt(V) * ((1 - GAMMA) * sps.norm.ppf(1 - 1 / N)
                        + GAMMA * sps.norm.ppf(1 - 1 / (N * np.e)))
    denom = np.sqrt(max(1 - sk * sr + (ku - 1) / 4 * sr ** 2, 1e-12))
    return float(sps.norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom))


def trade_stats(net_arr, pos_arr):
    in_trade = np.abs(pos_arr) > 0
    runs = []
    i, n = 0, len(net_arr)
    while i < n:
        if in_trade[i]:
            j = i
            while j < n and in_trade[j]:
                j += 1
            runs.append(float(net_arr[i:j].sum()))
            i = j
        else:
            i += 1
    wins = [r for r in runs if r > 0]
    losses = [r for r in runs if r <= 0]
    return {
        "trades": len(runs),
        "winrate": len(wins) / len(runs) if runs else np.nan,
        "avg_win": float(np.mean(wins)) if wins else 0.0,
        "avg_loss": float(np.mean(losses)) if losses else 0.0,
        "profit_factor": float(sum(wins) / abs(sum(losses))) if losses and sum(losses) else np.nan,
        "exposure_days": float(in_trade.mean()),
    }


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
    train = (full_idx >= dc.TRAIN_LO) & (full_idx <= dc.TRAIN_HI)

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

    out = []
    print(f"{'Metric':<26} {'TRAIN':>14} {'VALIDATE':>14} {'OOS':>14} {'FULL':>14}")
    rows = []
    windows = (("TRAIN", dc.TRAIN_LO, dc.TRAIN_HI), ("VALIDATE", dc.VAL_LO, dc.VAL_HI),
               ("OOS", dc.OOS_LO, dc.OOS_HI), ("FULL", dc.FULL_LO, dc.FULL_HI))
    per = {}
    for wname, lo, hi in windows:
        seg = book.loc[lo:hi].iloc[dc.WARMUP:] if len(book.loc[lo:hi]) > dc.WARMUP else book.loc[lo:hi]
        pseg = pos.loc[seg.index]
        r = seg.to_numpy()
        n = len(r)
        ann = r.mean() * 252
        vol = r.std(ddof=1) * np.sqrt(252)
        sr = ann / vol if vol else np.nan
        neg = r[r < 0]
        sortino = r.mean() * 252 / (neg.std(ddof=1) * np.sqrt(252)) if len(neg) > 1 and neg.std() else np.nan
        eq = (1 + r).cumprod()
        dd = float((eq / np.maximum.accumulate(eq) - 1).min())
        cagr = float(eq[-1] ** (252 / n) - 1) if n else np.nan
        ts = trade_stats(r, pseg.to_numpy())
        # DSR must use PER-PERIOD (daily) Sharpe with daily skew/kurtosis
        sr_daily = r.mean() / (r.std(ddof=1) if r.std(ddof=1) else np.nan)
        dsr243 = deflated_sharpe(sr_daily, seg, n, 243)
        dsr1000 = deflated_sharpe(sr_daily, seg, n, 1000)
        per[wname] = {"cagr": cagr, "sharpe": sr, "vol": vol, "sortino": sortino, "maxdd": dd,
                      "best_day": float(r.max()), "worst_day": float(r.min()), **ts,
                      "dsr243": dsr243, "dsr1000": dsr1000, "ann": ann, "t": sr * np.sqrt(n / 252)}
        rows.append({"window": wname, **per[wname]})

    for key in ("ann", "cagr", "sharpe", "dsr243", "dsr1000", "sortino", "vol", "maxdd",
                "best_day", "worst_day", "trades", "winrate", "avg_win", "avg_loss",
                "profit_factor", "exposure_days"):
        vals = []
        for wname, _, _ in windows:
            v = per[wname].get(key)
            if key in ("ann", "cagr", "vol", "maxdd", "best_day", "worst_day"):
                vals.append(f"{v*100:+.2f}%" if v == v else "   --")
            elif key in ("winrate", "exposure_days"):
                vals.append(f"{v*100:6.1f}%" if v == v else "   --")
            elif key in ("sharpe", "dsr243", "dsr1000", "sortino"):
                vals.append(f"{v:+7.3f}" if v == v else "   --")
            elif key in ("trades",):
                vals.append(f"{int(v):>8d}" if v == v else "   --")
            else:
                vals.append(f"{v*100:+8.2f}%" if v == v else "   --")
        print(f"{key:<26} " + " ".join(f"{v:>12}" for v in vals))

    pd.DataFrame(rows).round(6).to_csv(ROOT / "results" / "metrics_final.csv", index=False)
    print("\nSaved results/metrics_final.csv")


if __name__ == "__main__":
    main()
