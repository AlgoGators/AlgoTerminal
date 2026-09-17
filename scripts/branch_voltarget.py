"""True in-engine volatility targeting, pass A/B/C (causal, daily gear).

Pass A: per year, fit curve/controls on prior data; compute the w
exposure series for that year's days (causal) + per-year stops.
Pass B: gear_t = clip(target_ann_vol / forecast_ann_vol_t, 0, 1),
forecast = trailing 20d std (shift 1) of (w * unit_return) -- the
vol of the actual signal-bearing book returns, so realized book vol
converges to the target when the cap permits.
Pass C: positions = derived_risk(w * gear * scale) per year.
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
TARGET_VOL = 0.10
FIRST_EVAL, LAST_EVAL = 2012, 2026
NBINS = 24
ZLO, ZHI = -4.0, 1.5
MIN_BIN = 20
MIN_FIT = 100
BUDGET = 0.10

spec = importlib.util.spec_from_file_location("dc", str(ROOT / "scripts" / "derived_controls_harness.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def deflated_sharpe(sr, rets, T, N):
    sk = rets.skew()
    ku = rets.kurt()
    V = (1 - sk * sr + (ku - 1) / 4 * sr ** 2) / (T - 1)
    if V <= 0 or not np.isfinite(V):
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
            f = fs[m]
            mean = f.mean()
            p5 = np.percentile(f, 5)
            if abs(p5) >= mean and mean < 0.10:
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
    unit_ret = (lvl.diff() / base).fillna(0.0)
    lvl_n = lvl.to_numpy(dtype=float)
    tbar = ctrl["tbar"]
    ss = ctrl["stor"]
    tp = ctrl["trail"]
    cq = ctrl["cb"]
    cool = int(ctrl["cool"])

    # ---- Pass A: per-year causal exposure + controls ----
    w_full = np.zeros(len(full_idx))
    scale_full = np.ones(len(full_idx))
    per_year = {}
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
            scale = 1.0 if mode == "unit" else 0.5
        else:
            mu = crush.mean()
            var = crush.var(ddof=1)
            se = crush.std(ddof=1) / np.sqrt(len(crush))
            if mode == "anchor":
                scale = min(BUDGET / abs(np.percentile(crush, 5)), 1.0)
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
        per_year[y] = dict(emask=emask, w=w, scale=scale, cb=cb, trail=trail,
                           hard=hard, cool=cool)
        w_full[emask] = w[emask]
        scale_full[emask] = scale

    # ---- Pass B: causal gear on the signal-bearing book vol ----
    sig_ret = w_full * unit_ret.to_numpy(dtype=float)
    fvol = (pd.Series(sig_ret, index=full_idx).rolling(20, min_periods=10).std()
            .shift(1).replace(0.0, np.nan) * np.sqrt(252))
    gear = (TARGET_VOL / fvol).clip(0.0, 1.0).fillna(0.0).to_numpy(dtype=float)

    # ---- Pass C: positions per year ----
    all_ret = []
    all_pos = []
    all_gear = []
    for y, p in per_year.items():
        emask = p["emask"]
        raw = (pd.Series(p["w"], index=full_idx) * pd.Series(gear, index=full_idx)
               * p["scale"]).fillna(0.0)
        pos = dc.derived_risk(raw, lvl, base, p["cb"], p["hard"], p["trail"], p["cool"])
        pos = pos.clip(-p["scale"], p["scale"]).fillna(0.0)
        epos = pos[emask]
        ret = np.nan_to_num((epos.shift(1).fillna(0.0) * lvl.diff().loc[emask]
                             / base.loc[emask]).fillna(0.0).to_numpy())
        ret = pd.Series(ret, index=lvl.index[emask])
        turn = epos.diff().abs().fillna(0.0)
        net = dc.b4.apply_costs({"F1": epos}, {"F1": ret}, turnover={"F1": turn})["F1"]
        all_ret.append(net)
        all_pos.append(epos)
        all_gear.append(pd.Series(gear, index=full_idx)[emask])
    return pd.concat(all_ret), pd.concat(all_pos), pd.concat(all_gear)


def report(ret_full, pos_full, gear_full, tag):
    r = ret_full.to_numpy()
    n = len(r)
    vol = r.std(ddof=1) * np.sqrt(252)
    m = r.mean()
    sd = r.std(ddof=1)
    sr = m / sd * np.sqrt(252) if sd > 0 else np.nan
    eq = (1 + r).cumprod()
    cagr = float(((1 + r).prod()) ** (252 / n) - 1)
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    calmar = cagr / abs(dd) if dd else np.nan
    t_block, neg = block_metrics(r)
    dsr = deflated_sharpe(m / sd, pd.Series(r), n, 1000) if sd > 0 else np.nan
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
    mean_pos = np.abs(pos_full.to_numpy()).mean()
    dd_per_expo = abs(dd) / mean_pos if mean_pos > 0 else np.nan
    dd_vol = abs(dd) / vol if vol > 0 else np.nan
    mean_gear = gear_full.mean()
    print(f"{tag:22s} realized vol {vol*100:5.2f}% ann {m*252*100:+5.2f}% CAGR {cagr*100:+5.2f}% "
          f"Sh {sr:5.3f} DD {dd*100:6.2f}% Calmar {calmar:.2f} t {t_block:+.2f} DSR {dsr:.2f} "
          f"trades {len(runs)} PF {pf:.2f} mean_gear {mean_gear:.2f} dd/vol {dd_vol:.2f} "
          f"dd/expo {dd_per_expo:.2f}")
    s19 = ret_full[ret_full.index >= "2019-01-01"]
    if len(s19) > 200:
        r19 = s19.to_numpy()
        eq19 = (1 + r19).cumprod()
        dd19 = float((eq19 / np.maximum.accumulate(eq19) - 1).min())
        sr19 = r19.mean() / r19.std(ddof=1) * np.sqrt(252)
        print(f"{'':22s} 2019+ Sh {sr19:.3f} DD {dd19*100:6.2f}%")
    return dict(vol=vol, ann=m * 252, cagr=cagr, dd=dd, sh=sr, calmar=calmar,
                t=t_block, dsr=dsr, pf=pf, mean_gear=mean_gear, dd_vol=dd_vol,
                dd_per_expo=dd_per_expo)


def main() -> None:
    best = json.loads((ROOT / "results" / "sweep_big_best.json").read_text())[0]
    print("Frozen controls:", best, "target vol", TARGET_VOL, flush=True)
    rows = []
    for mode in ("unit", "kelly", "anchor", "kelly_half"):
        ret, pos, gear = run(mode, best)
        pd.DataFrame({"date": ret.index, "ret": ret.to_numpy(), "pos": pos.to_numpy(),
                      "gear": gear.to_numpy()}).to_csv(
            ROOT / "results" / f"branch_voltarget_{mode}_series.csv", index=False)
        m = report(ret, pos, gear, mode)
        m["mode"] = mode
        rows.append(m)
    pd.DataFrame(rows).to_csv(ROOT / "results" / "final_metrics_voltarget.csv", index=False)
    print("\nSaved results/branch_voltarget_*_series.csv + final_metrics_voltarget.csv")


if __name__ == "__main__":
    main()
