"""Book v7 — joint crisis discriminator overlay (Round 9).

Pre-registered primary hypothesis for the inflection test was:
  V-shape = deepening 10->5 then shallowing 5->0 into deep valley.
Diagnostics in diag_inflection.py FALSIFIED this before engine:
  all V-shape cells mean -0.08% to -0.15% vs grind +0.05% (OOS held).
  The shallowing leg loses; the inflection loses. Not built as overlay.

The diagnostic sweep then surfaced the joint filter, now tested here:

  JOINT = crash5 >= THR_CRASH and depth <= THR_DEPTH and crude20 <= THR_CRUDE
  where crash5 = depth(t-6)-depth(t-1) (positive = fast deepening),
        depth = held leg z at t-1, crude20 = CL 20d return ending t-1.

This isolates the crisis entry: a fast crush deepening into deep
territory WHILE crude is crashing. Descriptive: OOS held mean +0.89%
vs +0.04% grind (n=32), IS n=0 (no crude crash in 2023-26, so IS intact).
Pre-registered thresholds (round, a priori): 1.0/-1.25/-0.15 primary,
with 1.2/-1.5/-0.15 and 0.8/-1.25/-0.15 as grid.

Overlay: same v2 ladder, but JOINT forces FULL at day t (causal).
"""

from __future__ import annotations
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = (Path("/tmp/panel_adj_2007_2026.parquet")
         if Path("/tmp/panel_adj_2007_2026.parquet").exists()
         else Path(__file__).resolve().parent / "panel_v2.parquet")
IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90

spec = importlib.util.spec_from_file_location("b5", str(DEV / "book_oos_v5.py"))
b5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b5)
spec3 = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(fb)

SUBSETS = {"CORE3": ["crack_321", "cross_sectional", "bzwti"]}

def joint_signal(depth, crash5, crude20, thr_crash=1.0, thr_depth=-1.25, thr_crude=-0.15):
    return (crash5 >= thr_crash) & (depth <= thr_depth) & (crude20 <= thr_crude)

