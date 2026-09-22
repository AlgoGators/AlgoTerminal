"""Next batch: ES risk layer + retained-channel tests.

Preregistered in research/proceed2_next.md (8e6078d).
P1 B1h + ES gear (no ladder); P3 cold severity 5/10d; P4 gas-HO
relative; P2 utilization-surprise tilt.
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

BLOCK = 20
WARMUP = 90
BUDGET = 0.10
ES5_CRUSH = 0.274
# NOTE (artifact audit 2026-09-22): this window is NOT out-of-sample.
# It fully contains the training window, so any number reported under the
# "OOS" label from this harness is in-sample. See findings/artifact_audit.md.
OOS_LO, OOS_HI = "2007-07-30", "2023-09-08"
if OOS_LO <= "2018-12-31":
    print("WARNING: the window labelled OOS (2007-07-30..2023-09-08) fully "
          "contains the 2007-2018 training window; OOS numbers from this "
          "harness are IN-SAMPLE. See findings/artifact_audit.md.")
FULL_LO, FULL_HI = "2007-07-30", "2026-09-09"
NC = 20
NC_SEED = 23


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
        mean = (sub.cumsum() / sub.notna().cumsum()).shift(1)
        mean[sub.notna().cumsum().shift(1) < min_obs] = np.nan
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


def state_machine(z, regime_ok, enter=-0.75, exit_=-0.5):
    zz = z.to_numpy(dtype=float)
    vals = np.zeros(len(z), dtype=float)
    state = 0.0
    for i in range(len(z)):
        if np.isnan(zz[i]):
            vals[i] = 0.0
            continue
        if state == 1.0 and not regime_ok[i]:
            state = 0.0
        if state == 0.0 and zz[i] <= enter and regime_ok[i]:
            state = 1.0
        elif state == 1.0 and zz[i] >= exit_:
            state = 0.0
        vals[i] = state
    return pd.Series(vals, index=z.index)


def make_leg(level, z, sig, vt, trailing, mult=None):
    raw = sig * b4.fixed_vol_scale(level, vt)
    if mult is not None:
        raw = raw * mult.reindex(level.index).fillna(1.0).shift(1).fillna(1.0)
    pos = b4.leg_risk(raw, level, trailing_stop=trailing).fillna(0.0)
    base = b4.base_of(level).shift(1).replace(0.0, np.nan)
    ret = (pos.shift(1).fillna(0.0) * level.diff() / base).fillna(0.0)
    turn = pos.diff().abs().fillna(0.0)
    return pos, ret, turn


def net_book(parts, names):
    net = b4.apply_costs({k: v[0] for k, v in parts.items()},
                         {k: v[1] for k, v in parts.items()},
                         turnover={k: v[2] for k, v in parts.items()})
    w = b4.weight_scheme(net[names], "EQ")
    return b4.book_returns(net, names, w)


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
    return {"n": n, "ann": m * 252 / BLOCK, "t": m / se if se else np.nan,
            "lo90": m - 1.645 * se, "hi90": m + 1.645 * se, "neg": float((blocks < 0).mean()),
            "worst": float(blocks.min())}


def report(tag, ser, rows):
    for wname, lo, hi in (("OOS", OOS_LO, OOS_HI), ("FULL", FULL_LO, FULL_HI)):
        seg = ser.loc[lo:hi].iloc[WARMUP:] if len(ser.loc[lo:hi]) > WARMUP else ser.loc[lo:hi]
        st = block_stats(blocks_of(seg))
        log(f"  {tag:<20} {wname:<5} ann {st['ann']*100:+6.2f}% t={st['t']:+5.2f} "
            f"CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]% neg {st['neg']*100:.0f}% "
            f"worst {st['worst']*100:+.1f}%")
    so = b4.stats(ser.loc[OOS_LO:OOS_HI].iloc[WARMUP:])
    log(f"  {tag:<20} OOS raw Sh {so['sharpe']:.3f} DD {so['maxdd']*100:.2f}% CAGR {so['cagr']*100:.2f}%")
    rows.append({"variant": tag, "oos_sharpe": so["sharpe"], "oos_dd": so["maxdd"]})


def bucket(feat, fwd, mask=None, n_q=5):
    idx = fwd.index.intersection(feat.dropna().index)
    if mask is not None:
        idx = idx.intersection(mask[mask].index)
    if len(idx) < 60:
        return None
    f, r = feat.loc[idx], fwd.loc[idx]
    try:
        q = pd.qcut(f, n_q, labels=False, duplicates="drop")
    except ValueError:
        return None
    out = []
    for b in sorted(set(q.dropna())):
        sel = q == b
        out.append((b, int(sel.sum()), r[sel].mean()))
    return out


def print_b(rows, tag):
    if not rows:
        log(f"  {tag}: insufficient")
        return np.nan
    log(f"  {tag}: " + "  ".join(f"b{b}:{m*100:+.1f}%({n})" for b, n, m in rows))
    return rows[-1][2] - rows[0][2] if len(rows) >= 2 else np.nan


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    lvl = levels["crack_321"]
    rows = []

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
    util = read_csv(EIA / "raw_WPULEUS3.csv")
    util_z = daily_state(sm_z(util.diff()), full_idx)

    z1 = fb.seasonal_z(lvl)
    sig1 = state_machine(z1, regime_ok)
    h1_m = (1 - h1_gate.shift(1).fillna(0.0))
    f1 = make_leg(lvl, z1, sig1, fb.VT_F1, fb.TRAILING_STOP_ON["crack_321"], mult=h1_m)
    book_b1h_raw = net_book({"F1": f1}, ["F1"])

    log("=== P1 ES-derived gear (BUDGET=10%, ES5=27.4%) ===")
    gear = BUDGET / ES5_CRUSH
    log(f"  gear = {gear:.3f}")
    book_b1h_gear = book_b1h_raw * gear
    report("B1h raw", book_b1h_raw, rows)
    report("B1h + ES gear", book_b1h_gear, rows)

    # champion overlay comparison
    fac4, rets4, turn4 = b4.build_v4(levels, None)
    names = ["crack_321", "cross_sectional", "bzwti"]
    netc = b4.apply_costs({k: fac4[k] for k in names}, {k: rets4[k] for k in names},
                          turnover={k: turn4[k] for k in names})
    bookc = b4.book_returns(netc, names, b4.weight_scheme(netc[names], "EQ"))
    report("Champ overlay", b4.apply_overlay(bookc), rows)

    log("\n=== P3 cold severity power at 5/10d ===")
    t2m = read_csv(WEA / "raw_T2M_NYC.csv").reindex(full_idx)
    hdd_z = sm_z(pd.Series(np.maximum(0.0, 18.0 - t2m), index=full_idx))
    winter = pd.Series([m in (11, 12, 1, 2, 3) for m in full_idx.month], index=full_idx)
    lg = levels["crack_gas"]
    baseg = b4.base_of(lg).shift(1).replace(0.0, np.nan)
    for h in (5, 10):
        fwdg = ((lg.shift(-h) - lg) / baseg).rename(f"fwd{h}")
        # non-overlap sampling by step h
        sampled = full_idx[::h]
        f = fwdg.reindex(sampled)
        feat = hdd_z.reindex(sampled)
        msk = winter.reindex(sampled)
        d = print_b(bucket(feat, f, mask=msk), f"HDD z winter > fwd{h} gas")
        rows.append({"variant": f"cold_fwd{h}", "delta": d})
    # control on fwd5
    h = 5
    fwdg5 = ((lg.shift(-h) - lg) / baseg)
    sampled = full_idx[::h]
    f5 = fwdg5.reindex(sampled)
    feat = hdd_z.reindex(sampled)
    msk = winter.reindex(sampled)
    real_d = print_b(bucket(feat, f5, mask=msk), "HDD z winter > fwd5 gas (real)")
    nc = []
    for i in range(NC):
        rng = np.random.default_rng(NC_SEED + i)
        lab = rng.random(len(sampled)) < 0.2
        sel = msk & f5.notna()
        nc.append(f5[sel & pd.Series(lab, index=sampled)].mean())
    log(f"  control fwd5: real-delta {real_d} vs random-slice {np.mean(nc):.4f} sd {np.std(nc):.4f}")
    rows.append({"variant": "cold_fwd5_control", "shuf_mean": float(np.mean(nc)), "real_delta": real_d})

    log("\n=== P4 gas-HO relative ===")
    lho = levels["crack_ho"]
    baseho = b4.base_of(lho).shift(1).replace(0.0, np.nan)
    rel_level = lho - lg
    rel_z = fb.seasonal_z(rel_level)
    fwd_rel20 = ((rel_level.shift(-20) - rel_level) / (baseho + baseg)).fillna(0.0)
    for season, msk in (("winter", winter), ("summer", ~winter)):
        d = print_b(bucket(rel_z, fwd_rel20, mask=msk), f"rel z {season} > fwd20 gas-HO relative")
        rows.append({"variant": f"rel_{season}", "delta": d})

    log("\n=== P2 utilization-surprise tilt on B1h ===")
    util_down = pd.Series(util_z <= -1.0, index=full_idx)
    tilt = pd.Series(np.where(util_down.to_numpy(), 1.25, 1.0), index=full_idx)
    f1t = make_leg(lvl, z1, sig1, fb.VT_F1, fb.TRAILING_STOP_ON["crack_321"],
                   mult=h1_m * tilt)
    book_t = net_book({"F1": f1t}, ["F1"])
    report("B1h + util tilt", book_t, rows)

    with open(ROOT / "results" / "next_direction.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    log("\nSaved results/next_direction.csv")


if __name__ == "__main__":
    main()
