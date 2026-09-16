"""Weather as windfall holder with joint crisis filter."""
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
    if len(r)==0 or r.std()==0:
        return {"sharpe":np.nan,"cagr":np.nan,"maxdd":np.nan,"worst":np.nan,"vol":np.nan}
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
zdf={k:fb.seasonal_z(levels[k]) for k in ["crack_321","crack_gas","crack_ho","ng","bzwti"]}
for k in ["brent321","brent_gas","brent_ho"]: zdf[k]=fb.seasonal_z(bl[k])
depth=b5.book_depth(legpos,zdf,pd.Index(df.index))
held=depth.shift(1)
crash5=depth.shift(6)-depth.shift(1)
crude20=df.CL.pct_change(20).shift(1)
joint=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
joint=joint.fillna(False)

# load weather: try nasa-power provider cache, else try tmp csv
def load_weather_z():
    # try algoterminal-data provider cache for Houston T2M
    # provider stores parquet under ~/.algoterminal-data/cache/nasa-power__*.parquet ?
    # fallback: try /tmp/weather_NYC.csv and build HDD z
    # We'll try to use existing weather_gate logic: it used provider to fetch Houston/Rotterdam T2M
    # For now, try to load any existing parquet
    import glob
    candidates=glob.glob(str(Path.home()/".algoterminal-data/cache/nasa-power*")) + glob.glob("/tmp/weather*.csv") + glob.glob("/tmp/nasa*.parquet")
    print("weather candidates:", candidates[:5])
    # try to load via provider directly if available
    try:
        from importlib import import_module
        import sys
        sys.path.insert(0, str(Path("/home/sebas/algoterminal-data/src")))
        # try to import provider
        try:
            from algoterminal_data._providers.nasa_power import fetch_nasa_power
            # fetch not needed, try to load from cache
        except Exception as e:
            print("nasa provider import fail:", e)
    except Exception as e:
        print("sys path fail", e)
    # fallback: if we have NYC csv, build HDD z from it as proxy (NYC is good for gas)
    p="/tmp/weather_NYC.csv"
    if Path(p).exists():
        w=pd.read_csv(p, index_col=0, parse_dates=True)
        # w has temp column?
        print("NYC cols", w.columns.tolist()[:5], w.head(2).to_string()[:200])
        # try to find T2M
        col=None
        for c in w.columns:
            if "temp" in c.lower() or "t2m" in c.lower():
                col=c
                break
        if col is None:
            col=w.columns[0]
        s=w[col].dropna()
        s.index=pd.to_datetime(s.index)
        # HDD = 18 - T, clipped
        hdd=(18 - s).clip(lower=0)
        # same-month expanding z, causal lag 1
        z=pd.Series(np.nan, index=hdd.index)
        for m in range(1,13):
            idx=hdd.index[hdd.index.month==m]
            for i in range(len(idx)):
                t=idx[i]
                past=hdd.loc[:t-pd.Timedelta(days=1)]
                past=past[past.index.month==m].dropna()
                if len(past)>=30:
                    mu,sd=past.mean(),past.std()
                    if sd>1e-9:
                        z.loc[t]=(hdd.loc[t]-mu)/sd
        z=z.clip(-8,8)
        # daily ffill to df index
        z=z.sort_index().reindex(df.index.union(z.index)).sort_index().ffill().reindex(df.index)
        return z
    # try houston
    for p in ["/tmp/weather_Houston.csv","/tmp/weather_Rotterdam.csv"]:
        if Path(p).exists():
            w=pd.read_csv(p, index_col=0, parse_dates=True)
            col=w.columns[0]
            s=w[col].dropna()
            s.index=pd.to_datetime(s.index)
            hdd=(18 - s).clip(lower=0)
            z=pd.Series(np.nan, index=hdd.index)
            for m in range(1,13):
                idx=hdd.index[hdd.index.month==m]
                for i in range(len(idx)):
                    t=idx[i]
                    past=hdd.loc[:t-pd.Timedelta(days=1)]
                    past=past[past.index.month==m].dropna()
                    if len(past)>=30:
                        mu,sd=past.mean(),past.std()
                        if sd>1e-9:
                            z.loc[t]=(hdd.loc[t]-mu)/sd
            z=z.clip(-8,8)
            return z.sort_index().reindex(df.index.union(z.index)).sort_index().ffill().reindex(df.index)
    return pd.Series(np.nan, index=df.index)

