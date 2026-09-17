"""Try out the vol-targeted reporting standard on all strategy variants.

Every variant (unit/kelly/anchor/kelly_half, walk-forward 2012-2026,
tail-stop + cooldown 3) is scaled to 10% annualized volatility, then a
comparable metric set is computed. Prediction: shape metrics (Sharpe,
Sortino, DSR, block t, PF, win rate) are identical across variants —
the mode is a dial; only level metrics (CAGR, MaxDD) differ and they
collapse after vol-targeting.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path("/home/sebas/algoterminal-strategy-v2")
GAMMA = 0.5772


def deflated_sharpe(sr, rets, T, N):
    sk = rets.skew()
    ku = rets.kurt()
    V = (1 - sk * sr + (ku - 1) / 4 * sr ** 2) / (T - 1)
    if V <= 0 or not np.isfinite(V):
        return np.nan
    sr0 = np.sqrt(V) * ((1 - GAMMA) * sps.norm.ppf(1 - 1 / N)
                        + GAMMA * sps.norm.ppf(1 - 1 / (N * np.e)))
    denom = np.sqrt(max(1 - sk * sr + (ku - 1) / 4 * sr ** 2, 1e-12))
    return float(sps.norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom))


def block_metrics(r):
    n = len(r)
    pos = np.arange(n)
    sums = np.array([r[pos // 20 == b].sum() for b in range(pos.max() // 20 + 1)
                     if (pos // 20 == b).sum() == 20])
    if len(sums) < 5:
        return np.nan, np.nan
    return (float(sums.mean() / (sums.std(ddof=1) / np.sqrt(len(sums)))),
            float((sums < 0).mean()))


def trades_of(r, pos):
    in_t = np.abs(pos) > 0
    n = len(r)
    runs = []
    i = 0
    while i < n:
        if in_t[i]:
            j = i
            while j < n and in_t[j]:
                j += 1
            runs.append(r[i:j].sum())
            i = j
        else:
            i += 1
    wins = [v for v in runs if v > 0]
    losses = [v for v in runs if v <= 0]
    return runs, wins, losses


def full_metrics(ret, pos, vol_target=0.10):
    r = np.asarray(ret, dtype=float)
    n = len(r)
    vol = r.std(ddof=1) * np.sqrt(252)
    scale = vol_target / vol if vol > 0 else 1.0
    rs = r * scale
    m = rs.mean()
    sd = rs.std(ddof=1)
    sr = m / sd * np.sqrt(252)
    eq = (1 + rs).cumprod()
    cagr = float(((1 + rs).prod()) ** (252 / n) - 1)
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    ann = float(m * 252)
    calmar = cagr / abs(dd) if dd else np.nan
    negd = rs[rs < 0]
    sortino = m * 252 / (negd.std(ddof=1) * np.sqrt(252)) if len(negd) > 1 and negd.std() else np.nan
    t_block, neg_blk = block_metrics(rs)
    dsr = deflated_sharpe(m / sd, pd.Series(rs), n, 1000)
    runs, wins, losses = trades_of(rs, np.asarray(pos))
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else np.nan
    return dict(scale=scale, ann=ann, cagr=cagr, dd=dd, sh=sr, sortino=sortino,
                calmar=calmar, t=t_block, dsr=dsr, trades=len(runs),
                win=len(wins) / len(runs) if runs else np.nan,
                avgw=np.mean(wins) if wins else np.nan,
                avgl=np.mean(losses) if losses else np.nan,
                pf=pf, worst=float(rs.min()), expo=float((np.abs(pos) > 0).mean()))


def main() -> None:
    rows = []
    for mode in ("unit", "kelly", "anchor", "kelly_half"):
        df = pd.read_csv(ROOT / "results" / f"branch_{mode}_cool3_series.csv", parse_dates=["date"])
        m = full_metrics(df.ret.to_numpy(), df.pos.to_numpy())
        m["mode"] = mode
        rows.append(m)
    out = pd.DataFrame(rows)
    print("=== All variants scaled to 10% annualized vol (walk-forward 2012-2026) ===")
    cols = ["mode", "scale", "ann", "cagr", "dd", "sh", "sortino", "calmar",
            "t", "dsr", "trades", "win", "avgw", "avgl", "pf", "worst", "expo"]
    print(out[cols].round(3).to_string(index=False))
    out.to_csv(ROOT / "results" / "final_metrics_10vol.csv", index=False)
    print("\nSaved results/final_metrics_10vol.csv")

    # canonical series: unit at 10% vol, full sample + clean slice + yearly
    df = pd.read_csv(ROOT / "results" / "branch_unit_cool3_series.csv", parse_dates=["date"])
    vol = df.ret.std(ddof=1) * np.sqrt(252)
    scale = 0.10 / vol
    rs = df.ret.to_numpy() * scale
    eq = (1 + rs).cumprod()
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    cagr = float(((1 + rs).prod()) ** (252 / len(rs)) - 1)
    sr = rs.mean() / rs.std(ddof=1) * np.sqrt(252)
    years = pd.Series(rs, index=pd.DatetimeIndex(df.date)).groupby(
        lambda ts: ts.year).sum()
    print("\n=== Canonical: unit-risk, tail-stop + cool3, walk-forward, at 10% vol ===")
    print(f"period {df.date.min().date()} .. {df.date.max().date()}, vol target 10% (factor {scale:.3f})")
    print(f"CAGR {cagr*100:+.2f}% | MaxDD {dd*100:.2f}% | Sharpe {sr:.3f} | Calmar {cagr/abs(dd):.2f}")
    print("\nper-year returns at 10% vol:")
    for y, v in years.items():
        print(f"  {y}: {v*100:+.2f}%")
    s19 = rs[df.date >= "2019-01-01"]
    eq19 = (1 + s19).cumprod()
    dd19 = float((eq19 / np.maximum.accumulate(eq19) - 1).min())
    sr19 = s19.mean() / s19.std(ddof=1) * np.sqrt(252)
    print(f"\n2019+ clean slice: CAGR {((1+s19).prod()**(252/len(s19))-1)*100:+.2f}% "
          f"MaxDD {dd19*100:.2f}% Sharpe {sr19:.3f}")
    pd.DataFrame({"date": df.date, "ret": rs, "pos": df.pos}).to_csv(
        ROOT / "results" / "strategy_10vol_series.csv", index=False)
    print("Saved results/strategy_10vol_series.csv")


if __name__ == "__main__":
    main()
