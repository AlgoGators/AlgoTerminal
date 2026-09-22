"""Factor correlation / diversifier tests for the crack complex."""

import pandas as pd
import numpy as np
import yfinance as yf


def base_of(level, lookback: int = 20):
    """Return denominator: rolling mean of |level|.

    Used instead of pct_change so a spread that crosses zero does not
    explode the return. Same basis as the audit-corrected engine.
    """
    return level.abs().rolling(lookback, min_periods=10).mean().shift(1).replace(0.0, float("nan"))


raw = {}
for s, t in {"CL": "CL=F", "BZ": "BZ=F", "RB": "RB=F", "HO": "HO=F", "NG": "NG=F"}.items():
    d = yf.download(t, start="2023-09-08", end="2026-09-09", progress=False, auto_adjust=False, multi_level_index=False)
    raw[s] = d["Close"]
df = pd.DataFrame(raw).sort_index()
crack_wti = (2 * df.RB + df.HO) / 3 * 42 - df.CL
crack_ho = df.HO * 42 - df.CL

# Save the factor return series for cross-factor correlation
FACTOR_RETS = {}


def record_factor(name, r):
    FACTOR_RETS[name] = r.rename(name)




def seasonal_mean(s, minobs=10):
    out = pd.Series(np.nan, index=s.index)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        for i in range(len(idx)):
            t = idx[i]
            past = s.loc[: t - pd.Timedelta(days=1)]
            past = past[past.index.month == m]
            if len(past) >= minobs:
                out.loc[t] = past.mean()
    return out


def smr_pos(s, vt=0.5, lb=90, entry=0.75):
    prev = s.shift(1)
    seas = seasonal_mean(prev)
    adj = prev - seas
    mean = adj.rolling(lb, min_periods=45).mean()
    std = adj.rolling(lb, min_periods=45).std()
    z = (adj - mean) / std
    zz = z.to_numpy()
    vals = np.zeros(len(s))
    state = 0.0
    for i in range(len(s)):
        if np.isnan(zz[i]):
            vals[i] = 0
            continue
        if state == 0 and zz[i] < -entry:
            state = 1
        elif state == 1 and zz[i] >= -0.5:
            state = 0
        vals[i] = state
    sig = pd.Series(vals, index=s.index)
    level = s.abs().rolling(20, min_periods=10).mean().shift(1)
    rel = s.diff() / level
    rv = rel.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    rv = rv.replace(0, np.nan)
    scale = (vt / rv).clip(upper=1.0).fillna(0.5)
    return sig * scale


def cagr_sharpe(r):
    eq = (1 + r).cumprod()
    c = (eq.iloc[-1] ** (252 / len(r)) - 1) * 100 if len(r) else 0.0
    sh = r.mean() / r.std() * np.sqrt(252) if r.std() else 0.0
    return c, sh


p321 = smr_pos(crack_wti)
pho = smr_pos(crack_ho)
r_smr = (
    p321.shift(1).fillna(0) * (crack_wti.diff() / base_of(crack_wti)).fillna(0)
    + pho.shift(1).fillna(0) * (crack_ho.diff() / base_of(crack_ho)).fillna(0)
)
record_factor("F1_smr_book", r_smr)

print("=== CORRELATION OF CANDIDATE FACTORS WITH SMR BOOK ===")
print("SMR book vs CL daily ret:    %.2f" % r_smr.corr(df.CL.pct_change()))
print("SMR book vs NG daily ret:    %.2f" % r_smr.corr(df.NG.pct_change()))
print("SMR book vs BZ daily ret:    %.2f" % r_smr.corr(df.BZ.pct_change()))

cl_ma = df.CL.rolling(120, min_periods=60).mean().shift(1)
cl_mom = np.where(df.CL > cl_ma, 1.0, 0.0)
r_cl = pd.Series(cl_mom, index=df.index).shift(1).fillna(0) * df.CL.pct_change().fillna(0)
record_factor("CL_mom", r_cl)
c, sh = cagr_sharpe(r_cl)
print("\nCL momentum (long above 120d MA): CAGR=%.2f%% Sharpe=%.2f  corr with SMR=%.2f" % (c, sh, r_cl.corr(r_smr)))

slope = df.CL.rolling(60, min_periods=30).mean().diff(20).shift(1)
cl_mom2 = np.where((df.CL > cl_ma) & (slope > 0), 1.0, 0.0)
r_cl2 = pd.Series(cl_mom2, index=df.index).shift(1).fillna(0) * df.CL.pct_change().fillna(0)
record_factor("CL_mom_slope", r_cl2)
c, sh = cagr_sharpe(r_cl2)
print("CL momentum (above MA + slope>0): CAGR=%.2f%% Sharpe=%.2f  corr with SMR=%.2f" % (c, sh, r_cl2.corr(r_smr)))

ng_ret = df.NG.pct_change().fillna(0)
print("\nNG daily ret stats: mean=%+.4f%% ann_vol=%.0f%%  corr with SMR=%.2f" % (
    ng_ret.mean() * 100, ng_ret.std() * np.sqrt(252) * 100, ng_ret.corr(r_smr)))

gascrack = df.RB * 42 - df.CL
legs = {"crack_321": crack_wti, "crack_gas": gascrack, "crack_ho": crack_ho}
z_all = {}
for k, s in legs.items():
    prev = s.shift(1)
    seas = seasonal_mean(prev)
    adj = prev - seas
    mean = adj.rolling(90, min_periods=45).mean()
    std = adj.rolling(90, min_periods=45).std()
    z_all[k] = (adj - mean) / std
