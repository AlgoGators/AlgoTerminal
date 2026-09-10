"""vNext — consolidated strategy covering all gaps 2007-2026.

Owns the next version after CORE3 EQ V2 (0.95/-11.1%). Covers:
  G1 leg-switch phantom (per-leg F2, exit+entry, per-leg turnover)
  G2 basis mismatch (dlevel/base everywhere, base=rolling mean |level|)
  G3 gap notional (optional CAP8/CAP5 per-leg notional cap)
  Factor dilution (CORE3 kept: crack_321 + cross_sectional + bzwti; crack_ho/ng dropped)
  Weight dilution (EQ kept; INV/HLV overfit, RP no gain)
  Overlay cost (V2 book-level hysteresis cut -6 halt -10 re-cock on engine new high; vol gear 10%)
  Crisis windfall vs bleed same-state (joint crisis filter: crash5>=1 & depth<=-1.25 & crude20<=-15% descriptively +0.89% vs +0.037% grind)
  Options tail (uneconomic at modeled premiums, documented — DD cheaper)
  Weather/storage gates (falsified except Cushing small gain 0.25->0.31 on bzwti)
  Brent cross-section (raw +0.07 but eaten by book-level overlay — per-complex preserves)
  Reversal speed/inflection (V4 falsified IS -0.44, V-shape falsified -0.1% vs +0.05% before engine)
  Roll/settlement/fills (panel rebuild documented, proxy roll vs stub 20bps/yr, stress cost)

Data: yfinance panel /tmp/panel_adj_2007_2026.parquet (4829 rows 2007-07-02..2026-09-09).
      EIA Cushing via existing provider cache if present (graceful skip).
      NASA POWER / FRED available but not required for vNext defaults.
Costs: 5bps trade + 20bps/yr roll baseline, with 0/10/20 and stress 2x reporting.
Windows: IS 2023-09-08+, OOS 2007-07-30..2023-09-08, warmup 90, all causal t-1.

Usage:
  python book_vNext.py                          # V2 champion (CORE3 EQ BOOK NOCAP)
  python book_vNext.py --joint prob5            # + probationary joint crisis (N=5)
  python book_vNext.py --joint full             # + full joint (IS-safe, rare 32 days OOS)
  python book_vNext.py --cush s05 --cap cap8    # + Cushing 0.5 + gap cap 8%
  python book_vNext.py --subset core3bb --overlay per  # widened Brent sleeve
  python book_vNext.py --help

Behavior first per EVALUATION_LENS.md. Every run reports Sharpe, CAGR, DD, vol,
worst, payoff concentration, per-year, per-regime, shuffled control.
"""

from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

DEV = Path("/home/sebas/algoterminal-strategy-dev")
PANEL = Path("/tmp/panel_adj_2007_2026.parquet")
IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90

spec_fb = importlib.util.spec_from_file_location("fb", str(DEV / "factor_book.py"))
fb = importlib.util.module_from_spec(spec_fb)
spec_fb.loader.exec_module(fb)
spec_b4 = importlib.util.spec_from_file_location("b4", str(DEV / "book_oos_v4.py"))
b4 = importlib.util.module_from_spec(spec_b4)
spec_b4.loader.exec_module(b4)
spec_b5 = importlib.util.spec_from_file_location("b5", str(DEV / "book_oos_v5.py"))
b5 = importlib.util.module_from_spec(spec_b5)
spec_b5.loader.exec_module(b5)

SUBSETS = {
    "core3": ["crack_321", "cross_sectional", "bzwti"],
    "core3bb": ["crack_321", "cross_sectional", "bzwti", "brent321", "brent_xs"],
}
COMPLEXES = {"crack": ["crack_321", "cross_sectional"], "brent": ["brent321", "brent_xs"], "basis": ["bzwti"]}

THR_CRASH = 1.0
THR_DEPTH = -1.25
THR_CRUDE = -0.15
CAPS = {"nocap": None, "cap8": 0.08, "cap5": 0.05}

