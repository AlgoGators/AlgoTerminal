"""Branch comparison after the big sweep.

Frozen controls come from sweep_big_best.json (TRAIN-only selection,
disclosed). Walk-forward 2012-2026: curve/scale-stats/CB/trail
distributions refit per year on prior data only; controls frozen.

Scale modes:
  ANCHOR: 0.10 / |ES5 prior crush|          (the old 10% budget)
  UNIT:   1.0                                (no sizing in the strategy)
  KELLY:  max(0, (mu - 1.645*se)) / var      (growth-optimal from prior crush)
  KELLY_HALF: KELLY / 2
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
GAMMA = 0.5772
FIRST_EVAL, LAST_EVAL = 2012, 2026
NBINS = 24
ZLO, ZHI = -4.0, 1.5
MIN_BIN = 20
MIN_FIT = 100

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


def block_metrics(r):
    n = len(r)
    pos = np.arange(n)
    sums = np.array([r[pos // 20 == b].sum() for b in range(pos.max() // 20 + 1)
                     if (pos // 20 == b).sum() == 20])
    if len(sums) < 5:
        return np.nan, np.nan
    return float(sums.mean() / (sums.std(ddof=1) / np.sqrt(len(sums)))), float((sums < 0).mean())


def fit_curve(fit, zv, fw_n, rarr):
    on = fit & rarr & np.isfinite(zv) & np.isfinite(fw_n)
    zb = np.clip((zv[on] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1).astype(int)
    curve = np.full(NBINS, np.nan)
    sd = np.full(NBINS, np.nan)
    nn = np.zeros(NBINS)
    for b in range(NBINS):
        m = zb == b
        nn[b] = int(m.sum())
        if m.sum() >= MIN_BIN:
            v = fw_n[on][m]
            curve[b] = v.mean()
            sd[b] = v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan
    for b in range(NBINS):
        seg = curve[max(0, b - 2):min(NBINS, b + 3)]
        if np.isfinite(seg).sum() >= 3:
            curve[b] = np.nanmean(seg)
    tval = curve / sd
    maxc = np.nanmax(curve) if np.isfinite(curve).any() else np.nan
    return curve, sd, nn, tval, maxc


def hard_crossing(fit, zcut, zv, rarr, fw_n, lvl_n, lo=-0.45, hi=0.10, nb=36):
    """Data-derived hard stop: drawdown depth where conditional 20d forward
    edge turns negative (mean - 1.645*SE <= 0). No crossing -> no hard stop."""
    entries = np.flatnonzero(fit & rarr & (zv <= zcut) & np.isfinite(fw_n))
    ds, fs = [], []
    for i in entries[:3000]:
        j = min(i + 20, len(lvl_n) - 1)
        for k in range(i, j):
            d = (lvl_n[k] - lvl_n[i]) / max(abs(lvl_n[i]), 1e-9)
            if lo <= d <= hi and np.isfinite(fw_n[k]):
                ds.append(d)
                fs.append(fw_n[k])
    if len(ds) < 50:
        return 1.0
    ds = np.array(ds)
    fs = np.array(fs)
    edges = np.linspace(lo, hi, nb)
    for b in range(nb - 1):
        m = (ds >= edges[b]) & (ds < edges[b + 1])
        if m.sum() >= 10:
            mean = fs[m].mean()
            se = fs[m].std(ddof=1) / np.sqrt(m.sum())
            if mean - 1.645 * se <= 0:
                return float(np.clip(-edges[b], 0.02, 1.0))
    return 1.0


def run(mode: str, ctrl: dict):
    df = pd.read_parquet(ROOT / "engine" / "panel_v2.parquet").sort_index()
    levels = dc.fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    z = dc.z_factory(lvl, 90, 8.0)
    zv = z.to_numpy(dtype=float)
    base = dc.b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    base_n = base.to_numpy(dtype=float)
    fwd20 = (lvl.shift(-20) - lvl) / base
    fw_n = fwd20.to_numpy(dtype=float)
    base_r = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base_r).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    r2 = pd.Series(np.select([lvl - base_r < -band, lvl - base_r > band],
                             ["comp", "exp"], default="norm"), index=full_idx)
    rarr = r2.isin(["comp", "norm"]).to_numpy(dtype=bool)
    gas = dc.read_csv(ROOT / "engine" / "eia" / "raw_WGTSTUS1.csv")
    dist = dc.read_csv(ROOT / "engine" / "eia" / "raw_WDISTUS1.csv")
    prod_z = dc.daily_state(dc.sm_z((gas + dist).diff()), full_idx).to_numpy(dtype=float)
    rv = lvl.diff().abs().rolling(20, min_periods=10).mean().shift(1).replace(0.0, np.nan)
    inv = (1.0 / rv).fillna(1.0)
    relnorm = (inv / inv.expanding(min_periods=252).median().fillna(inv.median())).fillna(1.0)
    lvl_n = lvl.to_numpy(dtype=float)
    tbar = ctrl["tbar"]
    ss = ctrl["stor"]
    tp = ctrl["trail"]
    cq = ctrl["cb"]
    cool = int(ctrl["cool"])

    all_ret = []
    all_pos = []
    diaries = []
    for y in range(FIRST_EVAL, LAST_EVAL + 1):
        fit = full_idx < (pd.Timestamp(y, 1, 1) - pd.Timedelta(days=21))
        emask = (full_idx >= pd.Timestamp(y, 1, 1)) & (full_idx <= pd.Timestamp(y, 12, 31))
        on = fit & rarr & np.isfinite(zv) & np.isfinite(fw_n)
        if on.sum() < MIN_FIT:
            continue
        curve, sd, nn, tval, maxc = fit_curve(fit, zv, fw_n, rarr)
        zcents = ZLO + (np.arange(NBINS) + 0.5) * (ZHI - ZLO) / NBINS
        use = np.flatnonzero(np.isfinite(tval) & (tval >= tbar) & (nn >= MIN_BIN))
        zcut = zcents[use.max()] if len(use) else np.nan
        if not np.isfinite(zcut) or not np.isfinite(maxc) or maxc <= 0:
            continue
        crush = fw_n[fit & rarr & (zv <= zcut)]
        crush = crush[~np.isnan(crush)]
        if len(crush) < 50:
            scale = BUDGET if mode.startswith("anchor") else (1.0 if mode == "unit" else 0.5)
        else:
            mu = crush.mean()
            var = crush.var(ddof=1)
            se = crush.std(ddof=1) / np.sqrt(len(crush))
            if mode == "anchor":
                scale = min(0.10 / abs(np.percentile(crush, 5)), 1.0)
            elif mode == "unit":
                scale = 1.0
            elif mode == "kelly":
                scale = float(np.clip(max(0.0, (mu - 1.645 * se)) / max(var, 1e-9), 0.0, 1.0))
            elif mode == "kelly_half":
                scale = float(np.clip(max(0.0, (mu - 1.645 * se)) / max(var, 1e-9) / 2.0, 0.0, 1.0))
            else:
                raise ValueError(mode)
        w = np.zeros(len(full_idx))
        sig = rarr & np.isfinite(zv) & (zv <= zcut)
        for i in np.flatnonzero(sig):
            bi = int(np.clip((zv[i] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1))
            val = curve[bi]
            if np.isfinite(val):
                w[i] = float(np.clip(val / maxc, 0.0, 1.0))
        gated = np.zeros(len(prod_z), dtype=bool)
        if ss is not None:
            gated = prod_z >= ss
        gated = np.roll(gated, 2)
        gated[:2] = False
        w = w * (~gated).astype(float)
        # CB + trail from prior data with frozen rule knobs
        held = (w > 0) & fit
        rel_daily = (lvl.diff() / base).to_numpy(dtype=float)
        cb_vals = rel_daily[held]
        cb_vals = cb_vals[~np.isnan(cb_vals)]
        cb = -np.percentile(cb_vals, 100 * (1 - cq)) if len(cb_vals) > 50 else 0.11
        entries = np.flatnonzero(fit & rarr & (zv <= zcut) & np.isfinite(fw_n))
        maes = []
        for i in entries[:2000]:
            j = min(i + 20, len(lvl) - 1)
            seg = lvl_n[i:j]
            if j - i >= 5 and fw_n[i] > 0 and base_n[i] and np.isfinite(base_n[i]):
                maes.append(float((seg[0] - seg.min()) / max(base_n[i], 1e-9)))
        trail = float(np.percentile(maes, 100 * tp)) if len(maes) > 5 else 0.03
        hard = hard_crossing(fit, zcut, zv, rarr, fw_n, lvl_n)
        diaries.append({"y": y, "zcut": round(zcut, 3), "scale": round(scale, 4),
                        "cb": round(cb, 4), "trail": round(trail, 4), "hard": round(hard, 4)})
        raw = (pd.Series(w, index=full_idx) * relnorm * scale).fillna(0.0)
        pos = dc.derived_risk(raw, lvl, base, cb, hard, trail, cool).clip(-scale, scale).fillna(0.0)
        epos = pos[emask]
        ret = np.nan_to_num((epos.shift(1).fillna(0.0) * lvl.diff().loc[emask] / base.loc[emask]).fillna(0.0).to_numpy())
        ret = pd.Series(ret, index=lvl.index[emask])
        turn = epos.diff().abs().fillna(0.0)
        net = dc.b4.apply_costs({"F1": epos}, {"F1": ret}, turnover={"F1": turn})["F1"]
        all_ret.append(net)
        all_pos.append(epos)
    ret_full = pd.concat(all_ret)
    pos_full = pd.concat(all_pos)
    return ret_full, pos_full, diaries


def report(ret_full, pos_full, tag):
    r = ret_full.to_numpy()
    n = len(r)
    m = r.mean()
    sd = r.std(ddof=1)
    sr = m / sd * np.sqrt(252) if sd > 0 else np.nan
    eq = (1 + r).cumprod()
    cagr = float(((1 + r).prod()) ** (252 / n) - 1)
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    t_block, neg = block_metrics(r)
    dsr = deflated_sharpe(m / sd, ret_full, n, 1000)
    in_t = np.abs(pos_full.to_numpy()) > 0
    runs = []
    i = 0
    while i < n:
        if in_t[i]:
            j = i
            while j < n and in_t[j]:
                j += 1
            runs.append(r[i:j].sum())
            i = j
        else:
            i += 1
    wins = [v for v in runs if v > 0]
    losses = [v for v in runs if v <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else np.nan
    if len(runs) == 0:
        print(f"{tag:22s} NO TRADES")
        return ret_full
    print(f"{tag:22s} ann {m*252*100:+6.2f}% CAGR {cagr*100:+6.2f}% Sh {sr:5.3f} "
          f"DD {dd*100:6.2f}% t {t_block:+5.2f} DSR {dsr:5.3f} trades {len(runs)} "
          f"win {len(wins)/len(runs)*100:.0f}% PF {pf:.2f} expo {in_t.mean()*100:.0f}%")
    s19 = ret_full[ret_full.index >= "2019-01-01"]
    if len(s19) > 200:
        r19 = s19.to_numpy()
        m19 = r19.mean()
        sd19 = r19.std(ddof=1)
        eq19 = (1 + r19).cumprod()
        dd19 = float((eq19 / np.maximum.accumulate(eq19) - 1).min())
        print(f"{'':22s} 2019+  ann {m19*252*100:+6.2f}% Sh {m19/sd19*np.sqrt(252):5.3f} DD {dd19*100:6.2f}%")
    return ret_full


def main() -> None:
    best = json.loads((ROOT / "results" / "sweep_big_best.json").read_text())[0]
    print("Frozen controls from TRAIN sweep:", best, flush=True)
    out = {}
    for mode in ("anchor", "unit", "kelly", "kelly_half"):
        ret, pos, diag = run(mode, best)
        pd.DataFrame({"date": ret.index, "ret": ret.to_numpy(), "pos": pos.to_numpy()}).to_csv(
            ROOT / "results" / f"branch_{mode}_series.csv", index=False)
        pd.DataFrame(diag).to_csv(ROOT / "results" / f"branch_{mode}_diary.csv", index=False)
        out[mode] = report(ret, pos, mode)
    print("\nSaved results/branch_{anchor,unit,kelly,kelly_half}_series.csv + diaries")


if __name__ == "__main__":
    main()
