"""Final integration harness.

Preregistered in research/final_strategy.md (caab518). Variants:
V_Champ (reference), V3 (champion + H1), V1 (champion + regime
gate), V2 (regime gate + H1). Clean non-overlap blocks for
acceptance; overlay flagged path-dependent.
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
OOS = slice("2007-07-30", "2023-09-08")
OOS_FULL = ("2007-07-30", "2023-09-08")


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


def blocks_of(s: pd.Series) -> pd.Series:
    s = s.dropna()
    pos = np.arange(len(s))
    blk = pos // BLOCK
    out = {}
    for b in range(blk.max() + 1):
        seg = s[blk == b]
        if len(seg) == BLOCK:
            out[s.index[blk == b][0]] = seg.sum()
    return pd.Series(out)


def block_stats(blocks: pd.Series):
    n = len(blocks)
    m = blocks.mean()
    sd = blocks.std(ddof=1)
    se = sd / np.sqrt(n)
    return {"n": n, "mean20": m, "ann": m * 252 / BLOCK, "t": m / se if se else np.nan,
            "lo90": m - 1.645 * se, "hi90": m + 1.645 * se, "neg": float((blocks < 0).mean())}


def crack_gated(level, z, r2, use_regime, h1_gate):
    """Crack sleeve with optional regime gate and H1 de-risk."""
    zz = z.to_numpy(dtype=float)
    rg = r2.isin(["comp", "norm"]).to_numpy(dtype=bool)
    h1 = (1 - h1_gate.shift(1).fillna(0.0)).to_numpy(dtype=float)
    vals = np.zeros(len(level), dtype=float)
    state = 0.0
    reg_ok = True
    for i in range(len(level)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if use_regime:
            if not rg[i]:
                reg_ok = False
            elif not reg_ok:
                reg_ok = True
            if state == 1.0 and not rg[i]:
                state = 0.0
        if state == 0.0 and zz[i] <= -0.75 and (rg[i] if use_regime else True):
            state = 1.0
        elif state == 1.0 and zz[i] >= -0.5:
            state = 0.0
        vals[i] = state * h1[i]
    sig = pd.Series(vals, index=level.index)
    raw = sig * b4.fixed_vol_scale(level, fb.VT_F1)
    pos = b4.leg_risk(raw, level, trailing_stop=fb.TRAILING_STOP_ON["crack_321"]).fillna(0.0)
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    ret = (pos.shift(1).fillna(0.0) * level.diff() / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    return pos, ret, turn


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    fac4, rets4, turn4 = b4.build_v4(levels, None)
    names = ["crack_321", "cross_sectional", "bzwti"]
    net_c = b4.apply_costs({k: fac4[k] for k in names}, {k: rets4[k] for k in names},
                           turnover={k: turn4[k] for k in names})
    book_c = b4.book_returns(net_c, names, b4.weight_scheme(net_c[names], "EQ"))

    lvl = levels["crack_321"]
    z = fb.seasonal_z(lvl)
    base_r = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base_r).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    rel = lvl - base_r
    r2 = pd.Series(np.select([rel < -band, rel > band], ["comp", "exp"], default="norm"),
                   index=full_idx)
    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)
    h1_gate = pd.Series(prod_z >= 1.0, index=full_idx)

    rows = []
    variants = {
        "V_Champ": (False, False),
        "V3_H1": (False, True),
        "V1_regime": (True, False),
        "V2_both": (True, True),
    }
    for vid, (use_regime, use_h1) in variants.items():
        if vid == "V_Champ":
            legs = {k: (fac4[k], rets4[k], turn4[k]) for k in names}
        else:
            p, r, t = crack_gated(lvl, z, r2, use_regime, h1_gate)
            legs = {"crack_321": (p, r, t),
                    "cross_sectional": (fac4["cross_sectional"], rets4["cross_sectional"], turn4["cross_sectional"]),
                    "bzwti": (fac4["bzwti"], rets4["bzwti"], turn4["bzwti"])}
        net = b4.apply_costs({k: v[0] for k, v in legs.items()},
                             {k: v[1] for k, v in legs.items()},
                             turnover={k: v[2] for k, v in legs.items()})
        book = b4.book_returns(net, list(legs), b4.weight_scheme(net[list(legs)], "EQ"))
        book_ov = b4.apply_overlay(book)
        for wname, lo, hi in (("OOS", OOS_FULL[0], OOS_FULL[1]),
                              ("FULL", "2007-07-30", "2026-09-09")):
            for tag, ser in (("raw", book), ("ov", book_ov)):
                seg = ser.loc[lo:hi].iloc[WARMUP:] if len(ser.loc[lo:hi]) > WARMUP else ser.loc[lo:hi]
                st = block_stats(blocks_of(seg))
                log(f"  {vid:<9} {wname:<5} {tag} ann {st['ann']*100:+6.2f}% "
                    f"t={st['t']:+5.2f} CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]% "
                    f"neg {st['neg']*100:.0f}%")
                rows.append({"variant": vid, "window": wname, "series": tag, **st})
        so = b4.stats(book_ov.loc[OOS].iloc[WARMUP:])
        log(f"  {vid:<9} OOS ov Sharpe {so['sharpe']:.3f} DD {so['maxdd']*100:.2f}% "
            f"CAGR {so['cagr']*100:.2f}%")
        rows.append({"variant": vid, "oos_ov_sharpe": so["sharpe"], "oos_ov_dd": so["maxdd"]})

    with open(ROOT / "results" / "final_strategy.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    log("\nSaved results/final_strategy.csv")


if __name__ == "__main__":
    main()
