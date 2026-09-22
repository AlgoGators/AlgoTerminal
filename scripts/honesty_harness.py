"""Honesty pass: non-overlap restatement of the champion and the
EIA-scaled verdict. No new hypotheses. Blocks are non-overlapping
20-trading-day windows; overlay path-dependence is flagged.
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

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

BLOCK = 20
WARMUP = 90


def log(msg: str) -> None:
    print(msg, flush=True)


def read_csv(path: Path, col: str = "close") -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[col].astype(float)


def sm_expanding_mean(s: pd.Series, min_obs: int = 12) -> pd.Series:
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


def sm_expanding_std(s: pd.Series, min_obs: int = 12) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        var = ((sub - sub.expanding().mean().shift(1)).pow(2)).expanding().mean().shift(1)
        sd = var.pow(0.5)
        sd[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = sd
    return out


def sm_z(s: pd.Series, min_obs: int = 12) -> pd.Series:
    return ((s - sm_expanding_mean(s, min_obs)) / sm_expanding_std(s, min_obs)).clip(-8, 8)


def daily_state(weekly: pd.Series, index: pd.Index) -> pd.Series:
    av = weekly.copy()
    av.index = av.index + pd.Timedelta(days=6)
    av = av[~av.index.duplicated(keep="last")].sort_index()
    idx = pd.DatetimeIndex(pd.to_datetime(index))
    return av.reindex(av.index.union(idx)).sort_index().ffill().reindex(idx)


def blocks_of(s: pd.Series) -> pd.Series:
    """Non-overlapping BLOCK-day block sums from a daily series."""
    s = s.dropna()
    out = {}
    pos = np.arange(len(s))
    blk = pos // BLOCK
    for b in range(blk.max() + 1):
        seg = s[blk == b]
        if len(seg) == BLOCK:
            out[s.index[blk == b][0]] = seg.sum()
    return pd.Series(out)


def block_stats(blocks: pd.Series, annualize: int = 252):
    if len(blocks) < 3:
        return None
    n = len(blocks)
    m = blocks.mean()
    sd = blocks.std(ddof=1)
    se = sd / np.sqrt(n)
    t = m / se if se else np.nan
    return {"n": n, "mean20": m, "ann": m * annualize / BLOCK, "std20": sd,
            "t": t, "lo90": m - 1.645 * se, "hi90": m + 1.645 * se,
            "neg_frac": float((blocks < 0).mean()), "worst": float(blocks.min()),
            "best": float(blocks.max())}


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    fac4, rets4, turn4 = b4.build_v4(levels, None)
    names = ["crack_321", "cross_sectional", "bzwti"]
    net = b4.apply_costs({k: fac4[k] for k in names},
                         {k: rets4[k] for k in names},
                         turnover={k: turn4[k] for k in names})
    book = b4.book_returns(net, names, b4.weight_scheme(net[names], "EQ"))
    book_ov = b4.apply_overlay(book)

    # sanity: reproduce champion headline
    oos = book.copy()
    oos_ov = book_ov.copy()
    full_sh = b4.stats(book)
    full_ov = b4.stats(book_ov)
    log(f"champion sanity: full raw Sh {full_sh['sharpe']:.3f} cv ov Sh {full_ov['sharpe']:.3f}")

    rows = []
    log("\nnon-overlap 20d blocks:")
    # NOTE (artifact audit 2026-09-22): the window labelled "OOS" below is
    # NOT out-of-sample. It spans 2007-07-30..2023-09-08 and fully contains
    # the training window 2007-2018, and it also overlaps the window labelled
    # "IS" (2023-09..2026-09). The labels are wrong. Numbers reported as
    # "OOS" here are in-sample. See findings/artifact_audit.md.
    print("WARNING: honesty_harness labels 2007-2023 as OOS, but that window "
          "contains the 2007-2018 training window. OOS numbers here are "
          "IN-SAMPLE. The only post-training segment is 2023-09 onward.")
    for wname, (lo, hi) in (("OOS", ("2007-07-30", "2023-09-08")),
                            ("IS", ("2023-09-08", "2026-09-09")),
                            ("FULL", ("2007-07-30", "2026-09-09"))):
        for tag, ser in (("raw", book), ("ov", book_ov)):
            seg = ser.loc[lo:hi].iloc[WARMUP:] if len(ser.loc[lo:hi]) > WARMUP else ser.loc[lo:hi]
            bl = blocks_of(seg)
            st = block_stats(bl)
            if not st:
                continue
            log(f"  {wname:<5} {tag:<3} n_blocks={st['n']:>3} mean/b {st['mean20']*100:+6.2f}% "
                f"ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f} 90%CI "
                f"[{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]% neg {st['neg_frac']*100:.0f}% "
                f"worst {st['worst']*100:+6.2f}%")
            rows.append({"block": "20d", "window": wname, "series": tag, **st})

    # EIA scaled redo
    log("\nEIA-scaled verdict redo (non-overlap, full sample, warmup 90):")
    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    util = read_csv(EIA / "raw_WPULEUS3.csv")
    prod_draw = daily_state(-sm_z((gas + dist).diff()), full_idx)
    util_ch = daily_state(sm_z(util.diff()), full_idx)
    score = prod_draw - util_ch
    full_scale = (score >= 1.0) & (prod_draw >= 0.5)
    half_scale = (score >= 0.0) & (prod_draw >= 0.0)
    scale = pd.Series(np.select([full_scale, half_scale], [1.0, 0.5], default=0.0),
                      index=full_idx).where(score.notna() & prod_draw.notna(), 1.0)
    crack_legs = ["crack_321", "cross_sectional"]
    scaled_book = pd.Series(0.0, index=full_idx)
    for k in names:
        pos = fac4[k]
        gross = rets4[k]
        if k in crack_legs:
            pos = pos * scale
            gross = gross * scale.shift(1).fillna(1.0)
        sl = b4.apply_costs({k: pos}, {k: gross})[k]
        scaled_book = scaled_book + sl / len(names)
    for tag, ser in (("baseline", book), ("scaled", scaled_book)):
        seg = ser.iloc[WARMUP:]
        bl = blocks_of(seg)
        st = block_stats(bl)
        log(f"  {tag:<8} n_blocks={st['n']:>3} mean/b {st['mean20']*100:+6.2f}% "
            f"ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f} 90%CI "
            f"[{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]% neg {st['neg_frac']*100:.0f}%")
        rows.append({"block": "20d", "window": "FULL", "series": tag, **st})

    with open(ROOT / "results" / "honesty_blocks.csv", "w", newline="") as f:
        fields = ["block", "window", "series", "n", "mean20", "ann", "std20",
                  "t", "lo90", "hi90", "neg_frac", "worst", "best"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    log("\nSaved results/honesty_blocks.csv")


if __name__ == "__main__":
    main()
