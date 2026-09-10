import importlib.util
from pathlib import Path
import pandas as pd, numpy as np
DEV=Path("/home/sebas/algoterminal-strategy-dev")
spec=importlib.util.spec_from_file_location("b5", str(DEV/"book_oos_v5.py"))
b5=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b5)
spec3=importlib.util.spec_from_file_location("fb", str(DEV/"factor_book.py"))
fb=importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)
df=pd.read_parquet(b5.PANEL).sort_index()
levels=fb.build_levels(df)
levels["__df__"]=df
factors,rets,turn,legpos=b5.build_v5(levels,None,False)
net=b5.apply_costs(factors,rets,turnover=turn)
isw=b5.window(net,b5.IS_START,df.index.max())
oos=b5.window(net,b5.OOS_START,b5.IS_START)
zdf={}
for leg in ["crack_321","crack_gas","crack_ho","ng","bzwti"]:
    zdf[leg]=fb.seasonal_z(levels[leg])
for leg in ["brent321","brent_gas","brent_ho"]:
    zdf[leg]=fb.seasonal_z(b5.brent_levels(df)[leg])
depth=b5.book_depth(legpos,zdf,net.index)
w=b5.weight_scheme(isw[b5.SUBSETS["CORE3"]],"EQ")
book=b5.book_returns(net,b5.SUBSETS["CORE3"],w)
b_oos=book.loc[oos.index]
b_is=book.loc[isw.index]
held=depth.shift(1)
crash5=depth.shift(6)-depth.shift(1)
crude20=df.CL.pct_change(20).shift(1)
def apply_overlay_v4(book_, vstate):
    rv=book_.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
    gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
    g=gear.shift(1).fillna(1.0)
    n=len(book_)
    scale=np.empty(n)
    state=1.0
    eq,hwm=1.0,1.0
    eng_eq,eng_hwm=1.0,1.0
    vv=vstate.reindex(book_.index).fillna(False).to_numpy(dtype=bool)
    for t in range(n):
        scale[t]=state
        r=float(book_.iloc[t])
        ret=r*float(g.iloc[t])*scale[t]
        eq*=1.0+ret
        hwm=max(hwm,eq)
        exp_dd=eq/hwm-1.0 if hwm>0 else 0.0
        eng_eq*=1.0+r
        was_hwm=eng_hwm
        eng_hwm=max(eng_hwm,eng_eq)
        new_high=eng_eq>=was_hwm
        if vv[t]:
            state=1.0
        elif state==1.0:
            if exp_dd<=-0.10: state=0.0
            elif exp_dd<=-0.06: state=0.5
        elif state==0.5:
            if exp_dd<=-0.10: state=0.0
            elif new_high: state=1.0
        else:
            if new_high: state=1.0
    return book_*pd.Series(scale,index=book_.index)*g
def stats(r):
    r=r.dropna()
    eq=(1+r).cumprod()
    years=len(r)/252
    return {"cagr":eq.iloc[-1]**(1/years)-1,"sharpe":r.mean()/r.std()*np.sqrt(252),"maxdd":(eq/eq.cummax()-1).min(),"worst":r.min(),"vol":r.std()*np.sqrt(252)}
def v_joint(idx, cthr=1.0, crthr=-0.15, dthr=-1.25):
    h=held.reindex(idx); c=crash5.reindex(idx); cr=crude20.reindex(idx)
    return (c>=cthr)&(cr<=crthr)&(h<=dthr)
for cthr,crthr,dthr in [(1.0,-0.15,-1.25),(1.2,-0.15,-1.5)]:
    for label, b in [("OOS", b_oos), ("IS", b_is)]:
        v=v_joint(b.index,cthr,crthr,dthr)
        g=pd.DataFrame({"ret":b,"v":v})
        print(f"{label} joint c>={cthr} cr<={crthr} d<={dthr} n={int(v.sum())}/{len(v)} meanV {g.ret[v].mean()*100:+.3f}% vs {g.ret[~v].mean()*100:+.3f}%")
for cthr,crthr,dthr in [(1.0,-0.15,-1.25)]:
    v_oos=v_joint(b_oos.index,cthr,crthr,dthr)
    v_is=v_joint(b_is.index,cthr,crthr,dthr)
    vo=apply_overlay_v4(b_oos, v_oos)
    vi=apply_overlay_v4(b_is, v_is)
    v2oos=b5.apply_overlay_v2(b_oos)
    v2is=b5.apply_overlay_v2(b_is)
    print("JOINT 1.0/-0.15/-1.25 overlay IS", stats(vi))
    print("JOINT OOS", stats(vo))
    print("V2 IS", stats(v2is), "OOS", stats(v2oos))
    raw_y=b_oos.groupby(b_oos.index.year).sum()
    v2_y=v2oos.groupby(v2oos.index.year).sum()
    vj_y=vo.groupby(vo.index.year).sum()
    for y in sorted(set(b_oos.index.year)):
        if y in raw_y:
            print(f"{y} raw {raw_y.loc[y]*100:+6.1f}% v2 {v2_y.loc[y]*100:+6.1f}% joint {vj_y.loc[y]*100:+6.1f}%")
