"""Model book harness: from-scratch strategy from mechanism findings.

Preregistered in research/model_book.md (e1d19cd). No V2 overlay.
Per-factor clean blocks; books B1/B2/B3; keep factors whose OOS CI
excludes zero.
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
# NOTE (artifact audit 2026-09-22): this window is NOT out-of-sample.
# It fully contains the training window, so any number reported under the
# "OOS" label from this harness is in-sample. See findings/artifact_audit.md.
OOS_LO, OOS_HI = "2007-07-30", "2023-09-08"
if OOS_LO <= "2018-12-31":
    print("WARNING: the window labelled OOS (2007-07-30..2023-09-08) fully "
          "contains the 2007-2018 training window; OOS numbers from this "
          "harness are IN-SAMPLE. See findings/artifact_audit.md.")
FULL_LO, FULL_HI = "2007-07-30", "2026-09-09"


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
            "lo90": m - 1.645 * se, "hi90": m + 1.645 * se, "neg": float((blocks < 0).mean()),
            "worst": float(blocks.min())}


def make_leg(level, z, sig, vt, trailing, cap_total=None, mult=None):
    """sig in {-1,0,1}; optional multiplier; optional total cap shared via scale."""
    raw = sig * b4.fixed_vol_scale(level, vt)
    if mult is not None:
        raw = raw * mult.reindex(level.index).fillna(1.0).shift(1).fillna(1.0)
    pos = b4.leg_risk(raw, level, trailing_stop=trailing).fillna(0.0)
    if cap_total is not None:
        tot = pos.abs() + 1e-12
        pos = pos * (cap_total / tot).clip(upper=1.0).fillna(1.0)
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    ret = (pos.shift(1).fillna(0.0) * level.diff() / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    return pos, ret, turn


def state_machine(z, regime_ok=None, enter=-0.75, exit_=-0.5):
    zz = z.to_numpy(dtype=float)
    vals = np.zeros(len(z), dtype=float)
    state = 0.0
    for i in range(len(z)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if state == 1.0 and regime_ok is not None and not regime_ok[i]:
            state = 0.0
        if state == 0.0 and zz[i] <= enter and (regime_ok[i] if regime_ok is not None else True):
            state = 1.0
        elif state == 1.0 and zz[i] >= exit_:
            state = 0.0
        vals[i] = state
    return pd.Series(vals, index=z.index)


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    fac4, rets4, turn4 = b4.build_v4(levels, None)

    lvl = levels["crack_321"]
    base_r = lvl.rolling(504, min_periods=200).median()
    mad = (lvl - base_r).abs().rolling(504, min_periods=200).median()
    band = 1.4826 * mad
    rel = lvl - base_r
    r2 = pd.Series(np.select([rel < -band, rel > band], ["comp", "exp"], default="norm"),
                   index=full_idx)
    regime_ok = r2.isin(["comp", "norm"]).to_numpy(dtype=bool)
    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod_z = daily_state(sm_z((gas + dist).diff()), full_idx)
    h1_gate = pd.Series(prod_z >= 1.0, index=full_idx)

    # F1 regime-gated crush on crack_321
    z1 = fb.seasonal_z(lvl)
    sig1 = state_machine(z1, regime_ok=regime_ok)
    f1 = make_leg(lvl, z1, sig1, fb.VT_F1, fb.TRAILING_STOP_ON["crack_321"])

    # F2 multi-leg breadth on product legs (cap total 0.8)
    legs2 = ("crack_gas", "crack_ho")
    parts2 = {}
    for k in legs2:
        lk = levels[k]
        zk = fb.seasonal_z(lk)
        sigk = state_machine(zk)
        p, r, t = make_leg(lk, zk, sigk, fb.VT_F1, fb.TRAILING_STOP_ON["crack_321"])
        parts2[k] = (p, r, t)
    tot2 = pd.concat([parts2[k][0] for k in legs2], axis=1).abs().sum(axis=1)
    cap2 = (0.8 / tot2.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    f2 = {}
    agg_p2 = pd.Series(0.0, index=full_idx)
    agg_r2 = pd.Series(0.0, index=full_idx)
    agg_t2 = pd.Series(0.0, index=full_idx)
    for k in legs2:
        lk = levels[k]
        p = (parts2[k][0] * cap2).fillna(0.0)
        base = b4.base_of(lk).shift(1).replace(0.0, np.nan)
        r = (p.shift(1).fillna(0.0) * lk.diff() / base).fillna(0.0)
        t = p.diff().abs().fillna(0.0)
        agg_p2 += p
        agg_r2 += r
        agg_t2 += t
        f2[k] = (p, r, t)
    f2_agg = (agg_p2, agg_r2, agg_t2)

    # F3 bzwti (champion leg)
    f3 = (fac4["bzwti"], rets4["bzwti"], turn4["bzwti"])

    # F4 variant: H1 de-risk multiplier inside F1 (and F2)
    h1_m = (1 - h1_gate.shift(1).fillna(0.0))

    def book(parts, names):
        net = b4.apply_costs({k: v[0] for k, v in parts.items()},
                             {k: v[1] for k, v in parts.items()},
                             turnover={k: v[2] for k, v in parts.items()})
        w = b4.weight_scheme(net[names], "EQ")
        return b4.book_returns(net, names, w)

    def report(tag, ser):
        for wname, lo, hi in (("OOS", OOS_LO, OOS_HI), ("FULL", FULL_LO, FULL_HI)):
            seg = ser.loc[lo:hi].iloc[WARMUP:] if len(ser.loc[lo:hi]) > WARMUP else ser.loc[lo:hi]
            st = block_stats(blocks_of(seg))
            log(f"  {tag:<14} {wname:<5} ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f} "
                f"CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]% neg {st['neg']*100:.0f}% "
                f"worst {st['worst']*100:+.1f}%")
        so = b4.stats(ser.loc[OOS_LO:OOS_HI].iloc[WARMUP:])
        log(f"  {tag:<14} OOS raw Sharpe {so['sharpe']:.3f} DD {so['maxdd']*100:.2f}% "
            f"CAGR {so['cagr']*100:.2f}%")

    rows = []
    log("=== Per-factor clean blocks ===")
    for tname, ser in (("F1 regime-crush", book({"F1": f1}, ["F1"])),
                       ("F2 multi-breadth", book({"F2": f2_agg}, ["F2"])),
                       ("F3 bzwti", book({"F3": f3}, ["F3"]))):
        report(tname, ser)

    log("\n=== Books (no overlay) ===")
    b1 = book({"F1": f1, "F3": f3}, ["F1", "F3"])
    b2 = book({"F1": f1, "F2": f2_agg, "F3": f3}, ["F1", "F2", "F3"])
    # B3 = B2 with H1 de-risk applied inside F1 and F2
    p1h, r1h, t1h = make_leg(lvl, z1, sig1, fb.VT_F1, fb.TRAILING_STOP_ON["crack_321"], mult=h1_m)
    f1h = (p1h, r1h, t1h)
    p2h = (agg_p2 * h1_m.reindex(full_idx)).fillna(0.0)
    b2h = pd.Series(0.0, index=full_idx)
    lk321 = lvl
    base321 = b4.base_of(lk321).shift(1).replace(0.0, np.nan)
    r2h = (p2h.shift(1).fillna(0.0) * lk321.diff() / base321).fillna(0.0) if False else pd.Series(0.0, index=full_idx)
    # recompute F2 rets with the H1 multiplier properly per leg
    parts2h = {}
    for k in legs2:
        lk = levels[k]
        zk = fb.seasonal_z(lk)
        sigk = state_machine(zk)
        pk0, rk0, tk0 = make_leg(lk, zk, sigk, fb.VT_F1, fb.TRAILING_STOP_ON["crack_321"], mult=h1_m)
        parts2h[k] = (pk0, rk0, tk0)
    tot2h = pd.concat([parts2h[k][0] for k in legs2], axis=1).abs().sum(axis=1)
    cap2h = (0.8 / tot2h.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    agg_p2h = pd.Series(0.0, index=full_idx)
    agg_r2h = pd.Series(0.0, index=full_idx)
    agg_t2h = pd.Series(0.0, index=full_idx)
    for k in legs2:
        lk = levels[k]
        p = (parts2h[k][0] * cap2h).fillna(0.0)
        base = b4.base_of(lk).shift(1).replace(0.0, np.nan)
        r = (p.shift(1).fillna(0.0) * lk.diff() / base).fillna(0.0)
        t = p.diff().abs().fillna(0.0)
        agg_p2h += p
        agg_r2h += r
        agg_t2h += t
    f2h = (agg_p2h, agg_r2h, agg_t2h)
    b3 = book({"F1": f1h, "F2": f2h, "F3": f3}, ["F1", "F2", "F3"])
    b1h = book({"F1": f1h}, ["F1"])
    b1h3 = book({"F1": f1h, "F3": f3}, ["F1", "F3"])
    for tname, ser in (("B1", b1), ("B2", b2), ("B3(+H1)", b3),
                       ("B1h(F1+H1)", b1h), ("B1h3(F1+H1+F3)", b1h3)):
        report(tname, ser)

    # mixture context for B2 crush states (ES)
    # champion context
    report("Champ_raw", book({"crack_321": (fac4["crack_321"], rets4["crack_321"], turn4["crack_321"]),
                              "cross": (fac4["cross_sectional"], rets4["cross_sectional"], turn4["cross_sectional"]),
                              "bzwti": f3}, ["crack_321", "cross", "bzwti"]))

    with open(ROOT / "results" / "model_book.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "window", "ann", "t", "lo90", "hi90", "neg", "worst"])
        for tname, ser in (("F1", b1), ("F2", book({"F2": f2_agg}, ["F2"])),
                           ("F3", book({"F3": f3}, ["F3"])),
                           ("B1", b1), ("B2", b2), ("B3", b3),
                           ("B1h", b1h), ("B1h3", b1h3), ("Champ_raw", None)):
            if ser is None:
                continue
            for wname, lo, hi in (("OOS", OOS_LO, OOS_HI), ("FULL", FULL_LO, FULL_HI)):
                seg = ser.loc[lo:hi].iloc[WARMUP:] if len(ser.loc[lo:hi]) > WARMUP else ser.loc[lo:hi]
                st = block_stats(blocks_of(seg))
                w.writerow([tname, wname, st["ann"], st["t"], st["lo90"], st["hi90"], st["neg"], st["worst"]])
    log("\nSaved results/model_book.csv")


if __name__ == "__main__":
    main()
