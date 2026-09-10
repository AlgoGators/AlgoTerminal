"""Modeled crash-put overlay cost study (stylized, illustrative).

Question: could a crash-put overlay capture the windfall AND cap the
drawdown (the Round 4 structural gap)? Real historical option prices are
not available from any free source, so this prices the hedge with a
Black-76-style put on the book's monthly return and tests cost sensitivity
under conservative assumptions.

Model (clearly stylized; NOT tradeable as-is):
- Underlying: the CORE3 EQ raw book (monthly return).
- Each month start: buy a 1-month put struck at X (monthly return floor).
  Premium = Black-76 put price with S=1, K=e^X, T=21/252, r=0,
  sigma = trailing 60d realized annualized vol of the book (causal).
  Markup m scales traded IV vs realized (1.0/1.25/1.5).
- Hedge notional h: 1.0 or 0.5 of the book.
- Payoff at expiry: h * max(0, X - R_month). Overlay monthly return =
  R_month + payoff - h * premium.
- Compare raw vs overlaid monthly equity: CAGR, ann Sharpe, MaxDD, and
  premium cost (%/yr of notional).

Honest limits: a put on "the book" is not tradeable (real hedges are on
futures legs with basis risk); premium uses realized vol, not traded IV
(markup models the difference); monthly cadence is stylized; no
interaction with the DD overlay (this is RAW book + put).

Decision (logged): run this stylized screen first; pursue per-leg
modeling only if the economics are promising.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = Path("/tmp/panel_adj_2007_2026.parquet")
IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90

spec = importlib.util.spec_from_file_location("b4", str(DEV / "book_oos_v4.py"))
b4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b4)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)


def bs_put(x: float, sigma_ann: float, t: float = 21 / 252, r: float = 0.0) -> float:
    """Black-76-style put on the simple return: S=1, K=e^x, T=t."""
    sigma = max(sigma_ann * np.sqrt(t), 1e-6)
    k = np.exp(x)
    d1 = (np.log(1.0 / k) + 0.5 * sigma**2) / sigma
    d2 = d1 - sigma
    return k * np.exp(-r * t) * norm.cdf(-d2) - norm.cdf(-d1)


def monthly_stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "worst": np.nan}
    eq = (1 + r).cumprod()
    years = len(r) / 12
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1,
            "sharpe": r.mean() / r.std() * np.sqrt(12),
            "maxdd": (eq / eq.cummax() - 1).min(),
            "worst": r.min()}


def main():
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    factors, rets, turn = b4.build_v4(levels, None)
    net = b4.apply_costs(factors, rets, turnover=turn)
    isw = b4.window(net, IS_START, df.index.max())
    w = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], "EQ")
    book = b4.book_returns(net, b4.SUBSETS["CORE3"], w)

    months = book.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    mvol = book.rolling(60, min_periods=30).std().shift(1).resample("ME").last() * np.sqrt(252)

    raw = monthly_stats(months)
    print("=== RAW CORE3 EQ (monthly view) ===")
    print("  CAGR %7.2f%%  Sharpe %5.2f  MaxDD %7.2f%%  worstMonth %6.2f%%" % (
        raw["cagr"] * 100, raw["sharpe"], raw["maxdd"] * 100, raw["worst"] * 100))

    print("\n=== crash-put overlay (monthly, stylized) ===")
    print("  strike  h  markup | CAGR    Sharpe  MaxDD   worstM  premium(%/yr)")
    sig = mvol.reindex(months.index).ffill()
    for x in [-0.05, -0.075, -0.10, -0.15]:
        for h in [1.0, 0.5]:
            for m in [1.0, 1.25, 1.5]:
                prem = []
                pay = []
                for t in range(len(months)):
                    s = sig.iloc[t]
                    if pd.isna(s) or s <= 0:
                        prem.append(0.0)
                        pay.append(0.0)
                        continue
                    p = h * bs_put(x, s * m)
                    r = months.iloc[t]
                    prem.append(p)
                    pay.append(h * max(0.0, x - r))
                prem = pd.Series(prem, index=months.index)
                pay = pd.Series(pay, index=months.index)
                ov = months + pay - prem
                s = monthly_stats(ov)
                print("  %6.3f  %.1f  %5.2f | %7.2f%%  %5.2f  %7.2f%%  %7.2f%%  %8.2f%%" % (
                    x, h, m, s["cagr"] * 100, s["sharpe"], s["maxdd"] * 100,
                    s["worst"] * 100, prem.mean() * 12 * 100))

    print("\n=== worst 8 raw months ===")
    for idx, v in months.nsmallest(8).items():
        print("  %s  %+7.2f%%" % (idx.strftime("%Y-%m"), v * 100))

    oos = b4.window(net, OOS_START, IS_START)
    ob = b4.apply_overlay(book.loc[oos.index])
    ood = b4.stats(ob)
    print("\n=== reference: DD overlay (daily view, OOS) ===")
    print("  CAGR %7.2f%%  Sharpe %5.2f  MaxDD %7.2f%%  vol %5.1f%%" % (
        ood["cagr"] * 100, ood["sharpe"], ood["maxdd"] * 100, ood["vol"] * 100))


if __name__ == "__main__":
    main()