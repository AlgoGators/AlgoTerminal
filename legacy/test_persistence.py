"""Windfall persistence: stay more after big up day."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
DEV=Path("/home/sebas/algoterminal-strategy-dev")
spec=importlib.util.spec_from_file_location("b5", str(DEV/"book_oos_v5.py"))
b5=importlib.util.module_from_spec(spec); spec.loader.exec_module(b5)
spec3=importlib.util.spec_from_file_location("fb", str(DEV/"factor_book.py"))
fb=importlib.util.module_from_spec(spec3); spec3.loader.exec_module(fb)
PANEL=b5.PANEL
IS_START=pd.Timestamp("2023-09-08")
OOS_START=pd.Timestamp("2007-07-30")
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

# persistence signal: big up day in raw book
# Use raw return >2% or 5-day >5%
raw_oos_shifted=raw_oos.shift(1)  # yesterday's raw return known at close
big2 = (raw_oos_shifted > 0.02)
big5 = (raw_oos.rolling(5).sum().shift(1) > 0.05)

def apply_with_persistence(book, joint_raw, persist_raw, scale_joint=0.5, persist_scale=1.0, persist_n=5):
    rv=book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
    gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
    g=gear.shift(1).fillna(1.0)
    n=len(book)
    scale=np.empty(n)
    state=1.0
    eq,hwm=1.0,1.0
    eng_eq,eng_hwm=1.0,1.0
    jv=joint_raw.reindex(book.index).fillna(False).to_numpy(bool) if joint_raw is not None else np.zeros(n,bool)
    pv=persist_raw.reindex(book.index).fillna(False).to_numpy(bool) if persist_raw is not None else np.zeros(n,bool)
    persist_timer=0
    for t in range(n):
        # persistence trigger: if yesterday was big, set timer
        if pv[t]:
            persist_timer=persist_n
        if jv[t]:
            scale[t]=scale_joint
            state=scale_joint
            persist_timer=0  # joint overrides
        elif persist_timer>0:
            scale[t]=persist_scale
            persist_timer-=1
            state=persist_scale
        else:
            scale[t]=state
        r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
        eq*=1+ret; hwm=max(hwm,eq); exp_dd=eq/hwm-1 if hwm>0 else 0
        eng_eq*=1+r; was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq); new_high=eng_eq>=was
        if jv[t]:
            state=scale_joint
            persist_timer=0
        elif persist_timer>0:
            state=persist_scale
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

print("=== Persistence after big up ===")
for label, persist, pn, sc in [
    ("V2", None, None, None),
    ("HALF joint", joint.reindex(raw_oos.index).fillna(False), None, 0.5),
    ("persist big2>2% 5d full", big2, 5, 1.0),
    ("persist big2 5d half", big2, 5, 0.5),
    ("persist big5>5% 5d half", big5, 5, 0.5),
    ("joint half + big2 persist half", joint.reindex(raw_oos.index).fillna(False), 5, 0.5),
]:
    # for joint half + persist, we need joint logic; for pure persist, joint none
    if "joint" in label.lower():
        # use joint half
        over_is=apply_with_persistence(raw_is, joint.reindex(raw_is.index).fillna(False), None, 0.5, 0.5, 5) if "persist" not in label else apply_with_persistence(raw_is, joint.reindex(raw_is.index).fillna(False), big2.reindex(raw_is.index).fillna(False) if "big2" in label else big5.reindex(raw_is.index).fillna(False), 0.5, 0.5, 5)
        over_oos=apply_with_persistence(raw_oos, joint.reindex(raw_oos.index).fillna(False), None, 0.5, 0.5, 5) if "persist" not in label else apply_with_persistence(raw_oos, joint.reindex(raw_oos.index).fillna(False), big2, 0.5, 0.5, 5)
    elif "persist" in label:
        pr=big2 if "big2" in label else big5
        over_is=apply_with_persistence(raw_is, None, pr.reindex(raw_is.index).fillna(False), 1.0, sc, pn)
        over_oos=apply_with_persistence(raw_oos, None, pr, 1.0, sc, pn)
    else:
        over_is=b5.apply_overlay_v2(raw_is)
        over_oos=b5.apply_overlay_v2(raw_oos)
    print(f"{label:28s} IS {stats(over_is)['sharpe']:.2f} OOS {stats(over_oos)['sharpe']:.2f} DD {stats(over_oos)['maxdd']*100:+.1f}% CAGR {stats(over_oos)['cagr']*100:.1f}% worst {stats(over_oos)['worst']*100:.2f}% nBig {(persist.sum() if persist is not None else 0)}")

# direct: persistence alone vs joint half
print("\n=== yearly OOS ===")
over_half=apply_with_persistence(raw_oos, joint.reindex(raw_oos.index).fillna(False), None, 0.5, 0.5, 5)
over_persist=apply_with_persistence(raw_oos, None, big2, 1.0, 1.0, 5)
over_both=apply_with_persistence(raw_oos, joint.reindex(raw_oos.index).fillna(False), big2, 0.5, 1.0, 5)
v2=b5.apply_overlay_v2(raw_oos)
for y in sorted(set(raw_oos.index.year)):
    print(f"{y} v2 {v2[v2.index.year==y].sum()*100:+5.1f}% half {over_half[over_half.index.year==y].sum()*100:+5.1f}% persist {over_persist[over_persist.index.year==y].sum()*100:+5.1f}% both {over_both[over_both.index.year==y].sum()*100:+5.1f}% raw {raw_oos[raw_oos.index.year==y].sum()*100:+5.1f}%")

# check persistence hit rate: after big up, next day mean?
print(f"\nAfter big2>2% next day mean {raw_oos[big2].mean()*100:+.3f}% vs all {raw_oos.mean()*100:+.3f}% n={int(big2.sum())}")
print(f"After big5>5% next day mean {raw_oos[big5].mean()*100:+.3f}% n={int(big5.sum())}")
