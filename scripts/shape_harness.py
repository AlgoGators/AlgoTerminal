"""Shape pass: seasonal-norm assumption audit + conditional-mean curves.

The corrected method: read constants from the empirical shape, do not
pick them. This run measures the assumptions the seasonal norm makes
and estimates E[fwd | state] curves for margin levels.

Per research/self_assessment.md. No strategy machines here.
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
WEA = ENGINE / "weather"

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)


def log(msg: str) -> None:
    print(msg, flush=True)


def forward(level: pd.Series, h: int) -> pd.Series:
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    return ((level.shift(-h) - level) / base).rename(f"fwd{h}")


def sm_mean(s: pd.Series) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        out.loc[idx] = sub.expanding().mean().shift(1)
    return out


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    t2m = pd.read_csv(WEA / "raw_T2M_NYC.csv", index_col=0, parse_dates=True)["close"].reindex(full_idx)

    fwd10 = forward(levels["crack_321"], 10)
    fwd20 = forward(levels["crack_321"], 20)
    fwdg20 = forward(levels["crack_gas"], 20)

    rows = []
    log("=== ASSUMPTION AUDIT (crack_321) ===")

    # A3 mean vs median per month
    lvl = levels["crack_321"]
    gaps = []
    for m in range(1, 13):
        seg = lvl[lvl.index.month == m]
        gaps.append(seg.mean() - seg.median())
    log(f"A3 mean-median gap by month: max {max(gaps, key=abs):+.2f} "
        f"(months with |gap|>2: {sum(1 for g in gaps if abs(g) > 2)})")
    rows.append(("A3_max_mean_median_gap", max(gaps, key=abs)))

    # A4 intra-month homogeneity: early vs late half level
    day = np.array([d for d in full_idx.day], dtype=int)
    half = pd.Series(np.where(day <= 15, 0, 1), index=full_idx)
    eh = lvl[half == 0].mean()
    lh = lvl[half == 1].mean()
    log(f"A4 early-half {eh:.2f} vs late-half {lh:.2f} (delta {lh - eh:+.2f})")
    rows.append(("A4_early_late_delta", lh - eh))

    # A5 variance stability by period
    for tag, lo, hi in (("07-10", "2007-01-01", "2010-12-31"),
                        ("11-15", "2011-01-01", "2015-12-31"),
                        ("16-20", "2016-01-01", "2020-12-31"),
                        ("21-26", "2021-01-01", "2026-12-31")):
        seg = lvl.loc[lo:hi]
        log(f"A5 std {tag}: {seg.std():.2f}")
        rows.append((f"A5_std_{tag}", seg.std()))

    # A6 additive vs multiplicative: corr(monthly mean level, monthly std)
    ms = pd.DataFrame({"mean": lvl.groupby([lvl.index.year, lvl.index.month]).mean(),
                       "std": lvl.groupby([lvl.index.year, lvl.index.month]).std()}).dropna()
    corr_ms = ms["mean"].corr(ms["std"])
    log(f"A6 corr(monthly mean, monthly std) = {corr_ms:+.3f} (positive => multiplicative)")
    rows.append(("A6_mean_std_corr", corr_ms))

    # A8 gaussianity of deseasonalized z
    z = fb.seasonal_z(lvl)
    dz = (lvl - sm_mean(lvl)).dropna()
    log(f"A8 skew {dz.skew():+.2f} kurtosis {dz.kurt():+.2f} "
        f"(Gaussian kurtosis=3, skew=0)")
    rows.append(("A8_skew", dz.skew()))
    rows.append(("A8_kurtosis", dz.kurt()))

    # A2 carrier: calendar vs temperature for gas-crack fwd
    r_cal = fwdg20.groupby(full_idx.month).mean().std()
    r_wea = fwdg20.groupby(pd.qcut(t2m, 10, labels=False, duplicates="drop")).mean().std()
    log(f"A2 carrier spread (calendar months) {r_cal*100:.2f}% vs "
        f"(temperature deciles) {r_wea*100:.2f}% on fwd20 gas")
    rows.append(("A2_calendar_spread", r_cal))
    rows.append(("A2_weather_spread", r_wea))

    # A10 regime interaction of the z-shape (P5 extension for crush side)
    regime = lvl.shift(1) > lvl.shift(1).rolling(252, min_periods=126).mean()
    exp = regime.to_numpy(dtype=bool)
    zz = z.to_numpy(dtype=float)
    f20 = fwd20.to_numpy(dtype=float)
    log("\n=== SHAPE: E[fwd20 | seasonal-z], by regime ===")
    for rname, mask in (("expansion", exp), ("compression", ~exp)):
        vals = []
        for lo, hi in [(-8, -1.5), (-1.5, -0.75), (-0.75, -0.25), (-0.25, 0.25),
                       (0.25, 0.75), (0.75, 1.5), (1.5, 8)]:
            sel = mask & ~np.isnan(zz) & ~np.isnan(f20) & (zz >= lo) & (zz < hi)
            if sel.sum() >= 20:
                vals.append((f"[{lo},{hi})", sel.sum(), f20[sel].mean()))
        line = "  ".join(f"{b}:{n},{m*100:+.1f}%" for b, n, m in vals)
        log(f"  {rname:<12} {line}")
        rows.append((f"shape_{rname}", ";".join(f"{b}:{m*100:.1f}" for b, _, m in vals)))

    # S1 season curve: E[fwd20] by month
    log("\n=== SHAPE: E[fwd20 | month] ===")
    sea = fwd20.groupby(full_idx.month).mean()
    log("  " + "  ".join(f"M{m}:{sea[m]*100:+.1f}%" for m in range(1, 13)))
    rows.append(("season_curve", ";".join(f"{m}:{sea[m]*100:.1f}" for m in range(1, 13))))

    # S3 depth curve: E[fwd20 | |z|] on crushed days (z <= -0.5), continuous bins
    log("\n=== SHAPE: E[fwd20 | crush depth] (z <= -0.5) ===")
    on = (zz <= -0.5) & ~np.isnan(f20)
    depth = np.abs(zz)
    if on.sum() >= 100:
        idxs = np.flatnonzero(on)
        q = pd.qcut(pd.Series(np.abs(zz[idxs])), 10, labels=False)
        curve = []
        for b in range(10):
            sel_full = np.zeros(len(full_idx), dtype=bool)
            sel_full[idxs[q.to_numpy() == b]] = True
            curve.append(f"d{b}:{f20[sel_full].mean()*100:+.1f}%")
        log("  " + "  ".join(curve))
        rows.append(("depth_curve", ";".join(curve)))

    with open(ROOT / "results" / "shape_pass.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["check", "value"])
        for k, v in rows:
            w.writerow([k, v if isinstance(v, str) else f"{v:.6f}"])
    log("\nSaved results/shape_pass.csv")


if __name__ == "__main__":
    main()
