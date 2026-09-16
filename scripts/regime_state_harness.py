"""Regime model pass: sub-regime distributions and transitions.

Per research/regime_model.md. Regime identity is estimated from the
data (Gaussian mixture on the deseasonalized level, plus a rolling
median/MAD baseline); sub-regime axes are tagged from data; the
distributions and conditional forward expectations come out per cell.

Descriptive pass: forward tables are causal at the state date but the
regime fit uses the full sample to define identity. Honest note:
trading rules will use causal state only.
"""
from __future__ import annotations

import importlib.util
import csv
from pathlib import Path

import numpy as np
import pandas as pd

ENGINE = Path("/home/sebas/algoterminal-strategy-v2/engine")
spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

from sklearn.mixture import GaussianMixture  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PANEL = ENGINE / "panel_v2.parquet"
EIA = ENGINE / "eia"
WEA = ENGINE / "weather"


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
        cs = sub.cumsum()
        ct = sub.notna().cumsum()
        mean = cs.shift(1) / ct.shift(1)
        mean[ct.shift(1) < min_obs] = np.nan
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


def forward(level: pd.Series, h: int) -> pd.Series:
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    return ((level.shift(-h) - level) / base).rename(f"fwd{h}")


def cell_stats(ret_daily: pd.Series, fwd: pd.Series, mask: pd.Series):
    m = mask & ret_daily.notna()
    if m.sum() < 20:
        return None
    r = ret_daily[m]
    f = fwd[m & fwd.notna()]
    return {"n": int(m.sum()), "mean": float(r.mean()), "std": float(r.std()),
            "med": float(r.median()), "p5": float(r.quantile(0.05)),
            "p95": float(r.quantile(0.95)), "fwd20": float(f.mean()) if len(f) else np.nan}


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    mon = np.array([m for m in full_idx.month], dtype=int)

    lvl = levels["crack_321"]
    dz = (lvl - sm_expanding_mean(lvl)).dropna()
    ret_d = lvl.diff() / b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    fwd20 = forward(lvl, 20)

    # ---- R1: Gaussian mixture regime on deseasonalized level ----
    zstd = (dz - dz.mean()) / dz.std()
    gmm = GaussianMixture(n_components=3, covariance_type="full", random_state=23).fit(zstd.to_numpy().reshape(-1, 1))
    post = gmm.predict_proba(zstd.to_numpy().reshape(-1, 1))
    state1 = pd.Series(np.argmax(post, axis=1), index=dz.index).reindex(full_idx)
    # name states by mean dz
    order = {s: dz[state1.reindex(dz.index) == s].mean() for s in range(3)}
    r1_name = {s: ("comp" if order[s] == min(order.values()) else "exp" if order[s] == max(order.values()) else "norm")
               for s in range(3)}
    state1_named = state1.map(r1_name)

    # ---- R2: rolling median/MAD baseline regime ----
    base = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    rel = lvl - base
    r2 = pd.Series(np.select([rel < -band, rel > band], ["comp", "exp"], default="norm"),
                   index=full_idx)
    r2 = r2.where(base.notna())

    # ---- axis states ----
    frac = lvl.groupby(lvl.index.month).mean()
    terc = frac.quantile([1 / 3, 2 / 3])
    phase = pd.Series([("peak" if frac[m] >= terc.iloc[1] else "trough" if frac[m] <= terc.iloc[0] else "shoulder")
                       for m in mon], index=full_idx, dtype=str)

    t2m = pd.read_csv(WEA / "raw_T2M_NYC.csv", index_col=0, parse_dates=True)["close"].reindex(full_idx)
    tz = sm_z(t2m)
    weather = pd.Series(np.select([tz <= -1.0, tz >= 1.0], ["cold", "warm"], default="mild"),
                        index=full_idx)
    hurr = pd.Series([1 if m in (6, 7, 8, 9, 10, 11) else 0 for m in mon], index=full_idx)
    freeze = pd.Series((full_idx >= "2021-02-01") & (full_idx <= "2021-02-28"), index=full_idx)

    dist_apr = np.abs((pd.to_datetime([pd.Timestamp(y, 4, 1) for y in full_idx.year]).to_numpy() - full_idx.to_numpy()).astype("timedelta64[D]").astype(int))
    dist_sep = np.abs((pd.to_datetime([pd.Timestamp(y, 9, 15) for y in full_idx.year]).to_numpy() - full_idx.to_numpy()).astype("timedelta64[D]").astype(int))
    dmin = np.minimum(dist_apr, dist_sep)
    blend = pd.Series(np.select([dmin <= 21, dmin <= 51], ["switch", "near"], default="far"),
                      index=full_idx)

    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)
    inv = pd.Series(np.select([prod_z <= -1.0, prod_z >= 1.0], ["draw", "build"], default="flat"),
                    index=full_idx)

    zc = fb.seasonal_z(lvl)
    margin = pd.Series(np.select([zc <= -0.75, zc >= 0.75], ["crush", "stretch"], default="norm"),
                       index=full_idx)

    axes = {"R1_gmm": state1_named, "R2_base": r2, "phase": phase, "weather": weather,
            "blend": blend, "inventory": inv, "margin": margin}
    rows = []
    for ax, s in axes.items():
        log(f"\n{ax}:")
        for name in sorted(set(s.dropna())):
            c = cell_stats(ret_d, fwd20, (s == name))
            if c:
                log(f"  {name:<8} n={c['n']:>4} daily mean {c['mean']*100:+.2f}% "
                    f"std {c['std']*100:.2f}% p5 {c['p5']*100:+.2f}% p95 {c['p95']*100:+.2f}% "
                    f"fwd20 {c['fwd20']*100:+.2f}%")
                rows.append({"axis": ax, "state": name, **c})

    log("\nTwo-way E[fwd20] (crack_321):")
    pairs = [("R2_base", "margin"), ("R2_base", "phase"), ("weather", "phase"),
             ("inventory", "phase"), ("blend", "phase"), ("weather", "margin"),
             ("R1_gmm", "margin")]
    for a, b in pairs:
        log(f"  {a} x {b}:")
        for sa in sorted(set(axes[a].dropna())):
            cells = []
            for sb in sorted(set(axes[b].dropna())):
                m = (axes[a] == sa) & (axes[b] == sb) & fwd20.notna()
                cells.append(f"{sb}:{fwd20[m].mean()*100:+.1f}%({int(m.sum())})" if m.sum() >= 15 else f"{sb}:.-")
            log(f"    {sa:<6} " + "  ".join(cells))

    # ---- transition matrix R2 ----
    seq = r2.dropna()
    states = ["comp", "norm", "exp"]
    tm = {s: {t: 0 for t in states} for s in states}
    a = seq.to_numpy(dtype=str)
    for i in range(len(a) - 1):
        if a[i] in tm and a[i + 1] in tm[a[i]]:
            tm[a[i]][a[i + 1]] += 1
    log("\nR2 regime transition matrix (fractions):")
    for s in states:
        tot = sum(tm[s].values())
        log(f"  {s:<5} " + " ".join(f"{t}:{v / tot:.2f}" if tot else f"{t}:0" for t, v in tm[s].items()))

    with open(ROOT / "results" / "regime_state.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["axis", "state", "n", "mean", "std", "med", "p5", "p95", "fwd20"])
        w.writeheader()
        for r in rows:
            if "n" in r:
                w.writerow({k: r.get(k, "") for k in w.fieldnames})
    log("\nSaved results/regime_state.csv")


if __name__ == "__main__":
    main()