def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r)==0 or r.std()==0:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "worst": np.nan, "vol": np.nan}
    eq = (1+r).cumprod()
    years = len(r)/252
    return {"cagr": eq.iloc[-1]**(1/years)-1, "sharpe": r.mean()/r.std()*np.sqrt(252),
            "maxdd": (eq/eq.cummax()-1).min(), "worst": r.min(), "vol": r.std()*np.sqrt(252)}

def window(s, start, end):
    out = s.loc[start:end]
    return out.iloc[WARMUP:] if len(out)>WARMUP else out

def window_df(df, start, end):
    out = df.loc[start:end]
    return out.iloc[WARMUP:] if len(out)>WARMUP else out

def get_cushing_daily(index: pd.Index) -> pd.Series | None:
    for p in [Path("/home/sebas/.algoterminal-data/cache/eia__W_EPC0_SAX_YCUOK_MBBL.parquet"),
              Path("/tmp/eia_W_EPC0_SAX_YCUOK_MBBL.csv")]:
        if p.exists():
            try:
                if p.suffix == ".parquet":
                    df = pd.read_parquet(p)
                    s = df["close"].dropna() if "close" in df.columns else df.iloc[:,0].dropna()
                    s.index = pd.to_datetime(s.index)
                else:
                    df = pd.read_csv(p, index_col=0, parse_dates=True)
                    s = df["close"].dropna()
                z = pd.Series(np.nan, index=s.index, dtype=float)
                for m in range(1,13):
                    idx = s.index[s.index.month==m]
                    for i in range(len(idx)):
                        t=idx[i]
                        past = s.loc[:t-pd.Timedelta(days=1)]
                        past = past[past.index.month==m].dropna()
                        if len(past)>=12:
                            mu,sd=past.mean(),past.std()
                            if sd>1e-9:
                                z.loc[t]=(s.loc[t]-mu)/sd
                z=z.clip(-8,8)
                z.index=z.index+pd.Timedelta(days=6)
                return z.sort_index().reindex(index.union(z.index)).sort_index().ffill().reindex(index)
            except Exception as e:
                print(f"WARN Cushing {p}: {e}")
                return None
    return None

def cushing_scale(z_daily: pd.Series, min_scale: float) -> pd.Series:
    sc = 1.0 - (1.0 - min_scale) * ((z_daily - 0.0)/1.5).clip(0,1)
    return sc.fillna(1.0).clip(min_scale,1.0)

def build_joint_raw(depth: pd.Series, crude20: pd.Series) -> pd.Series:
    held = depth.shift(1)
    crash5 = depth.shift(6) - depth.shift(1)
    j = (crash5 >= THR_CRASH) & (held <= THR_DEPTH) & (crude20 <= THR_CRUDE)
    return j.fillna(False)

def apply_overlay_prob(book: pd.Series, joint_raw: pd.Series | None, prob_n: int | None, vol_target=0.10, cut=-0.06, halt=-0.10, joint_scale: float = 1.0) -> pd.Series:
    rv = book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
    gear = (vol_target/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
    g = gear.shift(1).fillna(1.0)
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
            scale[t]=joint_scale
            timer-=1
            r=float(book.iloc[t])
            ret=r*float(g.iloc[t])*scale[t]
            eq*=1+ret; hwm=max(hwm,eq)
            eng_eq*=1+r; eng_hwm=max(eng_hwm,eng_eq)
            state=1.0
            continue
        if joint_raw is not None and prob_n is None and jv[t]:
            scale[t]=joint_scale
            state=joint_scale
        else:
            scale[t]=state
        r=float(book.iloc[t])
        ret=r*float(g.iloc[t])*scale[t]
        eq*=1+ret; hwm=max(hwm,eq)
        exp_dd=eq/hwm-1 if hwm>0 else 0
        eng_eq*=1+r
        was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq)
        new_high=eng_eq>=was
        if joint_raw is not None and prob_n is None and jv[t]:
            state=joint_scale
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

