"""Exposure-comparable drawdown measures across modes (constant-scaling only)."""
import pandas as pd
import numpy as np

rows = []
for mode in ("unit", "kelly", "anchor", "kelly_half"):
    df = pd.read_csv(f"results/branch_{mode}_cool3_series.csv", parse_dates=["date"])
    r = df.ret.to_numpy()
    pos = df.pos.to_numpy()
    n = len(r)
    vol = r.std(ddof=1) * np.sqrt(252)
    eq_u = (1 + r).cumprod()
    dd_u = abs(float((eq_u / np.maximum.accumulate(eq_u) - 1).min()))
    cagr_u = (1 + r).prod() ** (252 / n) - 1
    sr_u = r.mean() / r.std(ddof=1) * np.sqrt(252)
    calmar = cagr_u / dd_u
    mean_expo = np.abs(pos).mean()
    dd_vol = dd_u / vol
    dd_expo = dd_u / mean_expo
    scale = 0.10 / vol
    rs = r * scale
    eq = (1 + rs).cumprod()
    dd10 = abs(float((eq / np.maximum.accumulate(eq) - 1).min()))
    cagr10 = (1 + rs).prod() ** (252 / n) - 1
    calmar10 = cagr10 / dd10
    s19 = r[df.date >= "2019-01-01"]
    eq19 = (1 + s19 * scale).cumprod()
    dd19 = abs(float((eq19 / np.maximum.accumulate(eq19) - 1).min()))
    sr19 = (s19 * scale).mean() / (s19 * scale).std(ddof=1) * np.sqrt(252)
    rows.append(dict(mode=mode, rawDD=dd_u, Sharpe=sr_u, Calmar=calmar,
                     DDperVol=dd_vol, DDperExpo=dd_expo,
                     DD_at10vol=dd10, Calmar10=calmar10, Sh2019=sr19, DD2019=dd19))
out = pd.DataFrame(rows)
print(out.round(3).to_string(index=False))
out.to_csv("results/comparison_drawdown_measures.csv", index=False)
