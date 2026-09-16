"""Print walk-forward sub-period metrics."""
import pandas as pd
import numpy as np

df = pd.read_csv("results/walkforward_series.csv", parse_dates=["date"])
for label, lo, hi in (("2019-2026 (fully OOS slice)", "2019-01-01", "2026-12-31"),
                      ("2012-2018 (controls-selected slice)", "2012-01-01", "2018-12-31")):
    s = df[(df.date >= lo) & (df.date <= hi)]
    r = s.ret.to_numpy()
    n = len(r)
    m = r.mean()
    sd = r.std(ddof=1)
    sr = m / sd * np.sqrt(252)
    ann = m * 252
    vol = sd * np.sqrt(252)
    eq = (1 + r).cumprod()
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    cagr = float(((1 + r).prod()) ** (252 / n) - 1)
    pos = np.abs(s.pos.to_numpy()) > 0
    runs = []
    i = 0
    while i < n:
        if pos[i]:
            j = i
            while j < n and pos[j]:
                j += 1
            runs.append(r[i:j].sum())
            i = j
        else:
            i += 1
    wins = [v for v in runs if v > 0]
    losses = [v for v in runs if v <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else np.nan
    print(f"{label}: days={n} ({n/252:.1f}y) ann {ann*100:+.2f}% CAGR {cagr*100:+.2f}% "
          f"Sh {sr:.3f} vol {vol*100:.2f}% DD {dd*100:.2f}% trades {len(runs)} "
          f"win {len(wins)/len(runs)*100:.0f}% avgW {np.mean(wins)*100:+.2f}% "
          f"avgL {np.mean(losses)*100:+.2f}% PF {pf:.2f}")
