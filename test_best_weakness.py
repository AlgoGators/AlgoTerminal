"""Weakness scan for best strategy: CORE3 EQ BOOK HALF (joint 0.5)."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
DEV=Path("/home/sebas/algoterminal-strategy-dev")
spec=importlib.util.spec_from_file_location("b5", str(DEV/"book_oos_v5.py"))
b5=importlib.util.module_from_spec(spec); spec.loader.exec_module(b5)
spec3=importlib.util.spec_from_file_location("fb", str(DEV/"factor_book.py"))
fb=importlib.util.module_from_spec(spec3); spec3.loader.exec_module(fb)
spec_v=importlib.util.spec_from_file_location("bv", str(DEV/"book_vNext.py"))
bv=importlib.util.module_from_spec(spec_v); spec_v.loader.exec_module(bv)
PANEL=bv.PANEL
IS_START=bv.IS_START
OOS_START=bv.OOS_START
WARMUP=90
def stats(r):
    r=r.dropna()
    if len(r)==0 or r.std()==0: return {"sharpe":np.nan,"cagr":np.nan,"maxdd":np.nan,"worst":np.nan,"vol":np.nan}
    eq=(1+r).cumprod(); years=len(r)/252
    return {"sharpe":r.mean()/r.std()*np.sqrt(252),"cagr":eq.iloc[-1]**(1/years)-1,"maxdd":(eq/eq.cummax()-1).min(),"worst":r.min(),"vol":r.std()*np.sqrt(252)}
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
depth=b5.book_depth(legpos,{k:fb.seasonal_z(levels[k]) for k in ["crack_321","crack_gas","crack_ho","ng","bzwti"]} | {k:fb.seasonal_z(bl[k]) for k in ["brent321","brent_gas","brent_ho"]}, pd.Index(df.index))
held=depth.shift(1)
crash5=depth.shift(6)-depth.shift(1)
crude20=df.CL.pct_change(20).shift(1)
joint=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
joint=joint.fillna(False)
# best = half joint book overlay
import importlib.util as iu
# reuse bv apply_overlay_prob with half
def half_overlay(book, j):
    return bv.apply_overlay_prob(book, j.reindex(book.index).fillna(False), None, joint_scale=0.5)
best_is=half_overlay(raw_is, joint.reindex(raw_is.index).fillna(False))
best_oos=half_overlay(raw_oos, joint.reindex(raw_oos.index).fillna(False))
v2_is=b5.apply_overlay_v2(raw_is)
v2_oos=b5.apply_overlay_v2(raw_oos)
print("=== Best (HALF joint) vs V2 vs Raw ===")
for label, bi, bo, raw in [("V2",v2_is,v2_oos,raw_oos),("HALF",best_is,best_oos,raw_oos),("RAW",raw_is,raw_oos,raw_oos)]:
    print(f"{label:6s} IS {stats(bi)['sharpe']:.2f} {stats(bi)['maxdd']*100:+.1f}% vol{stats(bi)['vol']*100:.1f}% | OOS {stats(bo)['sharpe']:.2f} {stats(bo)['cagr']*100:.1f}% DD {stats(bo)['maxdd']*100:+.1f}% vol{stats(bo)['vol']*100:.1f}% worst{stats(bo)['worst']*100:.2f}%")

print("\n=== Yearly OOS HALF vs V2 vs RAW ===")
for y in sorted(set(raw_oos.index.year)):
    print(f"{y} raw {raw_oos[raw_oos.index.year==y].sum()*100:+5.1f}% v2 {v2_oos[v2_oos.index.year==y].sum()*100:+5.1f}% half {best_oos[best_oos.index.year==y].sum()*100:+5.1f}%")

print("\n=== Worst 10 days HALF OOS ===")
print(best_oos.nsmallest(10).to_string())
print("\nWorst 10 attribution (factor nets on those days):")
worst_idx=best_oos.nsmallest(10).index
# factor nets weighted
for idx in worst_idx:
    contrib={f: net.loc[idx,f]*w[f] for f in ["crack_321","cross_sectional","bzwti"]}
    print(f"{idx.date()} half {best_oos.loc[idx]*100:+5.2f}% raw {raw_oos.loc[idx]*100:+5.2f}% -> crack321 {contrib['crack_321']*100:+5.2f}% cross {contrib['cross_sectional']*100:+5.2f}% bzwti {contrib['bzwti']*100:+5.2f}% joint {joint.loc[idx]}")

print("\n=== Best 10 days HALF OOS ===")
print(best_oos.nlargest(10).to_string())

print("\n=== Drawdown episodes HALF OOS ===")
eq=(1+best_oos).cumprod()
hwm=eq.cummax()
dd=eq/hwm-1
# find worst DD periods
# simple: find troughs where dd < -10%
troughs=dd[dd<-0.08]
print(f"MaxDD {dd.min()*100:.1f}% at {dd.idxmin().date()} eq {eq.loc[dd.idxmin()]:.3f} hwm {hwm.loc[dd.idxmin()]:.3f}")
# find start of that DD (last hwm before trough)
trough=dd.idxmin()
hwm_before=hwm.loc[:trough]
peak=hwm_before[hwm_before==hwm_before.max()].index[-1]
print(f"Peak {peak.date()} trough {trough.date()} days {(trough-peak).days} return {(eq.loc[trough]/eq.loc[peak]-1)*100:.1f}%")
# second worst
dd2=dd.copy()
# mask first episode
dd2.loc[peak:trough]=0
print(f"Second trough {dd2.idxmin().date()} DD {dd2.min()*100:.1f}%")

print("\n=== Rolling 3y Sharpe HALF OOS ===")
roll=best_oos.rolling(252*3).apply(lambda x: x.mean()/x.std()*np.sqrt(252) if x.std()!=0 else np.nan)
for y in [2010,2013,2015,2019,2020,2023]:
    vals=roll.loc[str(y)]
    if len(vals)>0:
        print(f"{y} 3y Sharpe {vals.iloc[-1]:+.2f} (mean {vals.mean():+.2f})")

print("\n=== Payoff concentration HALF ===")
top5=best_oos.nlargest(5)
print(f"Top5 {top5.sum()*100:+.1f}% of total {best_oos.sum()*100:+.1f}% = {top5.sum()/best_oos.sum()*100:.1f}% (raw 32.3%, V2 30%)")
print(f"Top20 share {best_oos.nlargest(20).sum()/best_oos.sum()*100:.1f}%")
print(f"Worst5 {best_oos.nsmallest(5).sum()*100:+.1f}%")

print("\n=== Per-factor OOS raw (no overlay) ===")
for f in ["crack_321","cross_sectional","bzwti"]:
    s=net[f].loc[OOS_START:IS_START].iloc[WARMUP:]
    print(f"{f:16s} Sharpe {stats(s)['sharpe']:.2f} CAGR {stats(s)['cagr']*100:.1f}% DD {stats(s)['maxdd']*100:.1f}% vol{stats(s)['vol']*100:.1f}% daysOn {(net[f].loc[OOS_START:IS_START].iloc[WARMUP:].abs()>0).mean()*100:.1f}% worst {s.min()*100:.2f}%")

print("\n=== Correlations OOS raw ===")
print(net.loc[OOS_START:IS_START].iloc[WARMUP:][["crack_321","cross_sectional","bzwti"]].corr().round(2).to_string())

print("\n=== Gap risk: worst day raw vs half ===")
print(f"Raw worst {raw_oos.min()*100:.2f}% on {raw_oos.idxmin().date()} -> half {best_oos.loc[raw_oos.idxmin()]*100:.2f}%")
print(f"Half worst {best_oos.min()*100:.2f}% on {best_oos.idxmin().date()} raw {raw_oos.loc[best_oos.idxmin()]*100:.2f}%")

print("\n=== Trade frequency HALF ===")
# Count entries per factor (pos 0->>0)
for f in ["crack_321","cross_sectional","bzwti"]:
    pos=factors[f].loc[OOS_START:IS_START].iloc[WARMUP:]
    entries=((pos.shift(1)==0)&(pos!=0)).sum()
    print(f"{f:16s} entries OOS {entries} (~{entries/16:.1f}/yr) daysOn {(pos.abs()>0).mean()*100:.1f}%")

print("\n=== Roll and cost deltas ===")
# Need engine_v2 deltas already known: stub vs proxy +0.04bps/yr net zero
# Just report gap cap would-be
caps=[None,0.08,0.05]
for cap in caps:
    if cap is None:
        lbl="NOCAP"
        f2,_ ,_,_ = b5.build_v5(levels,None,False)
    else:
        lbl=f"CAP{int(cap*100)}"
        f2,_ ,_,_ = b5.build_v5(levels,cap,False)
    net2=b5.apply_costs(f2, {k: f2[k].shift(1).fillna(0.0)*levels[k].diff()/b5.b4.base_of(levels[k]).shift(1).replace(0.0,np.nan) if k in levels else pd.Series(0,index=f2[k].index) for k in f2}, turnover={k:f2[k].diff().abs() for k in f2})
    # actually use b5 rets
    # simplify: use raw_book from net2? skip detailed, just report worst
    w2=b5.weight_scheme(net2.loc[IS_START:].iloc[WARMUP:][["crack_321","cross_sectional","bzwti"]],"EQ")
    raw2=b5.book_returns(net2, ["crack_321","cross_sectional","bzwti"], w2)
    ro2=window(raw2,OOS_START,IS_START)
    bo2=half_overlay(ro2, joint.reindex(ro2.index).fillna(False))
    print(f"{lbl:6s} HALF OOS Sharpe {stats(bo2)['sharpe']:.2f} DD {stats(bo2)['maxdd']*100:.1f}% worst {stats(bo2)['worst']*100:.2f}%")
