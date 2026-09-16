"""Next gaps: joint 0.5 re-cock and tighter crude windows."""
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
    if len(r)==0 or r.std()==0:
        return {"cagr":np.nan,"sharpe":np.nan,"maxdd":np.nan,"worst":np.nan,"vol":np.nan}
    eq=(1+r).cumprod(); years=len(r)/252
    return {"cagr":eq.iloc[-1]**(1/years)-1,"sharpe":r.mean()/r.std()*np.sqrt(252),"maxdd":(eq/eq.cummax()-1).min(),"worst":r.min(),"vol":r.std()*np.sqrt(252)}
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
oos=net.loc[OOS_START:IS_START].iloc[WARMUP:]
w=b5.weight_scheme(isw[["crack_321","cross_sectional","bzwti"]],"EQ")
raw_book=b5.book_returns(net, ["crack_321","cross_sectional","bzwti"], w)
raw_is=window(raw_book,IS_START,df.index.max())
raw_oos=window(raw_book,OOS_START,IS_START)
# depth/crash/crude
zdf={k:fb.seasonal_z(levels[k]) for k in ["crack_321","crack_gas","crack_ho","ng","bzwti"]}
for k in ["brent321","brent_gas","brent_ho"]: zdf[k]=fb.seasonal_z(bl[k])
depth=b5.book_depth(legpos,zdf,pd.Index(df.index))
held=depth.shift(1)
crash5=depth.shift(6)-depth.shift(1)
crude20=df.CL.pct_change(20).shift(1)
crude10=df.CL.pct_change(10).shift(1)
# crude vol-adjusted stress: crude10 / trailing vol
crude_ret10=df.CL.pct_change(10)
vol10=crude_ret10.rolling(20).std().shift(1)
crude_voladj=(crude10.shift(1)/vol10.replace(0,np.nan)).fillna(0)

def apply_joint_scale(book, joint_raw, scale_joint=1.0, prob_n=None, vol_target=0.10, cut=-0.06, halt=-0.10):
    rv=book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
    gear=(vol_target/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
    g=gear.shift(1).fillna(1.0)
    n=len(book)
    scale=np.empty(n)
    state=1.0
    eq,hwm=1.0,1.0
    eng_eq,eng_hwm=1.0,1.0
    if joint_raw is None:
        jv=np.zeros(n,bool)
    else:
        jv=joint_raw.reindex(book.index).fillna(False).to_numpy(bool)
    timer=0
    for t in range(n):
        if joint_raw is not None and jv[t] and prob_n is not None:
            timer=prob_n
        if prob_n is not None and timer>0:
            scale[t]=scale_joint
            timer-=1
            r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
            eq*=1+ret; hwm=max(hwm,eq); eng_eq*=1+r; eng_hwm=max(eng_hwm,eng_eq); state=scale_joint if scale_joint==1.0 else 1.0
            continue
        if joint_raw is not None and prob_n is None and jv[t]:
            scale[t]=scale_joint
            state=scale_joint
        else:
            scale[t]=state
        r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
        eq*=1+ret; hwm=max(hwm,eq)
        exp_dd=eq/hwm-1 if hwm>0 else 0
        eng_eq*=1+r; was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq); new_high=eng_eq>=was
        if joint_raw is not None and prob_n is None and jv[t]:
            state=scale_joint
        else:
            if state==1.0:
                if exp_dd<=halt: state=0.0
                elif exp_dd<=cut: state=0.5
            elif state==0.5:
                if exp_dd<=halt: state=0.0
                elif new_high: state=1.0
            else:
                if new_high: state=1.0
    return book*pd.Series(scale,index=book.index)*g

print("=== 1) Joint 0.5 re-cock vs FULL (20d crude, depth -1.25 crash 1.0) ===")
for sc, pn, label in [(1.0,None,"FULL book"),(0.5,None,"HALF book"),(1.0,5,"FULL prob5"),(0.5,5,"HALF prob5"),(1.0,10,"FULL prob10"),(0.5,10,"HALF prob10")]:
    j=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
    j=j.fillna(False)
    j_is=j.reindex(raw_is.index).fillna(False)
    j_oos=j.reindex(raw_oos.index).fillna(False)
    over_is=apply_joint_scale(raw_is,j_is,sc,pn)
    over_oos=apply_joint_scale(raw_oos,j_oos,sc,pn)
    si,so=stats(over_is),stats(over_oos)
    print(f"{label:12s} IS {si['sharpe']:.2f} {si['maxdd']*100:+.1f}% | OOS {so['sharpe']:.2f} {so['cagr']*100:.1f}% DD {so['maxdd']*100:+.1f}% vol{so['vol']*100:.1f}% worst{so['worst']*100:.2f}%")

