"""Fully causal walk-forward: no constant is tuned on any evaluated year.

Every data-driven value used in evaluation year y is a function only of
data on or before Dec 31 of y-1:
  - exposure curve (binned E[fwd20|z] + smoothing)         fit on prior
  - entry cut zcut (largest bin center with bin t>=1.5)     derived on prior
  - ES5 scale = 0.10 / |ES5 prior crush fwd20|              derived on prior
  - circuit breaker = 1st percentile of prior held-day rel  derived on prior
  - hard stop = per-trade budget (same 10% anchor) / scale  derived, no extra constant
  - trail distance = 85th pct of prior winners' MAE          derived on prior
  - cooldown = median prior stop-event gap                   derived on prior
  - relnorm uses expanding median of 1/rv (causal, no future constant)

Remaining constants are conventions/windows (504, 90, bin grid, pctiles,
costs) or the named 10% risk anchor. None was tuned on the future.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
PANEL = Path(os.environ.get("PANEL", ROOT / "engine" / "panel_v2.parquet"))
PANEL_TAG = os.environ.get("PANEL_TAG", "walkforward_causal")
GAMMA = 0.5772
BUDGET = 0.10
TRAIL_PCT = 0.85
CB_PCT = 0.99
FIRST_EVAL = 2012
LAST_EVAL = 2026
NBINS = 24
ZLO, ZHI = -4.0, 1.5
MIN_BIN = 20
T_SIG = 1.5
MIN_FIT = 100
# ENTRY_RULE selects how the crush entry cut is derived from prior data.
#   max_significant_bin (default, historical): largest z-bin with t >= T_SIG.
#     This picks the LEAST-crushed qualifying bin, which contradicts the
#     long-when-crushed thesis and admitted zcut up to +0.70.
#   contiguous_crush: walk up from the lowest eligible z-bin while the bin
#     t stays >= T_SIG; cut = the top of that contiguous crush region.
ENTRY_RULE = os.environ.get("ENTRY_RULE", "max_significant_bin")


def z_lag_loo(lvl, lookback=90, clip=8.0, min_obs=30):
    """Seasonal z with LEAVE-CURRENT-YEAR-OUT same-month norm.

    The norm for date t uses ONLY same-month observations from PRIOR
    years, so the value being normalized can never contribute to its
    own norm. Falls back causally (ffill) when prior-year history is
    short. Recent 90-day stage is trailing-only (causal).
    """
    prev = lvl.shift(1)
    vals = prev.to_numpy(dtype=float)
    years = prev.index.year.to_numpy()
    months = prev.index.month.to_numpy()
    mean = pd.Series(np.nan, index=prev.index, dtype=float)
    std = pd.Series(np.nan, index=prev.index, dtype=float)
    for m in range(1, 13):
        msel = months == m
        if not msel.any():
            continue
        yrs_m = np.unique(years[msel])
        for y in yrs_m:
            prior = np.flatnonzero(msel & (years < y))
            if len(prior) >= min_obs:
                sel = np.flatnonzero(msel & (years == y))
                mean.iloc[sel] = vals[prior].mean()
                std.iloc[sel] = vals[prior].std(ddof=1)
    mean = mean.ffill()
    std = std.ffill()
    mean = mean.replace([np.inf, -np.inf], np.nan)
    std = std.replace([np.inf, -np.inf], np.nan)
    if os.environ.get("Z_LOO_DRIFT") == "1":
        resid = prev - mean
        drift = resid.expanding(min_periods=252).mean()
        mean = mean + drift.replace([np.inf, -np.inf], np.nan)
    adj = prev - mean
    a_mean = adj.rolling(lookback, min_periods=45).mean()
    a_std = adj.rolling(lookback, min_periods=45).std()
    valid = a_std.fillna(0.0) > (1e-4 * a_mean.abs()).fillna(0.0)
    z = (adj - a_mean) / a_std.where(valid)
    return z.replace([np.inf, -np.inf], np.nan).clip(-clip, clip)

spec = importlib.util.spec_from_file_location("dc", str(ROOT / "scripts" / "derived_controls_harness.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
dc.b4.TRADE_BPS = float(os.environ.get("TRADE_BPS", 5.0))
dc.b4.ROLL_BPS = float(os.environ.get("ROLL_BPS", 20.0))


def deflated_sharpe(sr_daily, rets, T, N):
    sk = rets.skew()
    ku = rets.kurt()
    V = (1 - sk * sr_daily + (ku - 1) / 4 * sr_daily ** 2) / (T - 1)
    if V <= 0:
        return np.nan
    sr0 = np.sqrt(V) * ((1 - GAMMA) * sps.norm.ppf(1 - 1 / N)
                        + GAMMA * sps.norm.ppf(1 - 1 / (N * np.e)))
    denom = np.sqrt(max(1 - sk * sr_daily + (ku - 1) / 4 * sr_daily ** 2, 1e-12))
    return float(sps.norm.cdf((sr_daily - sr0) * np.sqrt(T - 1) / denom))


def block_metrics(r):
    n = len(r)
    posarr = np.arange(n)
    sums = np.array([r[posarr // 20 == b].sum() for b in range(posarr.max() // 20 + 1)
                     if (posarr // 20 == b).sum() == 20])
    if len(sums) < 5:
        return np.nan, np.nan
    return float(sums.mean() / (sums.std(ddof=1) / np.sqrt(len(sums)))), float((sums < 0).mean())


def fit_curve(zv, fw, on, fit_idx):
    zb = np.clip((zv - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1).astype(int)
    curve = np.full(NBINS, np.nan)
    sd = np.full(NBINS, np.nan)
    nn = np.zeros(NBINS)
    for b in range(NBINS):
        m = zb == b
        nn[b] = int(m.sum())
        if m.sum() >= MIN_BIN:
            v = fw[m]
            curve[b] = v.mean()
            sd[b] = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan
    for b in range(NBINS):
        seg = curve[max(0, b - 2):min(NBINS, b + 3)]
        if np.isfinite(seg).sum() >= 3:
            curve[b] = np.nanmean(seg)
    maxc = np.nanmax(curve) if np.isfinite(curve).any() else np.nan
    return curve, sd, nn, maxc


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = dc.fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    if os.environ.get("Z_LOO") == "1" or os.environ.get("Z_LOO_DRIFT") == "1":
        z = z_lag_loo(lvl, 90, 8.0)
    else:
        z = dc.z_factory(lvl, 90, 8.0)
    zv = z.to_numpy(dtype=float)
    base = dc.b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    fwd20 = (lvl.shift(-20) - lvl) / base
    base_r = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base_r).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    r2 = pd.Series(np.select([lvl - base_r < -band, lvl - base_r > band],
                             ["comp", "exp"], default="norm"), index=full_idx)
    rarr = r2.isin(["comp", "norm"]).to_numpy(dtype=bool)
    gas = dc.read_csv(ROOT / "engine" / "eia" / "raw_WGTSTUS1.csv")
    dist = dc.read_csv(ROOT / "engine" / "eia" / "raw_WDISTUS1.csv")
    prod_z = dc.daily_state(dc.sm_z((gas + dist).diff()), full_idx)
    h1 = (prod_z >= 1.0).shift(1).fillna(0.0).to_numpy(dtype=bool)
    rv = lvl.diff().abs().rolling(20, min_periods=10).mean().shift(1).replace(0.0, np.nan)
    inv = (1.0 / rv).fillna(1.0)
    relnorm = (inv / inv.expanding(min_periods=252).median().fillna(inv.median())).fillna(1.0)

    lvl_n = lvl.to_numpy(dtype=float)
    base_n = base.to_numpy(dtype=float)
    fw_n = fwd20.to_numpy(dtype=float)
    diary = []

    for y in range(FIRST_EVAL, LAST_EVAL + 1):
        fit_end = pd.Timestamp(y, 1, 1) - pd.Timedelta(days=21)
        fit = full_idx < fit_end
        emask = (full_idx >= pd.Timestamp(y, 1, 1)) & (full_idx <= pd.Timestamp(y, 12, 31))
        on = fit & rarr & np.isfinite(zv) & np.isfinite(fw_n)
        if on.sum() < MIN_FIT:
            print(f"{y}: insufficient fit data ({int(on.sum())}), flat year")
            diary.append((y, dict(scale=0.0, cb=0.0, hard=0.0, trail=0.0, cool=0, zcut=np.nan)))
            continue
        curve, sd, nn, maxc = fit_curve(zv[on], fw_n[on], on, None)
        # entry cut: largest bin center with bin t >= 1.5 (prior data only)
        zcents = ZLO + (np.arange(NBINS) + 0.5) * (ZHI - ZLO) / NBINS
        tval = curve / sd
        cut = np.nan
        if ENTRY_RULE == "contiguous_crush":
            elig = np.flatnonzero(np.isfinite(tval) & (nn >= MIN_BIN))
            b = 0
            while b < len(elig) and tval[elig[b]] >= T_SIG:
                b += 1
            if b > 0:
                cut = zcents[elig[b - 1]] + 0.5 * (ZHI - ZLO) / NBINS
        else:
            use_bins = np.flatnonzero(np.isfinite(tval) & (tval >= T_SIG) & (nn >= MIN_BIN))
            if len(use_bins):
                cut = zcents[use_bins.max()]
        if not np.isfinite(cut) or not np.isfinite(maxc) or maxc <= 0:
            print(f"{y}: no significant bins on prior data, flat year")
            diary.append((y, dict(scale=0.0, cb=0.0, hard=0.0, trail=0.0, cool=0, zcut=np.nan)))
            continue
        # ES5 scale from prior crush
        crush = fw_n[fit & rarr & (zv <= cut)]
        es5 = np.percentile(crush[~np.isnan(crush)], 5) if crush[~np.isnan(crush)].size >= 50 else np.nan
        scale = min(BUDGET / abs(es5), 1.0) if np.isfinite(es5) and es5 != 0 else BUDGET / 0.214
        # weights on prior data for stops
        wv = np.zeros(len(full_idx))
        sig = fit & rarr & np.isfinite(zv) & (zv <= cut)
        for i in np.flatnonzero(sig):
            bi = int(np.clip((zv[i] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1))
            val = curve[bi]
            if np.isfinite(val):
                wv[i] = float(np.clip(val / maxc, 0.0, 1.0))
        held = (wv > 0) & fit & ~h1
        rel_daily = (lvl.diff() / base).to_numpy(dtype=float)
        cb_vals = rel_daily[held]
        cb_vals = cb_vals[~np.isnan(cb_vals)]
        cb = -np.percentile(cb_vals, 100 * (1 - CB_PCT)) if len(cb_vals) > 50 else 0.11
        hard = BUDGET / scale  # per-trade budget == the 10% anchor, no extra constant
        # trail from prior winning crush entries MAE (85th convention, distance measured)
        entries = np.flatnonzero(fit & rarr & (zv <= cut) & np.isfinite(fw_n))
        maes = []
        for i in entries[:2000]:
            j = min(i + 20, len(lvl) - 1)
            seg = lvl_n[i:j]
            if j - i >= 5 and fw_n[i] > 0 and base_n[i] and np.isfinite(base_n[i]):
                maes.append(float((seg[0] - seg.min()) / max(base_n[i], 1e-9)))
        trail = float(np.percentile(maes, 100 * TRAIL_PCT)) if maes else 0.03
        # cooldown: median gap between prior stop events (1..10)
        events = np.flatnonzero(held)
        gaps = np.diff(events)
        cool = int(np.clip(np.median(gaps[gaps > 0]), 1, 10)) if len(gaps) > 10 else 3
        diary.append((y, dict(scale=scale, cb=cb, hard=hard, trail=trail, cool=cool, zcut=cut)))
        # ---- apply to eval year ----
        wv = np.zeros(len(full_idx))
        sig = emask & rarr & np.isfinite(zv) & (zv <= cut)
        for i in np.flatnonzero(sig):
            bi = int(np.clip((zv[i] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1))
            val = curve[bi]
            if np.isfinite(val):
                wv[i] = float(np.clip(val / maxc, 0.0, 1.0))
        w = pd.Series(wv, index=full_idx)
        wmasks = (~pd.Series(h1, index=full_idx)).fillna(True)
        w = (w * wmasks).fillna(0.0)
        raw = (w * relnorm * scale).fillna(0.0)
        pos = dc.derived_risk(raw, lvl, base, cb, min(hard, 1.0), trail, cool).clip(-scale, scale).fillna(0.0)
        epos = pos[emask]
        ret = (epos.shift(1).fillna(0.0) * lvl.diff().loc[emask] / base.loc[emask]).fillna(0.0)
        turn = epos.diff().abs().fillna(0.0)
        net = dc.b4.apply_costs({"F1": epos}, {"F1": ret}, turnover={"F1": turn})["F1"]
        all_ret.append(net)
        all_pos.append(epos)
        print(f"{y}: zcut {cut:+.2f} scale {scale:.3f} cb {cb*100:.1f}% hard {min(hard,1.0)*100:.0f}% "
              f"trail {trail*100:.1f}% cool {cool}  year_ret {net.sum()*100:+.2f}%")

    ret_full = pd.concat(all_ret)
    pos_full = pd.concat(all_pos)
    r = ret_full.to_numpy()
    n = len(r)
    m = r.mean()
    sd = r.std(ddof=1)
    sr = m / sd * np.sqrt(252)
    sr_daily = m / sd
    ann = m * 252
    vol = sd * np.sqrt(252)
    eq = (1 + r).cumprod()
    cagr = float(((1 + r).prod()) ** (252 / n) - 1)
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    negd = r[r < 0]
    sortino = m * 252 / (negd.std(ddof=1) * np.sqrt(252)) if len(negd) > 1 and negd.std() else np.nan
    t_block, neg_blk = block_metrics(r)
    dsr = deflated_sharpe(sr_daily, ret_full, n, 1000)
    in_trade = np.abs(pos_full.to_numpy()) > 0
    runs = []
    i = 0
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
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else np.nan
    print("\n=== FULLY CAUSAL WALK-FORWARD (controls re-derived per year on prior data) ===")
    print(f"period: {ret_full.index.min().date()} .. {ret_full.index.max().date()}  days={n} ({n/252:.1f}y)")
    print(f"ann {ann*100:+.2f}%  CAGR {cagr*100:+.2f}%  vol {vol*100:.2f}%  Sh {sr:.3f}  Sortino {sortino:.3f}")
    print(f"MaxDD {dd*100:.2f}%  best {r.max()*100:+.2f}%  worst {r.min()*100:+.2f}%  block t {t_block:+.2f}  DSR1000 {dsr:.3f}")
    print(f"trades {len(runs)}  win {len(wins)/len(runs)*100:.1f}%  avgW {np.mean(wins)*100:+.2f}%  avgL {np.mean(losses)*100:+.2f}%  PF {pf:.2f}  exposure {in_trade.mean()*100:.1f}%")
    yearly = ret_full.groupby(ret_full.index.year).sum()
    print("\nyearly:")
    for y, v in yearly.items():
        print(f"  {y}: {v*100:+.2f}%")
    pd.DataFrame({"date": ret_full.index, "ret": ret_full.to_numpy(), "pos": pos_full.to_numpy(),
                  "scale": np.nan}).to_csv(ROOT / "results" / f"{PANEL_TAG}_series.csv", index=False)
    with open(ROOT / "results" / f"{PANEL_TAG}_diary.txt", "w") as f:
        for y, d in diary:
            f.write(f"{y} " + " ".join(f"{k}={d[k]}" for k in d) + "\n")
    print(f"\nSaved results/{PANEL_TAG}_series.csv + diary")
    if os.environ.get("Z_LOO") == "1":
        pd.DataFrame({"date": ret_full.index, "ret": ret_full.to_numpy(),
                      "pos": pos_full.to_numpy()}).to_csv(
            ROOT / "results" / "walkforward_causal_loo_series.csv", index=False)


all_ret: list = []
all_pos: list = []

if __name__ == "__main__":
    main()