zdf = pd.DataFrame(z_all)
valid = zdf.notna().all(axis=1)
# Manual argmin per row, skipping all-NaN rows
arr = zdf.to_numpy(dtype=float)
cols = list(zdf.columns)
most_crushed = pd.Series(index=zdf.index, dtype=object)
for i in range(len(zdf)):
    row = arr[i]
    if valid.iloc[i] and len(row) and not np.isnan(row).all():
        most_crushed.iloc[i] = cols[int(np.nanargmin(row))]
has_crush = ((zdf < -0.5).any(axis=1)) & valid
r_xs = pd.Series(0.0, index=zdf.index)
for k in legs:
    on = (most_crushed == k) & has_crush
    r_xs[on] = (legs[k].diff() / base_of(legs[k])).fillna(0)[on]
r_xs = r_xs.shift(1).fillna(0)
record_factor("F2_cross_sectional", r_xs)
c, sh = cagr_sharpe(r_xs)
print("\nCross-sectional (long most-crushed leg only): CAGR=%.2f%% Sharpe=%.2f days=%.1f%%" % (
    c, sh, (r_xs != 0).mean() * 100))

# NG seasonal crush: same signal on natgas level (winter-demand reversion)
ng_prev = df.NG.shift(1)
ng_seas = seasonal_mean(ng_prev)
ng_adj = ng_prev - ng_seas
ng_mean = ng_adj.rolling(90, min_periods=45).mean()
ng_std = ng_adj.rolling(90, min_periods=45).std()
ng_z = (ng_adj - ng_mean) / ng_std
ng_zz = ng_z.to_numpy()
ng_vals = np.zeros(len(df))
state = 0.0
for i in range(len(df)):
    if np.isnan(ng_zz[i]):
        ng_vals[i] = 0
        continue
    if state == 0 and ng_zz[i] < -0.75:
        state = 1
    elif state == 1 and ng_zz[i] >= -0.5:
        state = 0
    ng_vals[i] = state
ng_sig = pd.Series(ng_vals, index=df.index)
ng_level = df.NG.abs().rolling(20, min_periods=10).mean().shift(1)
ng_rel = df.NG.diff() / ng_level
ng_rv = ng_rel.rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
ng_rv = ng_rv.replace(0, np.nan)
ng_scale = (0.5 / ng_rv).clip(upper=1.0).fillna(0.5)
ng_pos = ng_sig * ng_scale
r_ng = ng_pos.shift(1).fillna(0) * df.NG.pct_change().fillna(0)
record_factor("F3_ng_seasonal", r_ng)
c, sh = cagr_sharpe(r_ng)
print("NG seasonal crush (long): CAGR=%.2f%% Sharpe=%.2f  corr with SMR=%.2f" % (c, sh, r_ng.corr(r_smr)))

# Brent-WTI crude convergence as a small add-on: z-score reversion, sized vt=0.15
bzwti = df.BZ - df.CL
bw_mean = bzwti.rolling(60, min_periods=30).mean().shift(1)
bw_std = bzwti.rolling(60, min_periods=30).std().shift(1)
bw_z = (bzwti - bw_mean) / bw_std
bw_zz = bw_z.to_numpy()
bw_vals = np.zeros(len(df))
state = 0.0
for i in range(len(df)):
    if np.isnan(bw_zz[i]):
        bw_vals[i] = 0
        continue
    if state == 0:
        if bw_zz[i] < -1.0:
            state = 1.0
        elif bw_zz[i] > 1.0:
            state = -1.0
    elif state == 1.0:
        if bw_zz[i] >= 0.0:
            state = 0.0
    else:
        if bw_zz[i] <= 0.0:
            state = 0.0
    bw_vals[i] = state
bw_sig = pd.Series(bw_vals, index=df.index)
bw_pos = bw_sig * 0.15  # small book add, sized low
r_bw = bw_pos.shift(1).fillna(0) * (bzwti.diff() / base_of(bzwti)).fillna(0)
record_factor("F4_bw_convergence", r_bw)
c, sh = cagr_sharpe(r_bw)
print("Brent-WTI convergence (vt~0.15): CAGR=%.2f%% Sharpe=%.2f  corr with SMR=%.2f" % (c, sh, r_bw.corr(r_smr)))

print()
print("=== FACTOR CORRELATION MATRIX ===")
fr = pd.DataFrame(FACTOR_RETS).dropna()
print(fr.corr().round(2).to_string())

print()
print("=== COMBINED FACTOR BOOK (equal-vol weights, inverse vol) ===")
vols = fr.std()
w = (1.0 / vols)
w = w / w.sum()
book = fr.mul(w, axis=1).sum(axis=1)
c, sh = cagr_sharpe(book)
print("inverse-vol equal book: CAGR=%.2f%% Sharpe=%.2f" % (c, sh))
# Also a book of just the three positive factors
pos_factors = [k for k in fr.columns if fr[k].mean() > 0]
w2 = 1.0 / fr[pos_factors].std()
w2 = w2 / w2.sum()
book2 = fr[pos_factors].mul(w2, axis=1).sum(axis=1)
c2, sh2 = cagr_sharpe(book2)
print("inverse-vol book (positive factors only): CAGR=%.2f%% Sharpe=%.2f  factors=%s" % (c2, sh2, pos_factors))
