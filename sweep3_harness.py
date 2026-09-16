"""Derived-controls sweep v3 (single-builder, anchor-first).

One file, one builder. The base construction is copied verbatim from
the verified derived_controls_harness. The anchor must reproduce
TRAIN t ~1.11 before the grid is trusted. Prereg:
research/derived_controls_sweep.md (02e08ba).
"""
from __future__ import annotations

import importlib.util
import csv
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("dc", str(ROOT / "derived_controls_harness.py"))
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)

PANEL = ROOT / "engine" / "panel_v2.parquet"
EIA = ROOT / "engine" / "eia"
TS = [1.5, 2.0, 2.5]
CBQS = [0.99, 0.995, 0.999]
BUDGETS = [0.02, 0.05, 0.075]
TRAILQS = [0.65, 0.75, 0.85]
COOLS = [0, 3, 5]
SCALE = dc.BUDGET / 0.214


def log(msg: str) -> None:
    print(msg, flush=True)


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
    gas = dc.read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = dc.read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = dc.daily_state(dc.sm_z((gas + dist).diff()), full_idx)
    gate = (prod_z >= 1.0)
    h1_m = (1 - gate.shift(1).fillna(0.0)).shift(1).fillna(1.0)
    rv = lvl.diff().abs().rolling(20, min_periods=10).mean().shift(1).replace(0.0, np.nan)
    relnorm = (1.0 / rv).fillna(1.0)
    relnorm = relnorm / relnorm.median()

    train = (full_idx >= dc.TRAIN_LO) & (full_idx <= dc.TRAIN_HI)
    pre = {}
    for t in TS:
        on = train & rarr & z.notna() & fwd20.notna()
        zb = np.clip((z.to_numpy()[on] - dc.ZLO) / (dc.ZHI - dc.ZLO) * dc.NBINS, 0, dc.NBINS - 1).astype(int)
        curve = np.full(dc.NBINS, np.nan)
        sderr = np.full(dc.NBINS, np.nan)
        for b in range(dc.NBINS):
            sel = zb == b
            if sel.sum() >= 20:
                vals = fwd20.to_numpy()[on][sel]
                curve[b] = vals.mean()
                sderr[b] = vals.std(ddof=1) / np.sqrt(len(vals))
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
        if zcut is None:
            for b in range(dc.NBINS - 1, -1, -1):
                if np.isfinite(curve[b]) and curve[b] >= 0.05:
                    zcut = zcents[b]
                    break
        maxc = np.nanmax(curve)
        wv = np.zeros(len(full_idx), dtype=float)
        for i in range(len(full_idx)):
            if rarr[i] and np.isfinite(z.to_numpy()[i]) and z.to_numpy()[i] <= zcut:
                bi = int(np.clip((z.to_numpy()[i] - dc.ZLO) / (dc.ZHI - dc.ZLO) * dc.NBINS, 0, dc.NBINS - 1))
                val = curve[bi]
                if np.isfinite(val):
                    wv[i] = float(np.clip(val / maxc, 0.0, 1.0))
        w = pd.Series(wv, index=full_idx) * h1_m
        held = (w > 0) & train
        rel_daily = (lvl.diff() / base).loc[held]
        # CB computed the VERIFIED way: level-return percentile, not scaled book rets
        cb_level = -np.percentile(rel_daily.dropna(), 1.0)
        # MAE the VERIFIED way
        entries = np.flatnonzero((z.to_numpy() <= zcut) & rarr & train)
        maes = []
        for i in entries:
            j = min(i + 20, len(lvl) - 1)
            seg = lvl.iloc[i:j]
            if len(seg) >= 5 and fwd20.iloc[i] > 0:
                maes.append(float((seg.iloc[0] - seg.min()) / max(base.iloc[i], 1e-9)))
        pre[t] = {"zcut": zcut, "w": w, "cb_level": cb_level, "maes": maes,
                  "entries": len(entries), "held_days": int(held.sum())}
        log(f"t={t}: zcut {zcut:+.3f} cb_level {cb_level*100:.2f}% entries {len(entries)} "
            f"held {held.sum()}")

    def build_book(t, q, bud, tq, cool):
        p = pre[t]
        cb = p["cb_level"]  # positive; derived_risk compares daily <= -cb
        hard = min(bud / SCALE, 1.0)
        trail = float(np.percentile(p["maes"], 100 * tq)) if p["maes"] else 0.03
        raw = p["w"] * relnorm * SCALE
        pos = dc.derived_risk(raw.fillna(0.0), lvl, base, cb, hard, trail, cool)
        pos = pos.clip(-SCALE, SCALE).fillna(0.0)
        ret = (pos.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
        turn = pos.diff().abs().fillna(0.0)
        net = dc.b4.apply_costs({"F1": pos}, {"F1": ret}, turnover={"F1": turn})["F1"]
        return net

    def block_t_of(net, lo, hi):
        seg = net.loc[lo:hi].iloc[dc.WARMUP:] if len(net.loc[lo:hi]) > dc.WARMUP else net.loc[lo:hi]
        bl = dc.blocks_of(seg)
        if len(bl) < 10 or bl.std(ddof=1) == 0:
            return 0.0
        st = dc.block_stats(bl)
        return float(st["t"]) if np.isfinite(st["t"]) else 0.0

    anchor = build_book(2.0, 0.99, 0.02, 0.75, 3)
    at = block_t_of(anchor, dc.TRAIN_LO, dc.TRAIN_HI)
    log(f"\nANCHOR (2.0,.99,.02,.75,3) TRAIN t = {at:+.2f} (must be ~1.11)")
    if at < 0.7:
        log("ANCHOR FAILED -> diagnostics:")
        p = pre[2.0]
        raw = p["w"] * relnorm * SCALE
        cb = -p["cb_level"]
        trail = float(np.percentile(p["maes"], 75)) if p["maes"] else 0.03
        pos = dc.derived_risk(raw.fillna(0.0), lvl, base, cb, min(0.02 / SCALE, 1.0), trail, 3)
        log(f"  w nonzero: {(p['w']>0).sum()}, raw nonzero: {(raw>0).sum()}, "
            f"pos nonzero (L1): {(pos>0).sum() / len(pos):.3f}")
        log(f"  cb={cb*100:.2f}% hard={min(0.02/SCALE,1.0)*100:.2f}% trail={trail*100:.2f}%")
        return

    rows_all = []
    for t in TS:
        if pre[t] is None or pre[t]["entries"] == 0:
            continue
        for q in CBQS:
            for bud in BUDGETS:
                for tq in TRAILQS:
                    for cool in COOLS:
                        net = build_book(t, q, bud, tq, cool)
                        tt = block_t_of(net, dc.TRAIN_LO, dc.TRAIN_HI)
                        rows_all.append({"t": t, "cb": q, "budget": bud, "trail": tq,
                                         "cool": cool, "zcut": pre[t]["zcut"],
                                         "entries": pre[t]["entries"], "train_t": tt})
    rows_all.sort(key=lambda r: -r["train_t"])
    with open(ROOT / "results" / "sweep3_grid.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t", "cb", "budget", "trail", "cool",
                                          "zcut", "entries", "train_t"])
        w.writeheader()
        for r in rows_all:
            w.writerow(r)
    log(f"\nconfigs {len(rows_all)}; top-6 TRAIN:")
    for r in rows_all[:6]:
        log(f"  {r}")
    log("\nMarginals (mean TRAIN t):")
    for key, vals in (("t", TS), ("cb", CBQS), ("budget", BUDGETS),
                      ("trail", TRAILQS), ("cool", COOLS)):
        means = [(v, float(np.mean([r["train_t"] for r in rows_all if r[key] == v]))) for v in vals]
        log(f"  {key:<7} " + "  ".join(f"{v}:{m:+.2f}" for v, m in means))
    log("\nTop-10 confirmatory:")
    tops = rows_all[:10]
    for cfg in tops:
        net = build_book(cfg["t"], cfg["cb"], cfg["budget"], cfg["trail"], cfg["cool"])
        outs = {k: block_t_of(net, lo, hi) for k, (lo, hi) in
                (("VALIDATE", (dc.VAL_LO, dc.VAL_HI)), ("OOS", (dc.OOS_LO, dc.OOS_HI)),
                 ("FULL", (dc.FULL_LO, dc.FULL_HI)))}
        log(f"  {cfg['t']},{cfg['cb']},{cfg['budget']},{cfg['trail']},{cfg['cool']} "
            f"TRAIN {cfg['train_t']:+.2f} | VAL {outs['VALIDATE']:+.2f} "
            f"OOS {outs['OOS']:+.2f} FULL {outs['FULL']:+.2f}")
        cfg.update({f"{k}_t": v for k, v in outs.items()})
    with open(ROOT / "results" / "sweep3_top10.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t", "cb", "budget", "trail", "cool",
                                          "zcut", "entries", "train_t",
                                          "VALIDATE_t", "OOS_t", "FULL_t"])
        w.writeheader()
        for r in tops:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    log("\nSaved results/sweep3_grid.csv, sweep3_top10.csv")


if __name__ == "__main__":
    main()
