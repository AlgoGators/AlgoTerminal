"""BIG sweep of the five control knobs (stage 1 + stage 2).

Stage 1 (wide, vectorized, no stops): t-bar x storage-sigma grid.
Stage 2 (full risk sim on TRAIN): top (tbar, stor) pairs x trail pct
  x CB quantile x cooldown. Selection stat = non-overlapping block t
  on TRAIN. All screening is TRAIN-only; the honest OOS verdict runs
  in branches_unit_kelly.py (frozen controls, walk-forward 2019+).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
BUDGET = 0.10
TRAIN_LO, TRAIN_HI = "2007-07-30", "2018-12-31"
NBINS = 24
ZLO, ZHI = -4.0, 1.5
MIN_BIN = 20

spec = importlib.util.spec_from_file_location("dc", str(ROOT / "scripts" / "derived_controls_harness.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

T_BARS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
STOR_SIGMAS = [None, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
TRAIL_PCTS = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.975]
CB_QS = [0.50, 0.75, 0.90, 0.95, 0.99, 0.995, 0.999]
COOLS = [0, 1, 2, 3, 4, 5, 7, 10, 13]


def block_t(r):
    r = np.asarray(r, dtype=float)
    n = len(r)
    pos = np.arange(n)
    sums = np.array([r[pos // 20 == b].sum() for b in range(pos.max() // 20 + 1)
                     if (pos // 20 == b).sum() == 20])
    if len(sums) < 5:
        return np.nan
    return float(sums.mean() / (sums.std(ddof=1) / np.sqrt(len(sums))))


def set_up():
    df = pd.read_parquet(ROOT / "engine" / "panel_v2.parquet").sort_index()
    levels = dc.fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    z = dc.z_factory(lvl, 90, 8.0)
    zv = z.to_numpy(dtype=float)
    base = dc.b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    dl = lvl.diff().to_numpy(dtype=float)
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
    relnorm = (inv / inv.expanding(min_periods=252).median()).fillna(1.0)  # causal, neutral fallback
    tr = (full_idx >= TRAIN_LO) & (full_idx <= TRAIN_HI)
    return full_idx, lvl, zv, base, base_n, dl, fw_n, rarr, prod_z, relnorm, tr


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


def curve_weights(curve, maxc, zv, rarr, zcut):
    w = np.zeros(len(zv), dtype=float)
    if not np.isfinite(zcut) or not np.isfinite(maxc) or maxc <= 0:
        return w
    sig = rarr & np.isfinite(zv) & (zv <= zcut)
    for i in np.flatnonzero(sig):
        bi = int(np.clip((zv[i] - ZLO) / (ZHI - ZLO) * NBINS, 0, NBINS - 1))
        val = curve[bi]
        if np.isfinite(val):
            w[i] = float(np.clip(val / maxc, 0.0, 1.0))
    return w


def costed(exposure, dl, base_n, full_idx):
    ret = np.zeros(len(exposure))
    ok = np.flatnonzero(base_n > 0)
    ret[ok[ok > 0]] = (exposure[ok[ok > 0] - 1] * dl[ok[ok > 0]] / base_n[ok[ok > 0]])
    net = ret - 5.0 / 1e4 * np.abs(np.diff(exposure, prepend=0.0)) \
          - 20.0 / 252 / 1e4 * np.abs(exposure)
    return pd.Series(np.nan_to_num(net), index=full_idx)


def sim_config(expo, scale, cb_thresh, hard, trail_dist, cool, lvl, base, tr):
    pos = dc.derived_risk(pd.Series(expo * scale, index=lvl.index), lvl, base, cb_thresh, hard, trail_dist, cool)
    pos = pos.clip(-scale, scale)
    ret = np.zeros(len(pos))
    b = base.to_numpy(dtype=float)
    dlv = lvl.diff().to_numpy(dtype=float)
    p = pos.to_numpy(dtype=float)
    ok = np.flatnonzero(np.isfinite(b) & (b > 0))
    for i in ok:
        if i > 0:
            ret[i] = p[i - 1] * dlv[i] / b[i]
    net = np.nan_to_num(ret - 5.0 / 1e4 * np.abs(np.diff(p, prepend=0.0)) - 20.0 / 252 / 1e4 * np.abs(p))
    return block_t(net[tr][90:])


def stage1(curve, tval, nn, maxc, zcents, zv, rarr, prod_z, relnorm, dl, base_n, full_idx, tr):
    rows = []
    for tb in T_BARS:
        use = np.flatnonzero(np.isfinite(tval) & (tval >= tb) & (nn >= MIN_BIN))
        zcut = zcents[use.max()] if len(use) else np.nan
        if not np.isfinite(zcut):
            continue
        w = curve_weights(curve, maxc, zv, rarr, zcut)
        for ss in STOR_SIGMAS:
            gated = np.zeros(len(prod_z), dtype=bool)
            if ss is not None:
                gated = prod_z >= ss
            gated = np.roll(gated, 2)
            gated[:2] = False
            expo = (w * relnorm.to_numpy()).copy()
            expo[gated] = 0.0
            net = costed(expo, dl, base_n, full_idx)
            rows.append({"tbar": tb, "stor": ss, "zcut": zcut, "train_t": block_t(net.iloc[tr].to_numpy()[90:])})
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "sweep_big_stage1.csv", index=False)
    return df


def held_rel_daily(expo, lvl, base, tr):
    held = (expo > 0) & tr
    rel = (lvl.diff() / base).to_numpy(dtype=float)
    return rel[held], held


def winners_mae(zcut, zv, rarr, fw_n, lvl, base, tr):
    entries = np.flatnonzero(tr & rarr & (zv <= zcut) & np.isfinite(fw_n))
    maes = []
    lv = lvl.to_numpy(dtype=float)
    b = base.to_numpy(dtype=float)
    for i in entries[:3000]:
        j = min(i + 20, len(lv) - 1)
        seg = lv[i:j]
        if j - i >= 5 and fw_n[i] > 0 and b[i] and np.isfinite(b[i]):
            maes.append(float((seg[0] - seg.min()) / max(b[i], 1e-9)))
    return np.array(maes) if maes else np.array([0.03])


def stage2(df1, curve, maxc, zv, rarr, fw_n, prod_z, relnorm, dl, base_n, full_idx, tr, lvl, base):
    top = df1.sort_values("train_t", ascending=False).drop_duplicates("tbar").head(8)
    rows = []
    for _, prow in top.iterrows():
        tb, ss = prow["tbar"], prow["stor"]
        zcut = prow["zcut"]
        w = curve_weights(curve, maxc, zv, rarr, zcut)
        gated = np.zeros(len(prod_z), dtype=bool)
        if ss is not None:
            gated = prod_z >= ss
        gated = np.roll(gated, 2)
        gated[:2] = False
        expo = (w * relnorm.to_numpy()).copy()
        expo[gated] = 0.0
        rel_held, _ = held_rel_daily(expo, lvl, base, tr)
        maes = winners_mae(zcut, zv, rarr, fw_n, lvl, base, tr)
        crush = fw_n[tr & rarr & (zv <= zcut)]
        es5 = np.percentile(crush[~np.isnan(crush)], 5) if crush[~np.isnan(crush)].size >= 50 else -0.214
        scale = min(BUDGET / abs(es5), 1.0)
        for tp in TRAIL_PCTS:
            trail_dist = float(np.percentile(maes, 100 * tp)) if len(maes) > 5 else 0.03
            for cq in CB_QS:
                cb_thresh = -np.percentile(rel_held, 100 * (1 - cq)) if len(rel_held) > 50 else 0.11
                for cool in COOLS:
                    hard = min(BUDGET / scale, 1.0)
                    t = sim_config(expo, scale, cb_thresh, hard, trail_dist, cool, lvl, base, tr)
                    rows.append({"tbar": tb, "stor": ss, "zcut": zcut, "trail": tp,
                                 "cb": cq, "cool": cool, "scale": scale, "train_t": t})
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "sweep_big_stage2.csv", index=False)
    return df


def main() -> None:
    full_idx, lvl, zv, base, base_n, dl, fw_n, rarr, prod_z, relnorm, tr = set_up()
    zcents = ZLO + (np.arange(NBINS) + 0.5) * (ZHI - ZLO) / NBINS
    curve, sd, nn, tval, maxc = fit_curve(tr, zv, fw_n, rarr)
    print("stage 1: tbar x storage grid...", flush=True)
    df1 = stage1(curve, tval, nn, maxc, zcents, zv, rarr, prod_z, relnorm, dl, base_n, full_idx, tr)
    print(f"stage1 rows={len(df1)}")
    marg = df1.groupby("tbar").train_t.agg(["mean", "max"]).round(3)
    print("marginal t by tbar:\n", marg.to_string())
    print("\nstage1 best 25:\n", df1.sort_values("train_t", ascending=False).head(25).to_string())
    print("\nstage 2: full risk sim, top (tbar,stor) x trail x cb x cool...", flush=True)
    df2 = stage2(df1, curve, maxc, zv, rarr, fw_n, prod_z, relnorm, dl, base_n, full_idx, tr, lvl, base)
    print(f"stage2 rows={len(df2)}")
    print("\nstage2 best 20:\n", df2.sort_values("train_t", ascending=False).head(20).to_string())
    print("\nstage2 marginal by knob (train_t mean):")
    for k in ("trail", "cb", "cool"):
        print(f"  {k}:\n", df2.groupby(k).train_t.agg(["mean", "max"]).round(3).to_string().replace("\n", "\n  "))
    df2.sort_values("train_t", ascending=False).head(1).to_json(ROOT / "results" / "sweep_big_best.json", orient="records")


if __name__ == "__main__":
    main()
