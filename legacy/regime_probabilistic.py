"""Probabilistic windfall regime: P(windfall in next H days) at each t, causal.

Windfall = raw CORE3 book return >2% in next 5 days (or top20 days).
We want continuous prob, not binary: 37% now, 22% next horizon.

Features causal at close t-1:
  held (depth), crash5, crude20, crude10, vol20, depth*crash interaction, crude*crash
Label: did a windfall occur in next H=5 or 10 or 20 days?
Model: L2 logistic, time-series split (train 2007-2015, valid 2015-2020, test 2020-2023 plus IS 2023-26 as holdout).
Calibrated via isotonic or Platt. Evaluate AUC, PR, Brier, calibration curve, and prob trace around 2020-04-20.

We also wire prob to sizing: size = 0.5 + 0.5*prob_scaled where prob_scaled = (prob - p05)/(p95-p05) clipped.
Compare to HALF joint (0.5) and FULL (1.0).
"""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
# sklearn not available — manual logistic, metrics, and isotonic via numpy
def sigmoid(z):
    return 1/(1+np.exp(-np.clip(z,-30,30)))

def roc_auc(y, p):
    # Mann-Whitney
    if y.nunique()<=1:
        return np.nan
    order=np.argsort(p)
    y_sorted=y.to_numpy()[order]
    # rank sum
    pos=np.where(y_sorted==1)[0]
    n_pos=len(pos); n_neg=len(y_sorted)-n_pos
    if n_pos==0 or n_neg==0:
        return np.nan
    # sum ranks of positives (1-indexed)
    rank_sum=np.sum(pos+1)
    auc=(rank_sum - n_pos*(n_pos+1)/2)/(n_pos*n_neg)
    return auc

def avg_prec(y,p):
    if y.nunique()<=1:
        return np.nan
    order=np.argsort(-p)
    y_sorted=y.to_numpy()[order]
    prec=[]; rec=[]; tp=0
    for i, val in enumerate(y_sorted):
        if val==1:
            tp+=1
            prec.append(tp/(i+1))
    return np.mean(prec) if prec else 0.0

def brier(y,p):
    return np.mean((y.to_numpy()-p)**2)

DEV=Path("/home/sebas/algoterminal-strategy-dev")
spec=importlib.util.spec_from_file_location("b5", str(DEV/"book_oos_v5.py"))
b5=importlib.util.module_from_spec(spec); spec.loader.exec_module(b5)
spec3=importlib.util.spec_from_file_location("fb", str(DEV/"factor_book.py"))
fb=importlib.util.module_from_spec(spec3); spec3.loader.exec_module(fb)
PANEL=b5.PANEL
IS_START=pd.Timestamp("2023-09-08")
OOS_START=pd.Timestamp("2007-07-30")
WARMUP=90

def window(s,a,b):
    out=s.loc[a:b]; return out.iloc[WARMUP:] if len(out)>WARMUP else out

df=pd.read_parquet(PANEL).sort_index()
levels=fb.build_levels(df)
levels["__df__"]=df
bl=b5.brent_levels(df)
for k,v in bl.items(): levels[k]=v
factors,rets,turn,legpos=b5.build_v5(levels,None,False)
net=b5.apply_costs(factors,rets,turnover=turn)
isw=net.loc[IS_START:].iloc[WARMUP:]
w=b5.weight_scheme(isw[["crack_321","cross_sectional","bzwti"]],"EQ")
raw_book=b5.book_returns(net, ["crack_321","cross_sectional","bzwti"], w)
raw_is=window(raw_book,IS_START,df.index.max())
raw_oos=window(raw_book,OOS_START,IS_START)
# depth
zdf={k:fb.seasonal_z(levels[k]) for k in ["crack_321","crack_gas","crack_ho","ng","bzwti"]}
for k in ["brent321","brent_gas","brent_ho"]: zdf[k]=fb.seasonal_z(bl[k])
depth=b5.book_depth(legpos,zdf,pd.Index(df.index))
held=depth.shift(1)
crash5=depth.shift(6)-depth.shift(1)
crash10=depth.shift(11)-depth.shift(1)
crude20=df.CL.pct_change(20).shift(1)
crude10=df.CL.pct_change(10).shift(1)
vol20=raw_book.rolling(20,min_periods=10).std().shift(1)
# joint as feature too
joint_raw=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
joint_raw=joint_raw.fillna(False).astype(int)

# Build feature frame for OOS+IS
idx=raw_book.index
feat=pd.DataFrame({
    "held": held,
    "crash5": crash5,
    "crash10": crash10,
    "crude20": crude20,
    "crude10": crude10,
    "vol20": vol20,
    "joint": joint_raw.astype(float),
    "held_x_crash": held*crash5,
    "crash_x_crude": crash5*crude20,
}, index=idx)
feat=feat.fillna(0).clip(-8,8)  # clip extremes
# Labels: windfall in next H days = any day raw >2% in next H
for H in [5,10,20]:
    # raw threshold 2% single day
    is_wind = (raw_book > 0.02).astype(int)
    # rolling max in next H
    # causal label at t: lookahead 1..H
    lab = is_wind.rolling(H, min_periods=1).max().shift(-H).fillna(0)
    # also 5-day cumulative >5% as alternative
    cum5 = raw_book.rolling(5).sum().shift(-5)
    lab_cum = (cum5 > 0.05).astype(int).fillna(0)
    feat[f"wind_next{H}"] = lab
    feat[f"wind_cum5_next{H}"] = lab_cum

