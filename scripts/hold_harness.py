"""Hold validation: non-overlapping, causal, single-shot test.

Rule card frozen in research/hold_validation.md (d375566) before the
validation window was measured. Only causal states are used. Forward
windows are non-overlapping (every 20th date).
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
EIA = ENGINE / "eia"
WEA = ENGINE / "weather"

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

TRAIN_END = "2018-12-31"
VALIDATE_START = "2019-01-01"


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


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    base = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    rel = lvl - base
    r2 = pd.Series(np.select([rel < -band, rel > band], ["comp", "exp"], default="norm"),
                   index=full_idx)
    zc = fb.seasonal_z(lvl)
    margin = pd.Series(np.select([zc <= -0.75, zc >= 0.75], ["crush", "stretch"], default="norm"),
                       index=full_idx)
    t2m = pd.read_csv(WEA / "raw_T2M_NYC.csv", index_col=0, parse_dates=True)["close"].reindex(full_idx)
    weather = pd.Series(sm_z(t2m) <= -1.0, index=full_idx)
    d_apr = np.abs((pd.to_datetime([pd.Timestamp(y, 4, 1) for y in full_idx.year]).to_numpy() - full_idx.to_numpy()).astype("timedelta64[D]").astype(int))
    d_sep = np.abs((pd.to_datetime([pd.Timestamp(y, 9, 15) for y in full_idx.year]).to_numpy() - full_idx.to_numpy()).astype("timedelta64[D]").astype(int))
    blend_switch = pd.Series(np.minimum(d_apr, d_sep) <= 21, index=full_idx)

    # non-overlapping 20d windows: every 20th date
    sampled = full_idx[::20]
    f = forward_level(lvl)
    fwd = f.loc[sampled]

    def stats(mask, name, win):
        idx = sampled[mask.reindex(sampled).fillna(False).to_numpy(dtype=bool)]
        idx = idx[win[0]:win[1]] if False else idx[(idx >= win[0]) & (idx < win[1])]
        vals = fwd.reindex(idx).dropna()
        if len(vals) < 5:
            log(f"  {name:<22} {len(vals):>3} obs — too few")
            return {"name": name, "n": len(vals), "mean": np.nan, "std": np.nan,
                    "t": np.nan, "ci90_lo": np.nan, "ci90_hi": np.nan, "pos_frac": np.nan}
        n = len(vals)
        m = vals.mean()
        s = vals.std(ddof=1)
        se = s / np.sqrt(n)
        t = m / se if se else np.nan
        lo, hi = m - 1.645 * se, m + 1.645 * se
        pos = float((vals > 0).mean())
        log(f"  {name:<22} n={n:>3} mean {m*100:+7.2f}% std {s*100:6.2f}% t={t:+5.2f} "
            f"90%CI [{lo*100:+6.2f},{hi*100:+6.2f}] pos {pos*100:.0f}%")
        return {"name": name, "n": n, "mean": m, "std": s, "t": t, "ci90_lo": lo,
                "ci90_hi": hi, "pos_frac": pos}

    windows = {"TRAIN": ("2007-01-01", TRAIN_END), "VALIDATE": (VALIDATE_START, "2026-09-09")}
    rows = []
    for wname, (lo, hi) in windows.items():
        log(f"\n=== {wname} {lo}..{hi} (non-overlapping 20d) ===")
        L = (r2.isin(["comp", "norm"])) & (margin == "crush")
        S = (r2.isin(["norm", "exp"])) & (margin == "stretch")
        for rname, mask in (("L long crush", L), ("S short stretch", S)):
            rows.append({**{"window": wname}, **stats(mask, rname, (lo, hi))})
        # cold tilt on L
        coldL = L & weather
        warmL = L & ~weather
        rows.append({**{"window": wname}, **stats(coldL, "L + cold", (lo, hi))})
        rows.append({**{"window": wname}, **stats(warmL, "L not cold", (lo, hi))})
        # blend suppression on L
        rows.append({**{"window": wname}, **stats(L & blend_switch, "L + blend switch", (lo, hi))})

    # yearly sign consistency on validation for L and S
    log("\nValidation yearly (non-overlap):")
    for rname, mask in (("L", L), ("S", S)):
        idx = sampled[mask.reindex(sampled).fillna(False).to_numpy(dtype=bool)]
        idx = idx[(idx >= VALIDATE_START)]
        vals = fwd.reindex(idx).dropna()
        by_year = vals.groupby(vals.index.year).mean()
        log(f"  {rname}: " + "  ".join(f"{y}:{m*100:+.1f}%" for y, m in by_year.items()))

    with open(ROOT / "results" / "hold_validation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["window", "name", "n", "mean", "std", "t", "ci90_lo", "ci90_hi", "pos_frac"])
        w.writeheader()
        w.writerows(rows)
    log("\nSaved results/hold_validation.csv")


def forward_level(level: pd.Series) -> pd.Series:
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    return ((level.shift(-20) - level) / base).rename("fwd20")


if __name__ == "__main__":
    main()
