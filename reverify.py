"""Re-verify champion + options study + weather gate on the restored panel."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = (Path("/tmp/panel_adj_2007_2026.parquet")
         if Path("/tmp/panel_adj_2007_2026.parquet").exists()
         else Path(__file__).resolve().parent / "panel_v2.parquet")
IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90

spec = importlib.util.spec_from_file_location("b4", str(DEV / "book_oos_v4.py"))
b4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b4)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)


def bs_put(x, sigma_ann, t=21 / 252, r=0.0):
    sigma = max(sigma_ann * np.sqrt(t), 1e-6)
    k = np.exp(x)
    d1 = (np.log(1.0 / k) + 0.5 * sigma**2) / sigma
    d2 = d1 - sigma
    return k * np.exp(-r * t) * norm.cdf(-d2) - norm.cdf(-d1)


def monthly_stats(r):
    r = r.dropna()
    if len(r) == 0 or r.std() == 0:
        return {}
    eq = (1 + r).cumprod()
    years = len(r) / 12
    return {"cagr": eq.iloc[-1] ** (1 / years) - 1, "sharpe": r.mean() / r.std() * np.sqrt(12),
            "maxdd": (eq / eq.cummax() - 1).min(), "worst": r.min()}


df = pd.read_parquet(PANEL).sort_index()
levels = fb.build_levels(df)
factors, rets, turn = b4.build_v4(levels, None)
net = b4.apply_costs(factors, rets, turnover=turn)
isw = b4.window(net, IS_START, df.index.max())
oos = b4.window(net, OOS_START, IS_START)
w = b4.weight_scheme(isw[b4.SUBSETS["CORE3"]], "EQ")
book = b4.book_returns(net, b4.SUBSETS["CORE3"], w)
b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
ob_is, ob_oos = b4.apply_overlay(b_is), b4.apply_overlay(b_oos)

print("=== CHAMPION (restored panel) ===")
for label, s in [("IS raw", b_is), ("IS overlay", ob_is), ("OOS raw", b_oos), ("OOS overlay", ob_oos)]:
    st = b4.stats(s)
    print("  %-12s CAGR %7.2f%% Sh %5.2f DD %7.2f%% vol %5.1f%% worst %6.2f%%" % (
        label, st["cagr"] * 100, st["sharpe"], st["maxdd"] * 100, st["vol"] * 100, st["worst_day"] * 100))

print("\n=== OPTIONS STUDY (restored panel, key cells) ===")
months = book.resample("ME").apply(lambda x: (1 + x).prod() - 1)
mvol = book.rolling(60, min_periods=30).std().shift(1).resample("ME").last() * np.sqrt(252)
sig = mvol.reindex(months.index).ffill()
print("  strike  h  markup | CAGR    Sharpe  MaxDD   premium(%/yr)")
for x, h, m in [(-0.05, 1.0, 1.0), (-0.05, 1.0, 1.25), (-0.075, 1.0, 1.0), (-0.10, 0.5, 1.0), (-0.15, 1.0, 1.25)]:
    prem, pay = [], []
    for t in range(len(months)):
        s = sig.iloc[t]
        if pd.isna(s) or s <= 0:
            prem.append(0.0); pay.append(0.0); continue
        prem.append(h * bs_put(x, s * m))
        pay.append(h * max(0.0, x - months.iloc[t]))
    prem = pd.Series(prem, index=months.index)
    pay = pd.Series(pay, index=months.index)
    ov = months + pay - prem
    s = monthly_stats(ov)
    print("  %6.3f  %.1f  %5.2f | %7.2f%%  %5.2f  %7.2f%%  %8.2f%%" % (
        x, h, m, s["cagr"] * 100, s["sharpe"], s["maxdd"] * 100, prem.mean() * 12 * 100))

print("\n=== WEATHER GATE (restored panel, key cells) ===")
wz = pd.read_csv("/tmp/weather_NYC.csv", index_col=0, parse_dates=True)["close"]
hdd7 = pd.Series(np.maximum(0.0, 18.0 - wz), index=wz.index).rolling(7, min_periods=3).mean()
out = pd.Series(np.nan, index=hdd7.index)
for mth in range(1, 13):
    idx = hdd7.index[hdd7.index.month == mth]
    for i in range(len(idx)):
        t = idx[i]
        past = hdd7.loc[: t - pd.Timedelta(days=1)]
        past = past[past.index.month == mth].dropna()
        if len(past) >= 12:
            mu, sd = past.mean(), past.std()
            if sd > 1e-9:
                out.loc[t] = (hdd7.loc[t] - mu) / sd
z = out.clip(-8, 8)
zz = z.to_numpy(dtype=float)
gates = np.ones(len(z), dtype=float)
state = 1.0
for i in range(len(z)):
    if np.isnan(zz[i]):
        gates[i] = state
        continue
    if state == 1.0 and zz[i] < -1.0:
        state = 0.0
    elif state == 0.0 and zz[i] >= -0.5:
        state = 1.0
    gates[i] = state
g = pd.Series(gates, index=z.index).shift(1).fillna(1.0).reindex(net.index)
gp = factors["ng"] * g.fillna(1.0)
lvl = levels["ng"]
base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
gr = gp.shift(1).fillna(0.0) * lvl.diff() / base
gn = gr - 5 / 10000 * gp.diff().abs().fillna(0.0) - 20 / 252 / 10000 * gp.abs()
f2 = dict(factors); r2 = dict(rets); t2 = dict(turn)
f2["ng"] = gp; r2["ng"] = gr; t2["ng"] = gp.diff().abs().fillna(0.0)
n2 = b4.apply_costs(f2, r2, turnover=t2)
i2 = b4.window(n2, IS_START, df.index.max())
o2 = b4.window(n2, OOS_START, IS_START)
w2 = b4.weight_scheme(i2[["crack_321", "cross_sectional", "bzwti", "ng"]], "EQ")
bo = b4.apply_overlay(b4.book_returns(n2, ["crack_321", "cross_sectional", "bzwti", "ng"], w2).loc[o2.index])
s = b4.stats(bo)
print("  CORE3+NGW overlay: OOS Sh %.2f DD %.2f%% (champion 0.95 / -11.1%%)" % (s["sharpe"], s["maxdd"] * 100))