print("\n=== 2) Tighter crude window ===")
for cr, cr_label in [(crude20,"cr20 -15%"),(crude10,"cr10 -10%"),(crude10,"cr10 -15%")]:
    thr=-0.15 if "15" in cr_label else -0.10
    # use appropriate crude series
    if "cr20" in cr_label:
        cr_s=crude20
    else:
        cr_s=crude10
    j=(crash5>=1.0)&(held<=-1.25)&(cr_s<=thr)
    j=j.fillna(False)
    over_oos=apply_joint_scale(raw_oos,j.reindex(raw_oos.index).fillna(False),1.0,None)
    over_is=apply_joint_scale(raw_is,j.reindex(raw_is.index).fillna(False),1.0,None)
    print(f"{cr_label:12s} thr {thr} IS {stats(over_is)['sharpe']:.2f} OOS {stats(over_oos)['sharpe']:.2f} DD {stats(over_oos)['maxdd']*100:+.1f}% nOOS {int(j.loc[OOS_START:IS_START].sum())} nIS {int(j.loc[IS_START:].sum())} worst {stats(over_oos)['worst']*100:.2f}%")

print("\n=== 2b) vol-adjusted crude stress ===")
for thr in [-1.5, -2.0]:
    j=(crash5>=1.0)&(held<=-1.25)&(crude_voladj<=-thr)
    j=j.fillna(False)
    over_oos=apply_joint_scale(raw_oos,j.reindex(raw_oos.index).fillna(False),1.0,None)
    print(f"voladj <=-{thr} nOOS {int(j.loc[OOS_START:IS_START].sum())} OOS Sharpe {stats(over_oos)['sharpe']:.2f} DD {stats(over_oos)['maxdd']*100:+.1f}%")

print("\n=== 3) Brent sleeve with per-complex + joint 0.5 ===")
# Build Brent net quickly via b5
# Use net already has brent legs? b5.build_v5 includes brent via levels; net has brent321/brent_xs
# For per-complex test, use bv apply_overlay_per_complex logic simplified: per-complex V2 with joint half
# Quick: book core3 vs core3bb per-complex half
for subset, overlay, sc in [(["crack_321","cross_sectional","bzwti"],"book",1.0),(["crack_321","cross_sectional","bzwti","brent321","brent_xs"],"per",0.5)]:
    # need net with all factors
    isw2=net.loc[IS_START:].iloc[WARMUP:]
    w2=b5.weight_scheme(isw2[subset],"EQ")
    raw=b5.book_returns(net, subset, w2)
    raw_is2=window(raw,IS_START,df.index.max())
    raw_oos2=window(raw,OOS_START,IS_START)
    j=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
    j=j.fillna(False)
    # per-complex half joint
    # For per-complex, we need per-complex overlay; emulate via bv
    # Use bv apply_overlay_per_complex with scale 0.5 joint
    # Instead directly use book-level half for quick compare
    over_is=apply_joint_scale(raw_is2,j.reindex(raw_is2.index).fillna(False),sc,None)
    over_oos=apply_joint_scale(raw_oos2,j.reindex(raw_oos2.index).fillna(False),sc,None)
    print(f"{subset} {overlay} sc={sc} IS {stats(over_is)['sharpe']:.2f} OOS {stats(over_oos)['sharpe']:.2f} DD {stats(over_oos)['maxdd']*100:+.1f}% vol{stats(over_oos)['vol']*100:.1f}%")

print("\n=== yearly OOS for best half variant ===")
j=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
over_half=apply_joint_scale(raw_oos,j.reindex(raw_oos.index).fillna(False),0.5,None)
over_full=apply_joint_scale(raw_oos,j.reindex(raw_oos.index).fillna(False),1.0,None)
v2=b5.apply_overlay_v2(raw_oos)
for y in sorted(set(raw_oos.index.year)):
    print(f"{y} raw {raw_oos[raw_oos.index.year==y].sum()*100:+5.1f}% v2 {v2[v2.index.year==y].sum()*100:+5.1f}% half {over_half[over_half.index.year==y].sum()*100:+5.1f}% full {over_full[over_full.index.year==y].sum()*100:+5.1f}%")