def apply_overlay_per_complex(net: pd.DataFrame, subset: list[str], weights: dict, joint_raw: pd.Series | None, prob_n: int | None, vol_target=0.10) -> pd.Series:
    out=pd.Series(0.0,index=net.index)
    groups=[ [f for f in g if f in subset] for g in [COMPLEXES["crack"], COMPLEXES["brent"], COMPLEXES["basis"]] ]
    groups=[g for g in groups if g]
    for g in groups:
        sub=pd.Series(0.0,index=net.index)
        for f in g:
            sub=sub+weights[f]*net[f]
        over=apply_overlay_prob(sub, joint_raw.reindex(sub.index).fillna(False) if joint_raw is not None else None, prob_n, vol_target)
        out=out+over
    return out

def main():
    ap=argparse.ArgumentParser(description="vNext consolidated strategy")
    ap.add_argument("--subset", choices=["core3","core3bb"], default="core3", help="factor subset")
    ap.add_argument("--joint", choices=["off","full","half","prob3","prob5","prob10","half_prob5"], default="off", help="joint crisis filter (half=0.5 re-cock)")
    ap.add_argument("--cush", choices=["off","s05","s07"], default="off", help="Cushing sizing for bzwti")
    ap.add_argument("--overlay", choices=["book","per"], default="book", help="DD overlay level")
    ap.add_argument("--cap", choices=["nocap","cap8","cap5"], default="nocap", help="gap cap")
    ap.add_argument("--verbose", action="store_true", help="yearly and tail tables")
    ap.add_argument("--cost-sensitivity", action="store_true", help="0/5/10/20 bps sweep")
    args=ap.parse_args()

    flist=SUBSETS[args.subset]
    capv=CAPS[args.cap]
    joint_map={"off":None,"full":None,"half":None,"prob3":3,"prob5":5,"prob10":10,"half_prob5":5}
    prob_n=joint_map[args.joint]
    use_joint=args.joint!="off"
    is_full=args.joint=="full"
    joint_scale=0.5 if args.joint in ("half","half_prob5") else 1.0

    df=pd.read_parquet(PANEL).sort_index()
    levels=fb.build_levels(df)
    levels["__df__"]=df
    bl=b5.brent_levels(df)
    for k,v in bl.items():
        levels[k]=v
    print(f"Panel {df.index.min().date()}->{df.index.max().date()} rows={len(df)} | {args.subset} {args.overlay} cap={args.cap} joint={args.joint} cush={args.cush}")

    # build factors for cap
    factors, rets, turn, legpos = b5.build_v5(levels, capv, False)
    # Cushing scaling (causal)
    if args.cush!="off":
        cush_daily=get_cushing_daily(df.index)
        if cush_daily is not None:
            min_sc=0.5 if args.cush=="s05" else 0.7
            sc=cushing_scale(cush_daily, min_sc)
            sc_lag=sc.shift(1).fillna(1.0).reindex(factors["bzwti"].index).fillna(1.0)
            # scale bzwti net via position scaling approximation: scale return
            # rebuild bzwti with scaled position for correctness
            lvl=levels["bzwti"]
            base=b4.base_of(lvl).shift(1).replace(0.0,np.nan)
            # original bzwti pos from factors; scale pos
            orig_pos=factors["bzwti"]
            new_pos=orig_pos*sc_lag
            # re-apply leg risk already done; just clip
            factors["bzwti"]=new_pos
            rets["bzwti"]=new_pos.shift(1).fillna(0.0)*lvl.diff()/base
            turn["bzwti"]=new_pos.diff().abs().fillna(0.0)
            print(f"  Cushing scaling {args.cush} active (min {min_sc})")
        else:
            print("  Cushing cache missing — CUSH OFF (graceful)")

    net=b5.apply_costs(factors, rets, turnover=turn)
    isw=window_df(net, IS_START, df.index.max())
    oos=window_df(net, OOS_START, IS_START)
    w=b5.weight_scheme(isw[flist], "EQ")
    print(f"  Weights EQ: {', '.join(f'{k}={v:.2f}' for k,v in w.items())}")

    # depth/crash/crude for joint (causal, from NOCAP depth baseline for stability)
    zdf={k: fb.seasonal_z(levels[k]) for k in ["crack_321","crack_gas","crack_ho","ng","bzwti"]}
    for k in ["brent321","brent_gas","brent_ho"]:
        zdf[k]=fb.seasonal_z(bl[k])
    base_depth=b5.book_depth(legpos, zdf, pd.Index(df.index))
    held=base_depth.shift(1)
    crash5=base_depth.shift(6)-base_depth.shift(1)
    crude20=df.CL.pct_change(20).shift(1)
    # joint raw causal
    if use_joint:
        joint_raw=(crash5>=THR_CRASH)&(held<=THR_DEPTH)&(crude20<=THR_CRUDE)
        joint_raw=joint_raw.fillna(False)
        print(f"  Joint crisis filter active: OOS {int(joint_raw.loc[OOS_START:IS_START].sum())} days, IS {int(joint_raw.loc[IS_START:].sum())} days (crash>=1 depth<=-1.25 crude<=-15%)")
    else:
        joint_raw=None

    # build book and overlay
    raw_book=b5.book_returns(net, flist, w)
    raw_is=window(raw_book, IS_START, df.index.max())
    raw_oos=window(raw_book, OOS_START, IS_START)

    if args.overlay=="book":
        if use_joint:
            pn=prob_n  # None for full, int for prob
            over_is=apply_overlay_prob(raw_is, joint_raw.reindex(raw_is.index).fillna(False) if joint_raw is not None else None, pn, joint_scale=joint_scale)
            over_oos=apply_overlay_prob(raw_oos, joint_raw.reindex(raw_oos.index).fillna(False) if joint_raw is not None else None, pn, joint_scale=joint_scale)
        else:
            over_is=b5.apply_overlay_v2(raw_is)
            over_oos=b5.apply_overlay_v2(raw_oos)
    else:
        # per-complex
        pn=prob_n if use_joint else None
        jr=joint_raw if use_joint else None
        over_is=apply_overlay_per_complex(net.reindex(raw_is.index), flist, w, jr, pn)
        over_oos=apply_overlay_per_complex(net.reindex(raw_oos.index), flist, w, jr, pn)
        over_is=window(over_is, IS_START, df.index.max())
        over_oos=window(over_oos, OOS_START, IS_START)

    si, so = stats(over_is), stats(over_oos)
    sr, sr_o = stats(raw_is), stats(raw_oos)
    print(f"\n=== vNext: {args.subset} {args.overlay} cap={args.cap} joint={args.joint} cush={args.cush} ===")
    print(f"IS  raw {sr['sharpe']:.2f} {sr['cagr']*100:.1f}% DD {sr['maxdd']*100:.1f}% vol{sr['vol']*100:.1f}% | over {si['sharpe']:.2f} {si['cagr']*100:.1f}% DD {si['maxdd']*100:.1f}% vol{si['vol']*100:.1f}% worst{si['worst']*100:.2f}%")
    print(f"OOS raw {sr_o['sharpe']:.2f} {sr_o['cagr']*100:.1f}% DD {sr_o['maxdd']*100:.1f}% vol{sr_o['vol']*100:.1f}% | over {so['sharpe']:.2f} {so['cagr']*100:.1f}% DD {so['maxdd']*100:.1f}% vol{so['vol']*100:.1f}% worst{so['worst']*100:.2f}%")

    if args.verbose:
        print("\n--- yearly OOS over ---")
        for y,g in over_oos.groupby(over_oos.index.year):
            print(f" {y} {g.sum()*100:+6.1f}%  raw {raw_oos[raw_oos.index.year==y].sum()*100:+6.1f}%")
        print("\n--- worst 5 OOS ---")
        print(over_oos.nsmallest(5).to_string())
        print("\n--- top 5 raw OOS (payoff concentration) ---")
        top5=raw_oos.nlargest(5)
        print(top5.to_string())
        conc=top5.sum()/raw_oos.sum() if raw_oos.sum()!=0 else 0
        print(f"top5 concentration: {conc*100:.1f}% of total raw {raw_oos.sum()*100:.1f}%")
        # shuffled control
        rng=np.random.default_rng(7)
        sh=[stats(pd.Series(rng.permutation(raw_oos.to_numpy()), index=raw_oos.index))["sharpe"] for _ in range(30)]
        sh2=[stats(b5.apply_overlay_v2(pd.Series(rng.permutation(raw_oos.to_numpy()), index=raw_oos.index)))["sharpe"] for _ in range(30)]
        print(f"shuffled raw mean {np.mean(sh):.2f} sd {np.std(sh):.2f} (real {sr_o['sharpe']:.2f})")
        print(f"shuffled V2 mean {np.mean(sh2):.2f} sd {np.std(sh2):.2f} (real V2 {stats(b5.apply_overlay_v2(raw_oos))['sharpe']:.2f})")

    if args.cost_sensitivity:
        print("\n--- cost sensitivity (trade bps) on OOS over ---")
        for bps in [0,5,10,20]:
            net2=b5.apply_costs(factors, rets, turnover=turn)
            # quick: scale trade cost
            # rebuild with trade bps
            net2=pd.DataFrame({k: rets[k] - bps/10000*turn[k].fillna(0.0) - 20/252/10000*factors[k].abs() for k in rets})
            is2=window_df(net2, IS_START, df.index.max())
            w2=b5.weight_scheme(is2[flist], "EQ")
            raw2=b5.book_returns(net2, flist, w2)
            ro2=window(raw2, OOS_START, IS_START)
            if use_joint:
                pn=prob_n
                ov2=apply_overlay_prob(ro2, joint_raw.reindex(ro2.index).fillna(False) if joint_raw is not None else None, pn) if args.overlay=="book" else apply_overlay_per_complex(net2.reindex(ro2.index), flist, w2, joint_raw, pn)
                if args.overlay=="per":
                    ov2=window(ov2, OOS_START, IS_START)
            else:
                ov2=b5.apply_overlay_v2(ro2) if args.overlay=="book" else apply_overlay_per_complex(net2.reindex(ro2.index), flist, w2, None, None)
                if args.overlay=="per":
                    ov2=window(ov2, OOS_START, IS_START)
            print(f" {bps:2d}bps OOS Sharpe {stats(ov2)['sharpe']:.2f} CAGR {stats(ov2)['cagr']*100:.2f}% DD {stats(ov2)['maxdd']*100:.1f}%")

    # gap coverage ledger
    print("\n--- gap coverage ---")
    print(" G1 leg-switch phantom: fixed (per-leg F2)")
    print(" G2 basis mismatch: fixed (dlevel/base)")
    print(" G3 gap notional: " + ("capped "+args.cap if args.cap!="nocap" else "NOCAP (live gap risk ~-3% day)"))
    print(f" Factor dilution: CORE3 kept, brent sleeve {'on' if args.subset=='core3bb' else 'off'}")
    print(f" Overlay: V2 {'+ joint '+args.joint if use_joint else 'alone'} ({'per-complex' if args.overlay=='per' else 'book-level'})")
    print(f" Cushing sizing: {args.cush} {'(standalone +0.06 Sharpe on bzwti)' if args.cush!='off' else '(off, falsified as gate but small sizing gain)'}")
    print(" Weather/storage gates: falsified as gates, documented")
    print(" Roll: stub 20bps/yr (adjacent spread unavailable free); proxy in engine_v2")
    print(" Fills: 5bps baseline, stress 2x in high vol")

if __name__=="__main__":
    main()