wz=load_weather_z()
if wz.isna().all():
    print("No weather z found, building synthetic cold proxy from NG price?")
    wz=pd.Series(0.0, index=df.index)
else:
    print(f"Weather z loaded: non-na {(~wz.isna()).sum()}, range {wz.min():.2f}..{wz.max():.2f}")

# weather holder: when joint true, if weather cold (z > 0.5?) keep FULL else HALF
# Test variants: cold threshold 0, 0.5, 1.0
# Also test weather on NG leg only vs whole book

def apply_joint_weather(book, joint_raw, wz_daily, thr=0.5, keep_full_if_cold=True):
    # joint_raw is bool at close t-1 for day t
    # wz_daily is HDD z at close t-1
    rv=book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
    gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
    g=gear.shift(1).fillna(1.0)
    n=len(book)
    scale=np.empty(n)
    state=1.0
    eq,hwm=1.0,1.0
    eng_eq,eng_hwm=1.0,1.0
    jv=joint_raw.reindex(book.index).fillna(False).to_numpy(bool)
    wv=wz_daily.reindex(book.index).fillna(0).to_numpy(float) if wz_daily is not None else np.zeros(n)
    for t in range(n):
        # decide scale for day t
        if jv[t]:
            # in joint crisis window
            if keep_full_if_cold:
                scale[t]=1.0 if wv[t] > thr else 0.5
            else:
                scale[t]=1.0
            state=scale[t]
        else:
            scale[t]=state
        r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
        eq*=1+ret; hwm=max(hwm,eq)
        exp_dd=eq/hwm-1 if hwm>0 else 0
        eng_eq*=1+r; was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq); new_high=eng_eq>=was
        if jv[t]:
            state=scale[t]
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

# Test 1: joint alone full vs half vs weather holder
print("\n=== Joint alone vs weather holder (whole book) ===")
for label, fn in [
    ("V2", lambda b: b5.apply_overlay_v2(b)),
    ("JOINT FULL", lambda b: apply_joint_weather(b, joint.reindex(b.index).fillna(False), wz, thr=999)), # thr high = always half? actually we force full via keep_full_if_cold false? Let's use direct full
]:
    pass

# Direct tests
j_oos=joint.reindex(raw_oos.index).fillna(False)
j_is=joint.reindex(raw_is.index).fillna(False)
# full joint (scale 1.0)
def full_joint(b,j): return apply_joint_weather(b,j,wz.reindex(b.index), thr=999) # but our function with scale logic: when j true, scale 1.0 if wv>thr else 0.5 — thr 999 always 0.5
# So for full we need separate

def apply_full(b,j): 
    rv=b.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
    gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
    g=gear.shift(1).fillna(1.0)
    n=len(b); scale=np.empty(n); state=1.0; eq,hwm=1.0,1.0; eng_eq,eng_hwm=1.0,1.0
    jv=j.reindex(b.index).fillna(False).to_numpy(bool)
    for t in range(n):
        if jv[t]:
            scale[t]=1.0; state=1.0
        else:
            scale[t]=state
        r=float(b.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
        eq*=1+ret; hwm=max(hwm,eq); exp_dd=eq/hwm-1 if hwm>0 else 0
        eng_eq*=1+r; was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq); new_high=eng_eq>=was
        if jv[t]: state=1.0
        else:
            if state==1.0:
                if exp_dd<=-0.10: state=0.0
                elif exp_dd<=-0.06: state=0.5
            elif state==0.5:
                if exp_dd<=-0.10: state=0.0
                elif new_high: state=1.0
            else:
                if new_high: state=1.0
    return b*pd.Series(scale,index=b.index)*g