def apply_overlay_joint(book, vstate, vol_target=0.10, cut=-0.06, halt=-0.10):
    rv = book.rolling(20, min_periods=10).std().shift(1)*np.sqrt(252)
    gear = (vol_target/rv.replace(0.0, np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
    n=len(book)
    scale=np.empty(n)
    state=1.0
    eq,hwm=1.0,1.0
    eng_eq,eng_hwm=1.0,1.0
    vv=vstate.reindex(book.index).fillna(False).to_numpy(dtype=bool)
    for t in range(n):
        scale[t]=state
        r=float(book.iloc[t])
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
            if exp_dd <= halt: state=0.0
            elif exp_dd <= cut: state=0.5
        elif state==0.5:
            if exp_dd <= halt: state=0.0
            elif new_high: state=1.0
        else:
            if new_high: state=1.0
    return book*pd.Series(scale,index=book.index)*g

def stats(r):
    r=r.dropna()
    if len(r)==0 or r.std()==0:
        return {"cagr":np.nan,"sharpe":np.nan,"maxdd":np.nan,"worst":np.nan,"vol":np.nan}
    eq=(1+r).cumprod()
    years=len(r)/252
    return {"cagr":eq.iloc[-1]**(1/years)-1,"sharpe":r.mean()/r.std()*np.sqrt(252),"maxdd":(eq/eq.cummax()-1).min(),"worst":r.min(),"vol":r.std()*np.sqrt(252)}

def window(r,start,end):
    out=r.loc[start:end]
    return out.iloc[WARMUP:] if len(out)>WARMUP else out

def main():
    df=pd.read_parquet(PANEL).sort_index()
    levels=fb.build_levels(df)
    levels["__df__"]=df
    factors,rets,turn,legpos=b5.build_v5(levels,None,False)
    net=b5.apply_costs(factors,rets,turnover=turn)
    isw=window(net, IS_START, df.index.max())
    oos=window(net, OOS_START, IS_START)
    zdf={}
    for leg in ["crack_321","crack_gas","crack_ho","ng","bzwti"]:
        zdf[leg]=fb.seasonal_z(levels[leg])
    for leg in ["brent321","brent_gas","brent_ho"]:
        zdf[leg]=fb.seasonal_z(b5.brent_levels(df)[leg])
    depth=b5.book_depth(legpos,zdf,net.index)
    w=b5.weight_scheme(isw[SUBSETS["CORE3"]],"EQ")
    book=b5.book_returns(net,SUBSETS["CORE3"],w)
    b_is, b_oos = book.loc[isw.index], book.loc[oos.index]
    # causal features
    held=depth.shift(1)
    crash5=depth.shift(6)-depth.shift(1)
    crude20=df.CL.pct_change(20).shift(1)
    print("Window:", df.index.min().date(), "->", df.index.max().date(), "rows", len(df))
    v2_is=b5.apply_overlay_v2(b_is)
    v2_oos=b5.apply_overlay_v2(b_oos)
    print(f"V2 champ: IS {stats(v2_is)['sharpe']:.2f} DD {stats(v2_is)['maxdd']*100:+.1f}% | OOS {stats(v2_oos)['sharpe']:.2f} DD {stats(v2_oos)['maxdd']*100:+.1f}% CAGR {stats(v2_oos)['cagr']*100:.2f}% vol {stats(v2_oos)['vol']*100:.1f}%")
    # descriptive of joint before engine
    sf_oos=pd.DataFrame({"ret":b_oos,"held":held.reindex(b_oos.index),"crash5":crash5.reindex(b_oos.index),"crude20":crude20.reindex(b_oos.index)})
    mask=sf_oos.held.notna()&sf_oos.crash5.notna()&sf_oos.crude20.notna()
    g=sf_oos[mask]
    print("\n=== joint descriptive (OOS held) ===")
    for cthr,crthr,dthr in [(1.0,-0.15,-1.25),(1.2,-0.15,-1.5),(0.8,-0.15,-1.25)]:
        v=(g.crash5>=cthr)&(g.crude20<=crthr)&(g.held<=dthr)
        print(f" c>={cthr} cr<={crthr} d<={dthr} n={int(v.sum())} meanV {g.ret[v].mean()*100:+.3f}% vs {g.ret[~v].mean()*100:+.3f}% totalV {g.ret[v].sum()*100:+.2f}%")

    print("\n=== JOINT overlay grid ===")
    print(f" {'variant':<22} | {'IS_Sh':>5} {'IS_DD':>7} | {'OOS_Sh':>6} {'OOS_CAGR':>8} {'OOS_DD':>7} {'OOS_vol':>7} {'worst':>6} | top5")
    rows=[]
    for cthr,crthr,dthr in [(1.0,-0.15,-1.25),(1.2,-0.15,-1.5),(0.8,-0.15,-1.25),(1.0,-0.10,-1.25)]:
        h=held; c=crash5; cr=crude20
        v_oos=joint_signal(h, c, cr, cthr, dthr, crthr)
        v_is=joint_signal(h, c, cr, cthr, dthr, crthr)
        jo=apply_overlay_joint(b_oos, v_oos)
        ji=apply_overlay_joint(b_is, v_is)
        si,so=stats(ji),stats(jo)
        top5_raw=b_oos.nlargest(5).sum()
        top5_jo=jo.loc[b_oos.nlargest(5).index].sum()
        rows.append((cthr,crthr,dthr,si,so,top5_jo/top5_raw*100 if top5_raw else 0))
        print(f" c{cthr:.1f} cr{crthr:+.2f} d{dthr:.2f} | {si['sharpe']:5.2f} {si['maxdd']*100:7.1f}% | {so['sharpe']:6.2f} {so['cagr']*100:8.2f}% {so['maxdd']*100:7.1f}% {so['vol']*100:7.1f}% {so['worst']*100:6.2f}% | {top5_jo/top5_raw*100:4.1f}%")

    # best variant yearly
    cthr,crthr,dthr = 1.0,-0.15,-1.25
    v_oos=joint_signal(held,crash5,crude20,cthr,dthr,crthr)
    jo=apply_overlay_joint(b_oos, v_oos)
    print("\n=== joint 1.0/-0.15/-1.25 yearly OOS: raw | V2 | JOINT ===")
    raw_y=b_oos.groupby(b_oos.index.year).sum()
    v2_y=v2_oos.groupby(v2_oos.index.year).sum()
    jo_y=jo.groupby(jo.index.year).sum()
    for y in sorted(set(b_oos.index.year)):
        if y in raw_y:
            print(f" {y} {raw_y.loc[y]*100:+6.1f}% {v2_y.loc[y]*100:+6.1f}% {jo_y.loc[y]*100:+6.1f}%")
    print("\n=== joint worst days OOS ===")
    for idx,val in jo.nsmallest(5).items():
        print(f" {idx.date()} {val*100:+6.2f}% raw {b_oos.loc[idx]*100:+6.2f}% v2 {v2_oos.loc[idx]*100:+6.2f}%")

    # negative control: shuffle joint labels
    print("\n=== negative control: shuffle joint (30 draws) OOS Sharpe ===")
    import numpy as np
    rng=np.random.default_rng(7)
    sh=[]
    vb=v_oos.reindex(b_oos.index).fillna(False).to_numpy(bool)
    for _ in range(30):
        perm=rng.permutation(len(vb))
        sv=pd.Series(vb[perm], index=b_oos.index)
        sh.append(stats(apply_overlay_joint(b_oos, sv))["sharpe"])
    print(f" shuffled mean {np.mean(sh):.2f} sd {np.std(sh):.2f} (real joint {stats(jo)['sharpe']:.2f}, V2 {stats(v2_oos)['sharpe']:.2f}, raw {stats(b_oos)['sharpe']:.2f})")

    # persist
    pd.DataFrame({"date":b_oos.index,"raw":b_oos,"v2":v2_oos,"joint":jo}).to_csv(DEV/"book_oos_v7_results.csv", index=False)
    print("\nSaved book_oos_v7_results.csv")

if __name__=="__main__":
    main()