# Use wind_next5 as primary (any >2% day in next 5)
feat_oos=feat.loc[OOS_START:IS_START].iloc[WARMUP:]
feat_is=feat.loc[IS_START:].iloc[WARMUP:]
print(f"Feature rows OOS {len(feat_oos)} IS {len(feat_is)}")
for H in [5,10,20]:
    print(f" wind_next{H} OOS pos {(feat_oos[f'wind_next{H}']==1).sum()} ({(feat_oos[f'wind_next{H}']==1).mean()*100:.2f}%) IS {(feat_is[f'wind_next{H}']==1).sum()}")

# Time-series split: train 2007-2015, valid 2015-2020, test 2020-2023
# Use OOS period split
train = feat_oos.loc[:'2015-01-01']
valid = feat_oos.loc['2015-01-02':'2020-01-01']
test = feat_oos.loc['2020-01-02':'2023-09-07']
# Also holdout IS
holdout = feat_is

feature_cols=["held","crash5","crude20","crude10","vol20","joint","held_x_crash","crash_x_crude"]
# also add crash10
feature_cols.append("crash10")

for H in [5]:
    print(f"\n=== H={H} wind_next{H} ===")
    y_train=train[f"wind_next{H}"]
    y_valid=valid[f"wind_next{H}"]
    y_test=test[f"wind_next{H}"]
    y_hold=holdout[f"wind_next{H}"]
    X_train=train[feature_cols]
    X_valid=valid[feature_cols]
    X_test=test[feature_cols]
    X_hold=holdout[feature_cols]
    # handle class imbalance: pos ~0.5-2%
    # Use balanced class_weight
    clf=LogisticRegression(class_weight='balanced', max_iter=1000, C=1.0, solver='lbfgs')
    clf.fit(X_train, y_train)
    print(f"  Coef: {dict(zip(feature_cols, clf.coef_[0].round(3)))} intercept {clf.intercept_[0]:.3f}")
    for name, X, y in [("train",X_train,y_train),("valid",X_valid,y_valid),("test",X_test,y_test),("IS holdout",X_hold,y_hold)]:
        prob=clf.predict_proba(X)[:,1]
        auc=roc_auc_score(y, prob) if y.nunique()>1 else np.nan
        ap=average_precision_score(y, prob) if y.nunique()>1 else np.nan
        brier=brier_score_loss(y, prob)
        print(f"  {name:12s} n={len(y)} pos {int(y.sum())} AUC {auc:.3f} AP {ap:.3f} Brier {brier:.4f} meanProb {prob.mean():.3f} max {prob.max():.3f}")
    # Calibration via isotonic on valid
    prob_valid=clf.predict_proba(X_valid)[:,1]
    iso=IsotonicRegression(out_of_bounds='clip')
    iso.fit(prob_valid, y_valid)
    for name, X, y in [("test iso",X_test,y_test),("IS iso",X_hold,y_hold)]:
        prob=clf.predict_proba(X)[:,1]
        prob_iso=iso.transform(prob)
        auc=roc_auc_score(y, prob_iso) if y.nunique()>1 else np.nan
        ap=average_precision_score(y, prob_iso) if y.nunique()>1 else np.nan
        brier=brier_score_loss(y, prob_iso)
        print(f"  {name:12s} iso AUC {auc:.3f} AP {ap:.3f} Brier {brier:.4f} mean {prob_iso.mean():.3f} max {prob_iso.max():.3f}")
    # Show prob trace around 2020-04-20
    print("\n  Prob trace around 2020-04-20 (test period, wind_next5):")
    prob_test=clf.predict_proba(X_test)[:,1]
    prob_test_iso=iso.transform(prob_test)
    df_test=pd.DataFrame({"prob":prob_test,"prob_iso":prob_test_iso,"y":y_test.values}, index=X_test.index)
    focus=df_test.loc['2020-04-10':'2020-05-10']
    for idx,row in focus.iterrows():
        flag="WIND" if row["y"]==1 else "    "
        print(f"   {idx.date()} prob {row['prob']:.2%} iso {row['prob_iso']:.2%} {flag} raw {raw_book.loc[idx]*100:+.1f}% held {held.loc[idx]:+.2f} crash5 {crash5.loc[idx]:+.2f} crude20 {crude20.loc[idx]*100:+.1f}%")
    # Also show 2019 bleed period where joint false but prob?
    print("\n  Prob trace 2019-08 bleed (should be low):")
    focus2=df_test.loc['2019-08-01':'2019-09-10']
    for idx,row in focus2.head(10).iterrows():
        print(f"   {idx.date()} prob {row['prob']:.1%} iso {row['prob_iso']:.1%} y {int(row['y'])} raw {raw_book.loc[idx]*100:+.1f}%")
    # Wire prob to sizing: size = 0.5 + 0.5 * (prob_iso - p10)/(p90-p10) clipped, vs half joint
    # Evaluate sizing as overlay: size_t = 0.5 + 0.5*prob_iso_scaled
    p10, p90 = np.percentile(prob_test_iso, [10,90])
    prob_scaled = ((prob_test_iso - p10)/(p90-p10)).clip(0,1) if p90>p10 else np.zeros_like(prob_test_iso)
    size_prob = 0.5 + 0.5*prob_scaled
    # Build overlay with prob sizing vs half joint vs V2
    # For test period only
    raw_test=raw_oos.loc[test.index]
    # V2 baseline
    v2_test=b5.apply_overlay_v2(raw_test)
    # half joint baseline
    j_test=joint.reindex(raw_test.index).fillna(False)
    def apply_half(book,j):
        rv=book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
        gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
        g=gear.shift(1).fillna(1.0)
        n=len(book); scale=np.empty(n); state=1.0; eq,hwm=1.0,1.0; eng_eq,eng_hwm=1.0,1.0
        jv=j.reindex(book.index).fillna(False).to_numpy(bool)
        for t in range(n):
            if jv[t]: scale[t]=0.5; state=0.5
            else: scale[t]=state
            r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
            eq*=1+ret; hwm=max(hwm,eq); exp_dd=eq/hwm-1 if hwm>0 else 0
            eng_eq*=1+r; was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq); new_high=eng_eq>=was
            if jv[t]: state=0.5
            else:
                if state==1.0:
                    if exp_dd<=-0.10: state=0.0
                    elif exp_dd<=-0.06: state=0.5
                elif state==0.5:
                    if exp_dd<=-0.10: state=0.0
                    elif new_high: state=1.0
                else:
                    if new_high: state=1.0
        return book*pd.Series(scale,index=book.index)*g
    half_test=apply_half(raw_test, j_test)
    # prob sizing overlay: use prob size as scale when prob high? Instead blend: scale = 0.5 + 0.5*prob_scaled, but only when prob > median?
    # For comparison, use prob size as direct overlay scale (replace half joint logic with prob size, but keep V2 otherwise)
    def apply_prob(book, prob_scaled_series):
        rv=book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
        gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
        g=gear.shift(1).fillna(1.0)
        n=len(book); scale=np.empty(n); state=1.0; eq,hwm=1.0,1.0; eng_eq,eng_hwm=1.0,1.0
        pv=prob_scaled_series.reindex(book.index).fillna(0.5).to_numpy(float)
        for t in range(n):
            # if prob high, override state to prob size; else V2
            if pv[t] > 0.6:  # threshold for prob override
                scale[t]=0.5 + 0.5*pv[t]
                state=scale[t]
            else:
                scale[t]=state
            r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
            eq*=1+ret; hwm=max(hwm,eq); exp_dd=eq/hwm-1 if hwm>0 else 0
            eng_eq*=1+r; was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq); new_high=eng_eq>=was
            if pv[t] > 0.6:
                state=0.5+0.5*pv[t]
            else:
                if state==1.0:
                    if exp_dd<=-0.10: state=0.0
                    elif exp_dd<=-0.06: state=0.5
                elif state==0.5:
                    if exp_dd<=-0.10: state=0.0
                    elif new_high: state=1.0
                else:
                    if new_high: state=1.0
        return book*pd.Series(scale,index=book.index)*g
    prob_series=pd.Series(prob_scaled, index=X_test.index)
    prob_test_overlay=apply_prob(raw_test, prob_series)
    def stats2(r):
        r=r.dropna()
        eq=(1+r).cumprod(); years=len(r)/252
        return {"sharpe":r.mean()/r.std()*np.sqrt(252) if r.std()!=0 else np.nan,"cagr":eq.iloc[-1]**(1/years)-1,"maxdd":(eq/eq.cummax()-1).min(),"worst":r.min()}
    print(f"\n  Sizing comparison on test 2020-2023 (prob wiring):")
    for label, s in [("V2",v2_test),("HALF joint",half_test),("PROB scaled",prob_test_overlay)]:
        st=stats2(s)
        print(f"   {label:12s} Sharpe {st['sharpe']:.2f} CAGR {st['cagr']*100:.1f}% DD {st['maxdd']*100:.1f}% worst {st['worst']*100:.2f}%")
    # Save probs for plotting
    pd.DataFrame({"prob":prob_test,"prob_iso":prob_test_iso,"prob_scaled":prob_scaled,"raw":raw_test,"joint":j_test.astype(int)}, index=X_test.index).to_csv(DEV/"regime_probs.csv")
    print("\nSaved regime_probs.csv")

# Also quick feature importance via correlation with label
print("\n=== Feature correlation with wind_next5 (OOS) ===")
for c in feature_cols:
    print(f" {c:16s} corr {feat_oos[c].corr(feat_oos['wind_next5']):+.3f}")
