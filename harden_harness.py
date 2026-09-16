"""Direction 1: harden the hold.

Preregistered in research/direction1_harden_hold.md (bf8ccb9).
Sections: 1a deflated Sharpe, 1b cost robustness, 1c overlay cost
ledger, 1d settlement cross-check (RCLC1 Cushing WTI weekly vs
yfinance CL).
"""
from __future__ import annotations

import importlib.util
import csv
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).parent
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
GAMMA = 0.5772


def log(msg: str) -> None:
    print(msg, flush=True)


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
    if len(blocks) < 3:
        return None
    n = len(blocks)
    m = blocks.mean()
    sd = blocks.std(ddof=1)
    se = sd / np.sqrt(n)
    return {"n": n, "mean20": m, "ann": m * 252 / BLOCK, "t": m / se if se else np.nan,
            "lo90": m - 1.645 * se, "hi90": m + 1.645 * se}


def deflated_sharpe(sr: float, rets: pd.Series, T: int, N: int) -> float:
    sk = rets.skew()
    ku = rets.kurt()
    V = (1 - sk * sr + (ku - 1) / 4 * sr ** 2) / (T - 1)
    if V <= 0:
        return np.nan
    sr0 = np.sqrt(V) * ((1 - GAMMA) * sps.norm.ppf(1 - 1 / N)
                        + GAMMA * sps.norm.ppf(1 - 1 / (N * np.e)))
    denom = np.sqrt(max(1 - sk * sr + (ku - 1) / 4 * sr ** 2, 1e-12))
    return float(sps.norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom))


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    fac4, rets4, turn4 = b4.build_v4(levels, None)
    names = ["crack_321", "cross_sectional", "bzwti"]
    oos_slice = slice("2007-07-30", "2023-09-08")

    rows = []
    log("=== 1b cost robustness (OOS and FULL, non-overlap blocks) ===")
    for trade_bps, roll_bps in ((5, 20), (10, 20), (20, 40), (10, 40)):
        net = b4.apply_costs({k: fac4[k] for k in names},
                             {k: rets4[k] for k in names},
                             turnover={k: turn4[k] for k in names},
                             trade_bps=trade_bps, roll_bps=roll_bps)
        book = b4.book_returns(net, names, b4.weight_scheme(net[names], "EQ"))
        for wname, sl in (("OOS", oos_slice), ("FULL", slice(None))):
            seg = book.loc[sl].iloc[WARMUP:] if len(book.loc[sl]) > WARMUP else book.loc[sl]
            st = block_stats(blocks_of(seg))
            if st:
                log(f"  cost {trade_bps}/{roll_bps} {wname:<5} ann {st['ann']*100:+6.2f}% "
                    f"t={st['t']:+5.2f} CI [{st['lo90']*100:+6.2f},{st['hi90']*100:+6.2f}]%")
                rows.append({"item": "cost", "cost": f"{trade_bps}/{roll_bps}",
                             "window": wname, **st})

    log("\n=== 1c overlay cost ledger (OOS blocks) ===")
    net = b4.apply_costs({k: fac4[k] for k in names}, {k: rets4[k] for k in names},
                         turnover={k: turn4[k] for k in names})
    book = b4.book_returns(net, names, b4.weight_scheme(net[names], "EQ"))
    book_ov = b4.apply_overlay(book)
    raw = book.loc[oos_slice].iloc[WARMUP:]
    ov = book_ov.loc[oos_slice].iloc[WARMUP:]
    br, bo = blocks_of(raw), blocks_of(ov)
    both = pd.concat([br, bo], axis=1, join="inner")
    both.columns = ["raw", "ov"]
    forgone = float(both.loc[both["raw"] > 0, "raw"].sum() - both.loc[both["raw"] > 0, "ov"].sum())
    top10 = both.nlargest(10, "raw")
    captured = int((top10["ov"] > 0).sum())
    sat_out = int((top10["ov"] == 0).sum())
    flat = both.loc["2014-01-01":"2016-12-31"]
    log(f"  total raw {both['raw'].sum()*100:+.2f}% vs ov {both['ov'].sum()*100:+.2f}%")
    log(f"  forgone on positive raw blocks {forgone*100:+.2f}%")
    log(f"  top-10 raw blocks: captured {captured}, sat flat {sat_out}, "
        f"raw sum {top10['raw'].sum()*100:+.2f}%, ov sum {top10['ov'].sum()*100:+.2f}%")
    if len(flat):
        log(f"  2014-2016: raw {flat['raw'].sum()*100:+.2f}% vs ov {flat['ov'].sum()*100:+.2f}%")
    rows.append({"item": "overlay_ledger", "forgone_pos": forgone,
                 "top10_captured": captured, "top10_satflat": sat_out,
                 "top10_raw": float(top10["raw"].sum()), "top10_ov": float(top10["ov"].sum())})

    log("\n=== 1a deflated Sharpe (OOS daily) ===")
    raw_oos = book.loc[oos_slice].iloc[WARMUP:]
    ov_oos = book_ov.loc[oos_slice].iloc[WARMUP:]
    for tag, rets in (("raw", raw_oos), ("ov", ov_oos)):
        sr = rets.mean() / rets.std() * np.sqrt(252) if rets.std() else 0.0
        T = len(rets)
        dsr = {f"N{n}": deflated_sharpe(sr, rets, T, n) for n in (10, 100, 1000)}
        log(f"  {tag} OOS SR {sr:.3f} T={T} skew {rets.skew():+.2f} kurt {rets.kurt():.2f} "
            f"DSR { {k: round(v,3) for k,v in dsr.items()} }")
        rows.append({"item": "dsr", "series": tag, "sr": sr, **{k: v for k, v in dsr.items()}})

    log("\n=== 1d settlement cross-check (RCLC1 Cushing WTI weekly vs CL) ===")
    setl = pd.read_csv(EIA / "raw_pri_fut_RCLC1.csv", index_col=0, parse_dates=True)["close"].astype(float)
    cl = df["CL"].astype(float)
    merged = pd.DataFrame({"setl": setl, "cl": cl}).dropna()
    merged["next"] = merged["setl"].shift(-1)
    week = merged.resample("W-FRI").last().dropna()
    corr = week["setl"].corr(week["cl"])
    rets_c = week["setl"].pct_change().corr(week["cl"].pct_change())
    rel = ((week["setl"] - week["cl"]).abs() / week["cl"]).mean()
    log(f"  rows {len(week)} {week.index.min().date()}..{week.index.max().date()} "
        f"corr level {corr:.4f} corr wk-ret {rets_c:.4f} mean abs rel diff {rel*100:.2f}%")
    rows.append({"item": "settlement", "n": len(week), "corr_level": corr,
                 "corr_wkret": rets_c, "mean_abs_rel": rel})

    with open(ROOT / "results" / "direction1.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    log("\nSaved results/direction1.csv")


if __name__ == "__main__":
    main()
