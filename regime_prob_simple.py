"""Probabilistic windfall regime — heuristic, no sklearn, continuous prob."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
DEV=Path("/home/sebas/algoterminal-strategy-dev")
spec=importlib.util.spec_from_file_location("b5", str(DEV/"book_oos_v5.py"))
b5=importlib.util.module_from_spec(spec); spec.loader.exec_module(b5)
spec3=importlib.util.spec_from_file_location("fb", str(DEV/"factor_book.py"))
fb=importlib.util.module_from_spec(spec3); spec3.loader.exec_module(fb)
def sigmoid(z): return 1/(1+np.exp(-np.clip(z,-30,30)))
def roc_auc(y,p):
    if y.nunique()<=1: return np.nan
    order=np.argsort(p); y_sorted=y.to_numpy()[order]
    pos=np.where(y_sorted==1)[0]; n_pos=len(pos); n_neg=len(y_sorted)-n_pos
    if n_pos==0 or n_neg==0: return np.nan
    rank_sum=np.sum(pos+1); return (rank_sum - n_pos*(n_pos+1)/2)/(n_pos*n_neg)
def avg_prec(y,p):
    if y.nunique()<=1: return np.nan
    order=np.argsort(-p); y_sorted=y.to_numpy()[order]
    prec=[]; tp=0
    for i,val in enumerate(y_sorted):
        if val==1:
            tp+=1; prec.append(tp/(i+1))
    return np.mean(prec) if prec else 0.0
def brier(y,p): return np.mean((y.to_numpy()-p)**2)
def stats(r):
    r=r.dropna()
    if len(r)==0 or r.std()==0: return {"sharpe":np.nan,"cagr":np.nan,"maxdd":np.nan,"worst":np.nan,"vol":np.nan}
    eq=(1+r).cumprod(); years=len(r)/252
    return {"sharpe":r.mean()/r.std()*np.sqrt(252),"cagr":eq.iloc[-1]**(1/years)-1,"maxdd":(eq/eq.cummax()-1).min(),"worst":r.min(),"vol":r.std()*np.sqrt(252)}
def window(s,a,b):
    WARMUP=90
    out=s.loc[a:b]; return out.iloc[WARMUP:] if len(out)>WARMUP else out
import pandas as pd
PANEL=b5.PANEL
IS_START=pd.Timestamp("2023-09-08")
OOS_START=pd.Timestamp("2007-07-30")
df=pd.read_parquet(PANEL).sort_index()
levels=fb.build_levels(df)
levels["__df__"]=df
bl=b5.brent_levels(df)
for k,v in bl.items(): levels[k]=v
factors,rets,turn,legpos=b5.build_v5(levels,None,False)
net=b5.apply_costs(factors,rets,turnover=turn)
isw=net.loc[IS_START:].iloc[90:]
w=b5.weight_scheme(isw[["crack_321","cross_sectional","bzwti"]],"EQ")
raw_book=b5.book_returns(net, ["crack_321","cross_sectional","bzwti"], w)
raw_oos=window(raw_book,OOS_START,IS_START)
raw_is=window(raw_book,IS_START,df.index.max())
zdf={k:fb.seasonal_z(levels[k]) for k in ["crack_321","crack_gas","crack_ho","ng","bzwti"]}
for k in ["brent321","brent_gas","brent_ho"]: zdf[k]=fb.seasonal_z(bl[k])
depth=b5.book_depth(legpos,zdf,pd.Index(df.index))
held=depth.shift(1)
crash5=depth.shift(6)-depth.shift(1)
crash10=depth.shift(11)-depth.shift(1)
crude20=df.CL.pct_change(20).shift(1)
crude10=df.CL.pct_change(10).shift(1)
vol20=raw_book.rolling(20,min_periods=10).std().shift(1)
joint_raw=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
joint_raw=joint_raw.fillna(False).astype(int)
# Labels: windfall >2% in next 5 days
is_wind=(raw_book>0.02).astype(int)
lab5=is_wind.rolling(5,min_periods=1).max().shift(-5).fillna(0)
lab10=is_wind.rolling(10,min_periods=1).max().shift(-10).fillna(0)
feat=pd.DataFrame({"held":held,"crash5":crash5,"crash10":crash10,"crude20":crude20,"crude10":crude10,"vol20":vol20,"joint":joint_raw}, index=df.index).fillna(0).clip(-8,8)
feat["wind5"]=lab5
feat["wind10"]=lab10
feat_oos=feat.loc[OOS_START:IS_START].iloc[90:]
feat_is=feat.loc[IS_START:].iloc[90:]
print(f"OOS rows {len(feat_oos)} wind5 pos {(feat_oos['wind5']==1).sum()} ({(feat_oos['wind5']==1).mean()*100:.2f}%)")
print(f"IS rows {len(feat_is)} wind5 pos {(feat_is['wind5']==1).sum()}")
# Heuristic score: tuned to separate wind5
# From earlier: crash5+, held negative deep, crude negative, vol high
# Score = -4 + 1.0*crash5 -0.6*held -6*crude20 + 1.5*joint + 2*vol20*10  (vol scaled)
# Tune bias so mean prob ~ base rate 1.5% for wind5
# Let's grid search bias and weights quickly to maximize AUC on OOS train portion 2007-2015
train=feat.loc[:"2015-01-01"].iloc[90:]
# simple grid: keep weights fixed, vary bias
best=None
for bias in [-5,-4.5,-4,-3.5,-3]:
    score = bias + 1.0*train["crash5"] -0.6*train["held"] -6*train["crude20"] + 1.5*train["joint"] + 5*train["vol20"]
    prob=sigmoid(score)
    auc=roc_auc(train["wind5"], prob)
    if best is None or auc>best[0]:
        best=(auc,bias)
print(f"Best bias {best[1]} AUC {best[0]:.3f} on train 2007-2015")
bias=best[1]
# Final score on full
score = bias + 1.0*feat["crash5"] -0.6*feat["held"] -6*feat["crude20"] + 1.5*feat["joint"] + 5*feat["vol20"]
# also add crash10 slightly
score = score + 0.3*feat["crash10"]
prob=sigmoid(score)
# Calibrate: scale prob to match empirical wind rate via isotonic-ish: prob is 0-1 but mean ~? Let's check
print(f"Heuristic prob mean OOS {prob.loc[OOS_START:IS_START].iloc[90:].mean():.3f} max {prob.loc[OOS_START:IS_START].iloc[90:].max():.3f} wind rate {feat_oos['wind5'].mean():.3f}")
# Evaluate
for name, idx in [("OOS", feat_oos.index), ("IS", feat_is.index), ("train 07-15", train.index), ("test 20-23", feat.loc["2020-01-02":"2023-09-07"].index)]:
    y=feat.loc[idx,"wind5"]
    p=prob.loc[idx]
    print(f"{name:12s} AUC {roc_auc(y,p):.3f} AP {avg_prec(y,p):.3f} Brier {brier(y,p):.4f} meanProb {p.mean():.3f} max {p.max():.3f} pos {int(y.sum())}/{len(y)}")
# Show trace around 2020-04-20
print("\nProb trace around 2020-04-20 (wind5 = any >2% in next 5):")
focus=feat.loc["2020-04-10":"2020-05-10"]
for idx in focus.index:
    if idx in prob.index:
        y=int(feat.loc[idx,"wind5"])
        flag="WIND" if y==1 else "    "
        print(f" {idx.date()} prob {prob.loc[idx]:.1%} {flag} raw {raw_book.loc[idx]*100:+.1f}% held {held.loc[idx]:+.2f} crash5 {crash5.loc[idx]:+.2f} crude20 {crude20.loc[idx]*100:+.1f}% wind5inNext {y}")
        if idx==pd.Timestamp("2020-04-20"):
            break

print("\nTrace 2019 bleed (should be low):")
focus2=feat.loc["2019-08-01":"2019-09-10"]
for idx in focus2.index[:10]:
    y=int(feat.loc[idx,"wind5"])
    print(f" {idx.date()} prob {prob.loc[idx]:.1%} y {y} raw {raw_book.loc[idx]*100:+.1f}%")

# Show distribution: prob buckets
print("\nProb buckets vs actual wind rate OOS:")
bins=[0,0.02,0.05,0.10,0.20,0.5,1.0]
for lo,hi in zip(bins[:-1],bins[1:]):
    m=(prob.loc[feat_oos.index]>=lo)&(prob.loc[feat_oos.index]<hi)
    if m.sum()>0:
        print(f" {lo:.0%}-{hi:.0%} n={int(m.sum())} meanProb {prob.loc[feat_oos.index][m].mean():.1%} actualWind {feat_oos.loc[m,'wind5'].mean():.1%}")

# Wire prob to sizing vs half joint
# Size = 0.5 + 0.5*(prob - p10)/(p90-p10) clipped, but continuous
p10,p90=np.percentile(prob.loc[feat.loc["2020-01-02":"2023-09-07"].index],[10,90])
print(f"\np10 {p10:.3f} p90 {p90:.3f}")
prob_scaled=((prob - p10)/(p90-p10)).clip(0,1)
size_prob=0.5+0.5*prob_scaled
# Evaluate sizing on test period 2020-2023
test_idx=feat.loc["2020-01-02":"2023-09-07"].index
raw_test=raw_book.loc[test_idx]
# V2, half joint, prob sizing
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

def apply_prob(book, prob_s):
    rv=book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
    gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
    g=gear.shift(1).fillna(1.0)
    n=len(book); scale=np.empty(n); state=1.0; eq,hwm=1.0,1.0; eng_eq,eng_hwm=1.0,1.0
    pv=prob_s.reindex(book.index).fillna(0.5).to_numpy(float)
    for t in range(n):
        # continuous override: scale = 0.5 + 0.5*pv[t] when pv>0.3 else V2
        if pv[t]>0.3:
            scale[t]=0.5+0.5*pv[t]
            state=scale[t]
        else:
            scale[t]=state
        r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
        eq*=1+ret; hwm=max(hwm,eq); exp_dd=eq/hwm-1 if hwm>0 else 0
        eng_eq*=1+r; was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq); new_high=eng_eq>=was
        if pv[t]>0.3:
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

joint_test=joint_raw.loc[test_idx].fillna(False)
half_test=apply_half(raw_test, joint_test)
prob_test_series=prob_scaled.loc[test_idx]
prob_overlay=apply_prob(raw_test, prob_test_series)
v2_test=b5.apply_overlay_v2(raw_test)
for label,s in [("V2",v2_test),("HALF joint",half_test),("PROB cont",prob_overlay)]:
    st=stats(s)
    print(f" {label:12s} Sharpe {st['sharpe']:.2f} CAGR {st['cagr']*100:.1f}% DD {st['maxdd']*100:.1f}% worst {st['worst']*100:.2f}%")
pd.DataFrame({"prob":prob.loc[test_idx],"prob_scaled":prob_scaled.loc[test_idx],"raw":raw_test,"joint":joint_test.astype(int)}).to_csv(DEV/"regime_probs_simple.csv")
print("Saved regime_probs_simple.csv")
# Show continuous prob evolution sample
print("\nContinuous prob sample (every 5th day):")
for idx in test_idx[::20][:10]:
    print(f" {idx.date()} prob {prob.loc[idx]:.0%} scaled {prob_scaled.loc[idx]:.0%} size {0.5+0.5*prob_scaled.loc[idx]:.2f} raw {raw_book.loc[idx]*100:+.1f}%")
