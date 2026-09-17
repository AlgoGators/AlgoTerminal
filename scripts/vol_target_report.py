"""Vol-targeted presentation numbers for the unit-risk strategy."""
import pandas as pd
import numpy as np

df = pd.read_csv("results/branch_unit_cool3_series.csv", parse_dates=["date"])
r = df.ret.to_numpy()
vol = r.std(ddof=1) * np.sqrt(252)
scale = 0.10 / vol
rs = r * scale
eq = (1 + rs).cumprod()
dd = (eq / np.maximum.accumulate(eq) - 1).min()
cagr = (1 + rs).prod() ** (252 / len(rs)) - 1
sr = rs.mean() / rs.std(ddof=1) * np.sqrt(252)
calmar = cagr / abs(dd)
print(f"unit series: ann vol {vol*100:.2f}% -> scale to 10% vol factor {scale:.3f}")
print(f"at 10% vol target: CAGR {cagr*100:+.2f}% | MaxDD {dd*100:.2f}% | "
      f"Sharpe {sr:.3f} | Calmar {calmar:.2f}")
s19 = df[df.date >= "2019-01-01"].ret.to_numpy() * scale
eq19 = (1 + s19).cumprod()
dd19 = (eq19 / np.maximum.accumulate(eq19) - 1).min()
print(f"2019+ at 10% vol: MaxDD {dd19*100:.2f}% | "
      f"Sharpe {s19.mean()/s19.std(ddof=1)*np.sqrt(252):.3f}")