def apply_half(b,j):
    rv=b.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
    gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
    g=gear.shift(1).fillna(1.0)
    n=len(b); scale=np.empty(n); state=1.0; eq,hwm=1.0,1.0; eng_eq,eng_hwm=1.0,1.0
    jv=j.reindex(b.index).fillna(False).to_numpy(bool)
    for t in range(n):
        if jv[t]:
            scale[t]=0.5; state=0.5
        else:
            scale[t]=state
        r=float(b.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
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
    return b*pd.Series(scale,index=b.index)*g

# weather holder variants
for thr in [0.0, 0.5, 1.0]:
    over_oos=apply_joint_weather(raw_oos, j_oos, wz.reindex(raw_oos.index), thr=thr)
    over_is=apply_joint_weather(raw_is, j_is, wz.reindex(raw_is.index), thr=thr)
    print(f"Weather holder thr {thr:+.1f} (cold>thr keep 1.0 else 0.5) IS {stats(over_is)['sharpe']:.2f} OOS {stats(over_oos)['sharpe']:.2f} DD {stats(over_oos)['maxdd']*100:+.1f}% nJoint {int(j_oos.sum())} cold {(wz.reindex(raw_oos.index).fillna(0) > thr).sum()}%")

# baselines
for label, fn, j in [("V2", b5.apply_overlay_v2, None), ("FULL", apply_full, j_oos), ("HALF", apply_half, j_oos)]:
    if label=="V2":
        print(f"{label:12s} IS {stats(b5.apply_overlay_v2(raw_is))['sharpe']:.2f} OOS {stats(b5.apply_overlay_v2(raw_oos))['sharpe']:.2f} DD {stats(b5.apply_overlay_v2(raw_oos))['maxdd']*100:+.1f}%")
    else:
        over_is=fn(raw_is, j_is) if label!="V2" else None
        over_oos=fn(raw_oos, j_oos)
        print(f"{label:12s} IS {stats(over_is)['sharpe']:.2f} OOS {stats(over_oos)['sharpe']:.2f} DD {stats(over_oos)['maxdd']*100:+.1f}%")

# show yearly for best weather holder vs half
print("\n=== yearly OOS ===")
best_thr=0.5
over_w=apply_joint_weather(raw_oos, j_oos, wz.reindex(raw_oos.index), thr=best_thr)
over_half=apply_half(raw_oos, j_oos)
over_full=apply_full(raw_oos, j_oos)
v2=b5.apply_overlay_v2(raw_oos)
for y in sorted(set(raw_oos.index.year)):
    print(f"{y} v2 {v2[v2.index.year==y].sum()*100:+5.1f}% half {over_half[over_half.index.year==y].sum()*100:+5.1f}% weather{best_thr} {over_w[over_w.index.year==y].sum()*100:+5.1f}% full {over_full[over_full.index.year==y].sum()*100:+5.1f}%")

# also check correlation of weather with joint days returns
j_days=raw_oos[j_oos]
cold=wz.reindex(raw_oos.index).fillna(0) > 0.5
print(f"\nJoint days mean {j_days.mean()*100:+.3f}% cold joint {(raw_oos[j_oos & (wz.reindex(raw_oos.index).fillna(0)>0.5)]).mean()*100:+.3f}% warm joint {(raw_oos[j_oos & (wz.reindex(raw_oos.index).fillna(0)<=0.5)]).mean()*100:+.3f}%")
print(f"Weather z on joint days mean {wz.reindex(raw_oos.index)[j_oos].mean():+.2f} vs all {wz.reindex(raw_oos.index).mean():+.2f}")
