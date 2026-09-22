"""Walk-forward honest metrics.

For each evaluation year, every data-driven component (exposure
curve, ES5 scale, CB threshold, MAE trail distance) is re-estimated
on data strictly before that year. The four hyperparameters (entry
bin t=1.5 line zcut -0.45, per-trade budget 7.5%, trail pct 85,
cooldown 3) are fixed constants and were chosen once on the 2007-2018
window (selection disclosed, not re-tuned per year). H1 gate and
regime identity are causal expanding constructions.

Evaluated years: 2012-2026 (each uses only prior data; 5 years of
minimum fit). Returns are net of 5/20 bps costs.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
# PANEL lets the identical machinery run on a different price panel
# (e.g. the roll-free spot panel) without touching defaults.
PANEL = Path(os.environ.get("PANEL", ROOT / "engine" / "panel_v2.parquet"))
PANEL_TAG = os.environ.get("PANEL_TAG", "walkforward")
GAMMA = 0.5772
WARMUP = 90
BUDGET = 0.10
HARD_BUDGET = 0.075
TRAIL_PCT = 0.85
COOL = 3
ZCUT = -0.45
CB_PCT = 0.99
FIRST_EVAL = 2012
LAST_EVAL = 2026

spec = importlib.util.spec_from_file_location("dc", str(ROOT / "scripts" / "derived_controls_harness.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)
# Cost overrides so the same machinery can be run at measured cost levels.
# Defaults reproduce the historical 5/20 bps.
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
    sums = [r[posarr // 20 == b].sum() for b in range(posarr.max() // 20 + 1)
            if (posarr // 20 == b).sum() == 20]
    sums = np.array(sums)
    t_block = float(sums.mean() / (sums.std(ddof=1) / np.sqrt(len(sums)))) if len(sums) >= 5 else np.nan
    neg = float((sums < 0).mean())
    return t_block, neg


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
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
    inv = (1.0 / rv).fillna(1.0)
    relnorm = (inv / inv.expanding(min_periods=252).median()).fillna(1.0)  # causal, neutral fallback

    all_ret = []
    all_pos = []
    years = []
    for y in range(FIRST_EVAL, LAST_EVAL + 1):
        fit_end = pd.Timestamp(y, 1, 1) - pd.Timedelta(days=21)
        fit = full_idx < fit_end
        eval_mask = (full_idx >= pd.Timestamp(y, 1, 1)) & (full_idx <= pd.Timestamp(y, 12, 31))
        # ---- fit curve on past data ----
        on = fit & rarr & z.notna() & fwd20.notna()
        if on.sum() < 100:
            print(f"{y}: insufficient fit data, skipping")
            continue
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
        maxc = np.nanmax(curve)
        # ---- scale from prior ES5 (crush state) ----
        crush_fit = fwd20[fit & rarr & (z <= ZCUT)].dropna()
        if len(crush_fit) >= 50:
            es5 = np.percentile(crush_fit, 5)
            scale = min(BUDGET / abs(es5), 1.0)
        else:
            scale = BUDGET / 0.214
        # ---- CB from prior held-day level returns ----
        wfit_v = np.zeros(len(full_idx))
        for i in np.flatnonzero(fit & rarr & np.isfinite(z.to_numpy()) & (z.to_numpy() <= ZCUT)):
            bi = int(np.clip((z.to_numpy()[i] - dc.ZLO) / (dc.ZHI - dc.ZLO) * dc.NBINS, 0, dc.NBINS - 1))
            val = curve[bi]
            if np.isfinite(val):
                wfit_v[i] = float(np.clip(val / maxc, 0.0, 1.0))
        wfit = pd.Series(wfit_v, index=full_idx) * h1_m
        held = (wfit > 0) & fit
        rel_daily = (lvl.diff() / base).loc[held]
        cb = -np.percentile(rel_daily.dropna(), 100 * (1 - CB_PCT)) if held.sum() > 50 else 0.11
        # ---- trail from prior winning-trade MAE ----
        entries = np.flatnonzero((z.to_numpy() <= ZCUT) & rarr & fit)
        maes = []
        for i in entries:
            j = min(i + 20, len(lvl) - 1)
            seg = lvl.iloc[i:j]
            if len(seg) >= 5 and fwd20.iloc[i] > 0:
                maes.append(float((seg.iloc[0] - seg.min()) / max(base.iloc[i], 1e-9)))
        trail = float(np.percentile(maes, 100 * TRAIL_PCT)) if maes else 0.03
        hard = min(HARD_BUDGET / scale, 1.0)
        # ---- apply to the eval year ----
        wv = np.zeros(len(full_idx))
        for i in np.flatnonzero(eval_mask & rarr & np.isfinite(z.to_numpy()) & (z.to_numpy() <= ZCUT)):
            bi = int(np.clip((z.to_numpy()[i] - dc.ZLO) / (dc.ZHI - dc.ZLO) * dc.NBINS, 0, dc.NBINS - 1))
            val = curve[bi]
            if np.isfinite(val):
                wv[i] = float(np.clip(val / maxc, 0.0, 1.0))
        w = pd.Series(wv, index=full_idx) * h1_m
        raw = (w * relnorm * scale).fillna(0.0)
        pos = dc.derived_risk(raw, lvl, base, cb, hard, trail, COOL).clip(-scale, scale).fillna(0.0)
        epos = pos[eval_mask]
        ret = (epos.shift(1).fillna(0.0) * lvl.diff().loc[eval_mask] / base.loc[eval_mask]).fillna(0.0)
        turn = epos.diff().abs().fillna(0.0)
        net = dc.b4.apply_costs({"F1": epos}, {"F1": ret}, turnover={"F1": turn})["F1"]
        all_ret.append(net)
        all_pos.append(epos)
        years.append(y)
        print(f"{y}: scale {scale:.3f} cb {cb*100:.1f}% trail {trail*100:.1f}% "
              f"year_ret {net.sum()*100:+.2f}%")

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
    cagr = float(((1 + r).prod()) ** (252 / n) - 1)
    eq = (1 + r).cumprod()
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    negd = r[r < 0]
    sortino = m * 252 / (negd.std(ddof=1) * np.sqrt(252)) if len(negd) > 1 and negd.std() else np.nan
    t_block, neg_blk = block_metrics(r)
    dsr1000 = deflated_sharpe(sr_daily, ret_full, n, 1000)
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
    print("\n=== WALK-FORWARD METRICS ===")
    print(f"period: {ret_full.index.min().date()} .. {ret_full.index.max().date()}  days={n} ({n/252:.1f}y)")
    print(f"annualized return {ann*100:+.2f}%  CAGR {cagr*100:+.2f}%  vol {vol*100:.2f}%")
    print(f"Sharpe {sr:.3f}  Sortino {sortino:.3f}  MaxDD {dd*100:.2f}%  best {r.max()*100:+.2f}%  worst {r.min()*100:+.2f}%")
    print(f"block t {t_block:+.2f}  neg blocks {neg_blk*100:.0f}%  DSR(1000) {dsr1000:.3f}")
    print(f"trades {len(runs)}  winrate {len(wins)/len(runs)*100:.1f}%  avg win {np.mean(wins)*100:+.2f}%  avg loss {np.mean(losses)*100:+.2f}%  PF {pf:.2f}  exposure {in_trade.mean()*100:.1f}%")
    yearly = ret_full.groupby(ret_full.index.year).sum()
    print("\nyearly returns:")
    for y, v in yearly.items():
        print(f"  {y}: {v*100:+.2f}%")
    pd.DataFrame({"date": ret_full.index, "ret": ret_full.to_numpy(), "pos": pos_full.to_numpy()}).to_csv(
        ROOT / "results" / f"{PANEL_TAG}_series.csv", index=False)
    print(f"\nSaved results/{PANEL_TAG}_series.csv")


if __name__ == "__main__":
    main()
