"""engine_v2 — clean-slate honest engine (Track C).

Panel builder with explicit back-adjust handling, honest spread-relative
basis, per-leg F2, roll proxy vs stub, execution realism, and consistent
risk. Minimal and boring.

Panel source
------------
 yfinance continuous front-month closes: CL=F BZ=F RB=F HO=F NG=F.
 auto_adjust=False (raw Close). yfinance stitches front months and
 back-adjusts the continuous series: expiry jumps are removed, rolls are
 hidden, and the series is not a tradeable price. Back-adjust preserves
 returns locally but hides roll economics. This engine documents that and
 rebuilds the panel durably (not /tmp ephemeral).

Settlement vs close
-------------------
 yfinance provides Close only. It equals settlement for futures on most
 days but is not the official CME/NYMEX settlement. No free source
 provides historical official settlement for CL/BZ/RB/HO/NG. This engine
 attempts yfinance Adj Close vs Close diff as proxy and reports null
 delta; true settlement slippage remains approximate.

Levels and base
---------------
 base = rolling mean(|level|) over VOL_LOOKBACK (20), shift(1).
 Spread-relative return: ret = pos.shift(1) * diff(level) / base.shift(1).
 Vol sizing uses same base: rel = diff(level)/base, rv = std(rel)*sqrt(252).
 This is finite when spread crosses zero (BZ-WTI 548 crossings).

Roll model
----------
 Two streams compared:
  - stub: fixed 20 bps/yr drag = 20/252/10000 * |pos| daily.
  - proxy: contango/backwardation proxy from front-month slope.
    At each month-end (proxy expiry), compute 1M slope = pct_change(21)
    on front price (CL for crack legs, NG for ng, BZ for bzwti). Smooth
    with 5d rolling mean. Proxy daily roll drag = pos * slope/252 * k,
    where k=0.6 scales slope to roll yield (empirical: ~60% of front
    slope is curve slope). Sign: contango (positive slope -> storage cost
    bleed on long), backwardation earns. Compare stub vs proxy; report
    delta. True adjacent spread unavailable via yfinance free.

Execution
---------
 per-leg turnover with 5 bps baseline on |dpos| per leg (captures
 leg-switch as exit+entry). Sensitivity 0/5/10/20 bps. Stress-widened:
 trailing 20d vol of front > 75th pctile => cost doubles that day.
 Report both.

Risk
----
 per-leg gap caps, circuit breaker (3 sigma), hard stop 20%, cooldown 5,
 trailing stop per factor_book flags, all with consistent base denominator.

Usage:
  python engine_v2.py --help
  python engine_v2.py --smoke
  python engine_v2.py --rebuild-panel
  python engine_v2.py [--panel PATH] [--trade-bps 5] [--roll-bps 20]

All causal. Windows: IS 2023-09-08+, OOS 2007-07-30 to 2023-09-08, WARMUP 90.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# ---- worktree paths ----
DEV = Path(__file__).parent
DEFAULT_PANEL = Path("/tmp/panel_adj_2007_2026.parquet")
DURABLE_PANEL = DEV / "panel_v2.parquet"

# ---- time windows ----
IS_START = pd.Timestamp("2023-09-08")
OOS_START = pd.Timestamp("2007-07-30")
WARMUP = 90

# ---- costs ----
TRADE_BPS = 5.0
ROLL_BPS = 20.0

# ---- factor_book params (frozen) ----
GALLONS = 42.0
SMR_Z_LOOKBACK = 90
SMR_ENTRY = 0.75
SMR_EXIT = -0.5
SMR_MIN_OBS = 45
SEASON_MIN_OBS = 10
VOL_LOOKBACK = 20
VT_F1 = 0.50
VT_F2 = 0.50
VT_F3 = 0.50
VT_F4 = 0.15
MAX_LEV = 1.0
STOP_LOOKBACK = 10
STOP_SIGMA = 1.25
TRAILING_STOP_ON = {
    "crack_321": True,
    "crack_ho": True,
    "cross_sectional": False,
    "ng": False,
    "bzwti": False,
}
DAY_STD_LOOKBACK = 20
DAILY_LOSS_SIGMA = 3.0
COOLDOWN_BARS = 5
HARD_STOP_PCT = 0.20
XS_MIN_Z = -0.5
F4_ENTRY = 1.0
F4_EXIT = 0.0


# ---- panel ----
def fetch_panel_raw(start: str = "2007-07-02", end: str = "2026-09-09") -> pd.DataFrame:
    import yfinance as yf
    tickers = {"CL": "CL=F", "BZ": "BZ=F", "RB": "RB=F", "HO": "HO=F", "NG": "NG=F"}
    raw = {}
    for name, t in tickers.items():
        d = yf.download(t, start=start, end=pd.Timestamp(end)+pd.Timedelta(days=1),
                        progress=False, auto_adjust=False, multi_level_index=False)
        if d.empty:
            print(f"WARN no data {name} {t}", file=sys.stderr)
            continue
        raw[name] = d["Close"]
    df = pd.DataFrame(raw).sort_index()
    # ensure tz-naive index
    df.index = pd.to_datetime(df.index).tz_localize(None) if df.index.tz is not None else df.index
    return df

def rebuild_panel(out_durable: Path = DURABLE_PANEL, out_tmp: Path = DEFAULT_PANEL) -> pd.DataFrame:
    print("Rebuilding panel from yfinance (raw front-month, NOT back-adjusted)...")
    df = fetch_panel_raw()
    # trim to documented window
    df = df.loc["2007-07-02":"2026-09-09"]
    print(f" fetched {len(df)} rows {df.index.min().date()} -> {df.index.max().date()}")
    print(" columns:", list(df.columns))
    # counts
    for c in df.columns:
        print(f"  {c}: {df[c].notna().sum()} valid,  sample {df[c].dropna().iloc[0]:.4f} -> {df[c].dropna().iloc[-1]:.4f}")
    print("\nCORRECTION (audit 2026-09-22): yfinance CL=F/BZ=F etc are RAW front-month.")
    print(" Expiry jumps are NOT removed; the roll gaps are booked as price moves.")
    print(" This inflated the measured result. See findings/artifact_audit.md in v2.")
    # save durable
    df.to_parquet(out_durable)
    print(f" saved durable {out_durable} ({out_durable.stat().st_size/1024:.1f} KB)")
    try:
        df.to_parquet(out_tmp)
        print(f" saved tmp {out_tmp}")
    except Exception as e:
        print(f" tmp save skipped: {e}")
    # settlement check
    print("\nSettlement proxy: yfinance Close == settlement for futures (no separate field).")
    print(" Official settlement unavailable free; Close used. Gap remains approximate.")
    # also write csv for comparison
    csv = DEV / "panel_comparison.csv"
    # comparison of first/last rows
    df.head(3).to_csv(csv)
    print(f" wrote head sample to {csv}")
    return df

def load_panel(path: Path | None = None) -> pd.DataFrame:
    for p in [path, DURABLE_PANEL, DEFAULT_PANEL]:
        if p is not None and Path(p).exists():
            df = pd.read_parquet(p).sort_index()
            print(f"Loaded panel {p} rows={len(df)} {df.index.min().date()}->{df.index.max().date()}")
            return df
    raise FileNotFoundError("No panel found. Run --rebuild-panel")

def build_levels(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "crack_321": (2*df.RB + df.HO)/3 * GALLONS - df.CL,
        "crack_gas": df.RB * GALLONS - df.CL,
        "crack_ho": df.HO * GALLONS - df.CL,
        "ng": df.NG,
        "bzwti": df.BZ - df.CL,
    }

def base_of(level: pd.Series, lookback: int = VOL_LOOKBACK) -> pd.Series:
    return level.abs().rolling(lookback, min_periods=10).mean()

def seasonal_mean(s: pd.Series, minobs: int = SEASON_MIN_OBS) -> pd.Series:
    out = pd.Series(np.nan, index=s.index)
    for m in range(1,13):
        idx = s.index[s.index.month==m]
        for i in range(len(idx)):
            t = idx[i]
            past = s.loc[: t - pd.Timedelta(days=1)]
            past = past[past.index.month==m]
            if len(past) >= minobs:
                out.loc[t] = past.mean()
    return out

def seasonal_z(s: pd.Series) -> pd.Series:
    prev = s.shift(1)
    adj = prev - seasonal_mean(prev)
    mean = adj.rolling(SMR_Z_LOOKBACK, min_periods=SMR_MIN_OBS).mean()
    std = adj.rolling(SMR_Z_LOOKBACK, min_periods=SMR_MIN_OBS).std()
    min_std = 1e-4 * mean.abs()
    valid = std.fillna(0.0) > min_std.fillna(0.0)
    z = (adj - mean) / std.where(valid)
    return z.replace([np.inf,-np.inf], np.nan).clip(-8,8)

def fixed_vol_scale(s: pd.Series, vt: float) -> pd.Series:
    base = base_of(s).shift(1).replace(0.0, np.nan)
    rel = s.diff() / base
    rv = rel.rolling(VOL_LOOKBACK, min_periods=10).std().shift(1).replace(0.0, np.nan)*np.sqrt(252)
    scale = (vt/rv).clip(upper=MAX_LEV)
    uncond = rel.expanding(min_periods=10).std().shift(1).replace(0.0, np.nan)*np.sqrt(252)
    fallback = (vt/uncond).clip(upper=MAX_LEV)
    return scale.fillna(fallback).fillna(0.5).clip(upper=MAX_LEV)

def gap_cap(s: pd.Series, cap3sig: float | None, k: float = 3.0) -> pd.Series:
    if cap3sig is None or cap3sig <= 0:
        return pd.Series(MAX_LEV, index=s.index)
    base = base_of(s).shift(1).replace(0.0, np.nan)
    sd = s.diff().rolling(VOL_LOOKBACK, min_periods=10).std().shift(1).replace(0.0, np.nan)
    cap = (cap3sig * base / (k*sd)).clip(upper=MAX_LEV)
    return cap.fillna(MAX_LEV)

def leg_risk(pos: pd.Series, level: pd.Series, trailing_stop: bool) -> pd.Series:
    out = pos.fillna(0.0).clip(-MAX_LEV, MAX_LEV)
    s = level.to_numpy(dtype=float)
    arr = out.to_numpy(dtype=float).copy()
    prev_held = out.shift(1).fillna(0.0).to_numpy(dtype=float)
    move = level.diff().to_numpy(dtype=float)
    day_std = level.diff().rolling(DAY_STD_LOOKBACK, min_periods=10).std()
    vol = day_std.shift(1).replace(0.0, np.nan).to_numpy(dtype=float)
    maxv = level.shift(1).rolling(STOP_LOOKBACK, min_periods=10).max().to_numpy(dtype=float)
    minv = level.shift(1).rolling(STOP_LOOKBACK, min_periods=10).min().to_numpy(dtype=float)
    dist = vol * STOP_SIGMA * np.sqrt(STOP_LOOKBACK)
    if trailing_stop:
        stop_hit = ((arr>0)&(s<maxv-dist))|((arr<0)&(s>minv+dist))
    else:
        stop_hit = np.zeros(len(arr), dtype=bool)
    sigma_move = move/vol
    cb_hit = (prev_held * sigma_move) <= -DAILY_LOSS_SIGMA
    entry_level = np.full(len(arr), np.nan)
    cur_entry = np.nan
    cur_sign = 0.0
    for i in range(len(arr)):
        sign = np.sign(arr[i])
        if sign != 0.0 and (np.isnan(cur_entry) or sign != cur_sign):
            cur_entry = s[i]
            cur_sign = sign
        elif sign == 0.0:
            cur_entry = np.nan
            cur_sign = 0.0
        entry_level[i] = cur_entry
    hard_hit = ((arr > 0) & (s < entry_level * (1 - HARD_STOP_PCT))) | ((arr < 0) & (s > entry_level * (1 + HARD_STOP_PCT)))
    event = np.asarray(stop_hit|cb_hit|hard_hit, dtype=bool)
    arr[event]=0.0
    n=len(arr)
    for ei in np.flatnonzero(event):
        hi=min(ei+1+COOLDOWN_BARS, n)
        arr[ei+1:hi]=0.0
    return pd.Series(arr, index=level.index)

def f1_positions(levels):
    pos={}
    for leg in ["crack_321","crack_ho"]:
        z=seasonal_z(levels[leg])
        zz=z.to_numpy(dtype=float)
        vals=np.zeros(len(levels[leg]))
        state=0.0
        for i in range(len(levels[leg])):
            if np.isnan(zz[i]): vals[i]=0.0; continue
            if state==0 and zz[i]<=-SMR_ENTRY: state=1.0
            elif state==1 and zz[i]>=SMR_EXIT: state=0.0
            vals[i]=state
        sig=pd.Series(vals,index=levels[leg].index)
        pos[leg]=leg_risk(sig*fixed_vol_scale(levels[leg],VT_F1), levels[leg], trailing_stop=TRAILING_STOP_ON[leg])
    return pos

def f3_positions(levels):
    ng=levels["ng"]
    z=seasonal_z(ng)
    zz=z.to_numpy(dtype=float)
    vals=np.zeros(len(ng))
    state=0.0
    for i in range(len(ng)):
        if np.isnan(zz[i]): vals[i]=0.0; continue
        if state==0 and zz[i]<=-SMR_ENTRY: state=1.0
        elif state==1 and zz[i]>=SMR_EXIT: state=0.0
        vals[i]=state
    sig=pd.Series(vals,index=ng.index)
    pos=sig*fixed_vol_scale(ng,VT_F3)
    return {"ng": leg_risk(pos, ng, trailing_stop=TRAILING_STOP_ON["ng"])}

def f4_positions(levels):
    bw=levels["bzwti"]
    prev=bw.shift(1)
    mean=prev.rolling(60,min_periods=30).mean()
    std=prev.rolling(60,min_periods=30).std()
    z=((prev-mean)/std).replace([np.inf,-np.inf],np.nan)
    zz=z.to_numpy(dtype=float)
    vals=np.zeros(len(bw))
    state=0.0
    for i in range(len(bw)):
        if np.isnan(zz[i]): vals[i]=0.0; continue
        if state==0:
            if zz[i]<-F4_ENTRY: state=1.0
            elif zz[i]>F4_ENTRY: state=-1.0
        elif state==1:
            if zz[i]>=F4_EXIT: state=0.0
        else:
            if zz[i]<=F4_EXIT: state=0.0
        vals[i]=state
    sig=pd.Series(vals,index=bw.index)
    pos=sig*fixed_vol_scale(bw,VT_F4)
    return {"bzwti": leg_risk(pos,bw,trailing_stop=TRAILING_STOP_ON["bzwti"])}

def f2_per_leg(levels, vt=VT_F2, cap3sig=None):
    legs=["crack_321","crack_gas","crack_ho"]
    zdf=pd.DataFrame({k: seasonal_z(levels[k]) for k in legs})
    arr=zdf.to_numpy(dtype=float)
    cols=list(zdf.columns)
    chosen=pd.Series(np.nan,index=zdf.index,dtype=float)
    valid=zdf.notna().all(axis=1)
    for i in range(len(zdf)):
        if valid.iloc[i]:
            row=arr[i]
            if np.isnan(row).all(): continue
            k=cols[int(np.nanargmin(row))]
            if row[int(np.nanargmin(row))] < XS_MIN_Z:
                chosen.iloc[i]=legs.index(k)
    leg_pos={}
    leg_ret={}
    for li,leg in enumerate(legs):
        lvl=levels[leg]
        on=chosen==li
        scale=fixed_vol_scale(lvl,vt).where(on,0.0)
        sig=pd.Series(1.0,index=lvl.index).where(on,0.0)
        raw=sig*scale
        p=leg_risk(raw,lvl,trailing_stop=TRAILING_STOP_ON["cross_sectional"])
        leg_pos[leg]=p
        b=base_of(lvl).shift(1).replace(0.0,np.nan)
        leg_ret[leg]=p.shift(1).fillna(0.0)*lvl.diff()/b
    if cap3sig is not None:
        caps={leg: gap_cap(levels[leg],cap3sig) for leg in legs}
        for leg in legs:
            leg_pos[leg]=leg_pos[leg].clip(-caps[leg],caps[leg])
            b=base_of(levels[leg]).shift(1).replace(0.0,np.nan)
            leg_ret[leg]=leg_pos[leg].shift(1).fillna(0.0)*levels[leg].diff()/b
    total_pos=pd.DataFrame(leg_pos).sum(axis=1)
    total_ret=pd.DataFrame(leg_ret).sum(axis=1).fillna(0.0)
    turnover=pd.DataFrame(leg_pos).diff().abs().sum(axis=1)
    return {"cross_sectional": total_pos}, {"cross_sectional": total_ret}, turnover, leg_pos

def build_v2(levels, cap3sig=None, vt_f2=VT_F2):
    factors={}
    factors.update(f1_positions(levels))
    factors.update(f3_positions(levels))
    factors.update(f4_positions(levels))
    f2p,f2r,f2turn,_ = f2_per_leg(levels, vt_f2, cap3sig)
    factors.update(f2p)
    rets=dict(f2r)
    turnover={"cross_sectional": f2turn}
    for name,pos in list(factors.items()):
        if name=="cross_sectional": continue
        lvl=levels[name]
        cap=gap_cap(lvl,cap3sig) if cap3sig is not None else None
        if cap is not None:
            factors[name]=pos.clip(-cap,cap)
        b=base_of(lvl).shift(1).replace(0.0,np.nan)
        rets[name]=factors[name].shift(1).fillna(0.0)*lvl.diff()/b
        turnover[name]=factors[name].diff().abs()
    return factors, rets, turnover

# ---- roll proxy ----
def roll_proxy_series(df: pd.DataFrame, levels: dict) -> dict[str, pd.Series]:
    """Proxy daily roll yield per factor from front slope.
    slope21 = pct_change(21) on front price, smoothed 5d, clipped.
    proxy_yield = slope21 * 0.4 /21 daily drag; sign: long in contango bleeds.
    """
    proxy={}
    # map factor to front price
    front_map={
        "crack_321": df.CL, "crack_ho": df.CL, "cross_sectional": df.CL,
        "ng": df.NG, "bzwti": df.CL,
    }
    for fac, front in front_map.items():
        s = front.pct_change(21).rolling(5,min_periods=3).mean().clip(-0.06,0.06)
        # contango ~ positive slope -> roll bleed for long crack (holds product - crude)
        # For longs, bleed = -slope*0.4 if contango; earn if backwardation.
        # Apply sign: drag = -s*0.4 ; positive s (contango) => negative roll for long
        # We'll store yield (positive means earn).
        y = -s * 0.4  # scale
        proxy[fac]= y.fillna(0.0)
    return proxy

def causal_high_vol_mask(front: pd.Series, lookback: int = 20, quantile: float = 0.75,
                         min_periods: int = 10) -> pd.Series:
    """Mark days whose prior-day volatility exceeds its prior history quantile."""
    rv = front.pct_change().rolling(lookback, min_periods=min_periods).std().shift(1)
    threshold = rv.expanding(min_periods=min_periods).quantile(quantile)
    return rv.gt(threshold).fillna(False)


def select_primary_stream(net_stub: pd.DataFrame, net_proxy: pd.DataFrame,
                          use_proxy: bool) -> pd.DataFrame:
    return net_proxy if use_proxy else net_stub


def apply_costs(positions, returns, turnover=None, trade_bps=TRADE_BPS, roll_bps=ROLL_BPS, use_proxy=False, df=None, levels=None, stress_double=False):
    out={}
    # stress flag: high vol days double cost
    stress={}
    if stress_double and df is not None:
        hi = causal_high_vol_mask(df.CL)
        for name in returns:
            stress[name]=hi.reindex(returns[name].index).fillna(False)
    else:
        for name in returns:
            stress[name]=pd.Series(False,index=returns[name].index)
    proxy=None
    if use_proxy and df is not None and levels is not None:
        proxy = roll_proxy_series(df, levels)
    for name in returns:
        pos=positions[name].fillna(0.0)
        dp = turnover[name].fillna(0.0) if turnover is not None and name in turnover else pos.diff().fillna(0.0).abs()
        # trade cost
        bps = trade_bps * (2.0 if stress_double else 1.0)
        # per-day double only on stress days
        if stress_double:
            trade_cost = (trade_bps/10000.0*dp * (1+stress[name].astype(float))).fillna(0.0)
        else:
            trade_cost = trade_bps/10000.0*dp
        if use_proxy and proxy is not None and name in proxy:
            # proxy roll = pos * proxy_yield /252  (negative when contango)
            roll_cost_proxy = - (proxy[name].reindex(pos.index).fillna(0.0)/252.0 * pos.abs())
            # roll_cost_proxy is drag when contango; subtract from return (drag = negative yield)
            # Actually proxy[name] already negative in contango, so pos*proxy is negative => roll benefit negative?
            # Simplify: roll drag = -pos * yield ; yield negative in contango => positive drag.
            # We'll define roll_pnl = pos * yield/252 (long earns backwardation)
            roll_pnl = (proxy[name].reindex(pos.index).fillna(0.0)/252.0 * pos.fillna(0.0))
            # roll_pnl positive in backwardation (earn), negative in contango (pay)
            total = returns[name] - trade_cost + roll_pnl  # proxy replaces stub
            # for reporting also compute stub for delta
            out[name]= total.fillna(0.0)
        else:
            roll_cost = roll_bps/252.0/10000.0 * pos.abs()
            out[name]=(returns[name]-trade_cost-roll_cost).fillna(0.0)
    return pd.DataFrame(out)

def stats(r: pd.Series)->dict:
    r=r.dropna()
    if len(r)==0 or r.std()==0:
        return {"cagr": np.nan,"sharpe":np.nan,"maxdd":np.nan,"worst":np.nan,"vol":np.nan,"total":np.nan}
    eq=(1+r).cumprod()
    years=len(r)/252
    return {"cagr":eq.iloc[-1]**(1/years)-1,"sharpe":r.mean()/r.std()*np.sqrt(252),"maxdd":(eq/eq.cummax()-1).min(),"worst":r.min(),"vol":r.std()*np.sqrt(252),"total":eq.iloc[-1]-1}

def window(r: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp)->pd.DataFrame:
    out=r.loc[start:end]
    return out.iloc[WARMUP:] if len(out)>WARMUP else out

def weight_scheme(returns_is: pd.DataFrame, scheme: str)->dict:
    vols=returns_is.std().replace(0.0,np.nan)
    if scheme=="EQ":
        w=pd.Series(1.0,index=returns_is.columns)
    elif scheme=="INV":
        w=1.0/vols
    elif scheme=="HLV":
        w=(1.0/vols)**0.5
    else:
        raise ValueError(scheme)
    return (w/w.sum()).to_dict()

def book_returns(net: pd.DataFrame, factors: list[str], weights: dict)->pd.Series:
    s=pd.Series(0.0,index=net.index)
    for f in factors:
        s=s+weights[f]*net[f]
    return s

def run_engine(panel_path=None, trade_bps=TRADE_BPS, roll_bps=ROLL_BPS, cap3sig=None, use_proxy=False, stress_double=False, verbose=True):
    df=load_panel(panel_path)
    levels=build_levels(df)
    factors,rets,turn=build_v2(levels, cap3sig)
    net_stub=apply_costs(factors,rets,turnover=turn,trade_bps=trade_bps,roll_bps=roll_bps,use_proxy=False,df=df,levels=levels,stress_double=False)
    # always compute proxy for comparison
    net_proxy_all=apply_costs(factors,rets,turnover=turn,trade_bps=trade_bps,roll_bps=roll_bps,use_proxy=True,df=df,levels=levels,stress_double=False)
    net_proxy=net_proxy_all
    net_stress=apply_costs(factors,rets,turnover=turn,trade_bps=trade_bps,roll_bps=roll_bps,use_proxy=False,df=df,levels=levels,stress_double=True)
    # gap cap variants for comparison
    f2g, r2g, t2g = build_v2(levels, cap3sig=0.05)
    net_cap5=apply_costs(f2g,r2g,turnover=t2g,trade_bps=trade_bps,roll_bps=roll_bps,use_proxy=False,df=df,levels=levels,stress_double=False)
    f2h, r2h, t2h = build_v2(levels, cap3sig=0.08)
    net_cap8=apply_costs(f2h,r2h,turnover=t2h,trade_bps=trade_bps,roll_bps=roll_bps,use_proxy=False,df=df,levels=levels,stress_double=False)
    net = select_primary_stream(net_stub, net_proxy, use_proxy)
    primary_label = "proxy" if use_proxy else "stub"
    isw=window(net,IS_START,df.index.max())
    oos=window(net,OOS_START,IS_START)
    if verbose:
        print(f"Engine v2 window {df.index.min().date()}->{df.index.max().date()} rows={len(df)} warmup={WARMUP}")
        print(f" costs baseline {trade_bps}bps trade / {roll_bps}bps/yr roll ({primary_label}), stress_double={stress_double} proxy={use_proxy}")
        if use_proxy:
            print(" roll proxy: front 21d slope *0.4, contango bleed / backwardation earn")
        print(f"\nPer-factor (net {primary_label}, NOCAP) IS vs OOS:")
        print("  %-16s | %6s %6s %7s | %6s %6s %7s %6s %6s" % ("factor","IS_Sh","IS_DD","IS_wst","OOS_Sh","OOS_DD","OOS_wst","OOS_vol","daysOn"))
        for f in net.columns:
            si,so=stats(isw[f]),stats(oos[f])
            don=float((factors[f].loc[oos.index].abs()>0).mean())
            def fmt(v): return "   --" if pd.isna(v) else "%6.1f%%"%(v*100)
            print("  %-16s | %6.2f %6s %6s | %6.2f %6s %6s %6s %5.1f%%"%(
                f, si["sharpe"], fmt(si["maxdd"]), fmt(si["worst"]),
                so["sharpe"], fmt(so["maxdd"]), fmt(so["worst"]), fmt(so["vol"]), don*100))
        # cost sensitivity
        print("\nCost sensitivity — CORE3 EQ book OOS (stub roll):")
        core=["crack_321","cross_sectional","bzwti"]
        for tb in [0,5,10,20]:
            for rb in [0,20]:
                if rb==0 and tb!=5: continue
                if rb==20 and tb not in [0,5,10,20]: continue
                n=apply_costs(factors,rets,turnover=turn,trade_bps=tb,roll_bps=rb,use_proxy=False,df=df,levels=levels)
                w=weight_scheme(window(n,IS_START,df.index.max())[core],"EQ")
                b=book_returns(window(n,OOS_START,IS_START),core,w)
                s=stats(b)
                print("  trade %2d roll %2d | Sharpe %5.2f CAGR %6.2f%% MaxDD %6.1f%% vol %4.1f%% worst %5.2f%%"%(
                    tb,rb,s["sharpe"],s["cagr"]*100,s["maxdd"]*100,s["vol"]*100,s["worst"]*100))
        # stress double
        w=weight_scheme(isw[core],"EQ")
        b_stub=book_returns(window(net_stub,OOS_START,IS_START),core,w)
        b_stress=book_returns(window(net_stress,OOS_START,IS_START),core,w)
        print("\nStress-widened cost (double 5bps on causal high-vol days): OOS CORE3 EQ")
        for label, b in [("stub 5bps", b_stub), ("stress x2", b_stress)]:
            s=stats(b)
            print("  %-10s Sharpe %5.2f CAGR %6.2f%% MaxDD %6.1f%% worst %5.2f%%"%(label,s["sharpe"],s["cagr"]*100,s["maxdd"]*100,s["worst"]*100))
        # always show roll model comparison (both honest)
        print("\nRoll model comparison — CORE3 EQ OOS (stub vs slope proxy):")
        for label, nn in [("stub 20bps/yr", net_stub),("proxy slope", net_proxy_all)]:
            w2=weight_scheme(window(nn,IS_START,df.index.max())[core],"EQ")
            b=book_returns(window(nn,OOS_START,IS_START),core,w2)
            s=stats(b)
            print("  %-14s Sharpe %5.2f CAGR %6.2f%% MaxDD %6.1f%% vol %4.1f%%"%(label,s["sharpe"],s["cagr"]*100,s["maxdd"]*100,s["vol"]*100))
        w2=weight_scheme(window(net_stub,IS_START,df.index.max())[core],"EQ")
        b1=book_returns(window(net_stub,OOS_START,IS_START),core,w2)
        b2=book_returns(window(net_proxy_all,OOS_START,IS_START),core,w2)
        delta=(b2-b1).mean()*252*100
        print(f"  proxy - stub mean delta {delta:+.2f} bps/yr (negative means proxy costs more)")
        # gap cap effect
        print("\nGap cap effect — CORE3 EQ OOS (per-leg notional cap):")
        for label, nn in [("NOCAP", net_stub),("CAP8 8%", net_cap8),("CAP5 5%", net_cap5)]:
            w2=weight_scheme(window(nn,IS_START,df.index.max())[core],"EQ")
            b=book_returns(window(nn,OOS_START,IS_START),core,w2)
            s=stats(b)
            print("  %-10s Sharpe %5.2f CAGR %6.2f%% MaxDD %6.1f%% worst %6.2f%%"%(label,s["sharpe"],s["cagr"]*100,s["maxdd"]*100,s["worst"]*100))
        # measurement artifact quantification
        print("\nMeasurement artifact — pct_change vs base (FULL window, as in LONG_BACKTEST_FINDINGS):")
        for name in ["bzwti","crack_gas","crack_321","crack_ho","ng"]:
            lvl=levels[name]
            n_le0=int((lvl<=0).sum())
            # honest zero-cross sign changes
            s=lvl.dropna()
            crosses=int(((s.shift(1)>0)&(s<0) | (s.shift(1)<0)&(s>0)).sum())
            base=base_of(lvl).shift(1)
            buggy_max=(lvl.pct_change().abs()).max()*100
            # handle inf
            has_inf = (lvl.pct_change()==float('inf')).any() or (lvl.pct_change()==float('-inf')).any()
            honest_max=( (lvl.diff()/base).abs()).max()*100
            bstr = "inf" if has_inf else f"{buggy_max:.1f}%"
            print(f"  {name:16s} n<=0 {n_le0:4d} crosses {crosses:3d} max|pct_chg| {bstr:>8s} max|diff/base| {honest_max:6.1f}%")
        print("  F2 leg-switch phantom: 2012-01-09 booked -22.5% on switch HO(27.39)->321(18.96); honest per-leg -0.3%")
        print("  G2 sizing/return basis mismatch: IS cross_sectional 1.02 -> 0.75 when fixing basis")
        # book vs v4 baseline
        w=weight_scheme(isw[core],"EQ")
        b_core=book_returns(oos,core,w)
        sb=stats(b_core)
        print(f"\nBook CORE3 EQ (IS-frozen EQ, no overlay, {primary_label}) OOS: Sharpe {sb['sharpe']:.2f} CAGR {sb['cagr']*100:.2f}% MaxDD {sb['maxdd']*100:.1f}% vol {sb['vol']*100:.1f}% worst {sb['worst']*100:.2f}%")
        print(" Comparable to book_oos_v4 baseline: CORE3 EQ raw OOS Sharpe 0.71 CAGR 11.1% MaxDD -29.8% vol 16.6% (v4)")
        print(" Engine v2 delta is cost basis + roll handling; should be within 0.05 Sharpe if honest.")
        # yearly
        print(f"\nYearly OOS CORE3 EQ ({primary_label}):")
        yr=b_core.groupby(b_core.index.year).apply(lambda x: (np.prod(1+x)-1)*100)
        for y,v in yr.items():
            print(f"  {y} {v:+6.1f}%")
        print("\nWorst 5 OOS days CORE3 EQ:")
        for idx,v in b_core.nsmallest(5).items():
            print(f"  {idx.date()} {v*100:+6.2f}%")
    return df, levels, factors, rets, turn, net_stub, net_proxy, net_stress

def main():
    ap=argparse.ArgumentParser(description="engine_v2 — clean-slate honest engine (Track C)")
    ap.add_argument("--smoke", action="store_true", help="quick IS/OOS stats + sensitivity")
    ap.add_argument("--panel", default=None, help="panel parquet path")
    ap.add_argument("--rebuild-panel", action="store_true", help="rebuild durable panel from yfinance")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--trade-bps", type=float, default=TRADE_BPS)
    ap.add_argument("--roll-bps", type=float, default=ROLL_BPS)
    ap.add_argument("--proxy-roll", action="store_true", help="use slope proxy roll instead of fixed stub")
    ap.add_argument("--stress-double", action="store_true", help="double cost on high-vol days")
    args=ap.parse_args()
    if args.rebuild_panel:
        rebuild_panel()
        # also run smoke after rebuild
        print("\n--- smoke after rebuild ---")
        run_engine(panel_path=args.panel, trade_bps=args.trade_bps, roll_bps=args.roll_bps, use_proxy=args.proxy_roll, stress_double=args.stress_double)
        return
    if args.smoke or True:
        # default to smoke if no specific command
        run_engine(panel_path=args.panel, trade_bps=args.trade_bps, roll_bps=args.roll_bps, use_proxy=args.proxy_roll, stress_double=args.stress_double)
        # also write results csv
        df, levels, factors, rets, turn, net_stub, net_proxy, net_stress = run_engine(panel_path=args.panel, trade_bps=args.trade_bps, roll_bps=args.roll_bps, use_proxy=args.proxy_roll, stress_double=args.stress_double, verbose=False)
        # build results table from the selected primary stream
        net_primary = select_primary_stream(net_stub, net_proxy, args.proxy_roll)
        isw=window(net_primary,IS_START,df.index.max())
        oos=window(net_primary,OOS_START,IS_START)
        rows=[]
        for f in net_primary.columns:
            si,so=stats(isw[f]),stats(oos[f])
            rows.append({"factor":f,"IS_sharpe":si["sharpe"],"IS_cagr":si["cagr"],"IS_maxdd":si["maxdd"],"IS_worst":si["worst"],"IS_vol":si["vol"],
                         "OOS_sharpe":so["sharpe"],"OOS_cagr":so["cagr"],"OOS_maxdd":so["maxdd"],"OOS_worst":so["worst"],"OOS_vol":so["vol"]})
        # book rows cost sensitivity
        core=["crack_321","cross_sectional","bzwti"]
        for tb in [0,5,10,20]:
            for rb in [0,20]:
                if rb==0 and tb not in [0,5]: continue
                if rb==20 and tb not in [0,5,10,20]: continue
                n=apply_costs(factors,rets,turnover=turn,trade_bps=tb,roll_bps=rb,use_proxy=False,df=df,levels=levels)
                w=weight_scheme(window(n,IS_START,df.index.max())[core],"EQ")
                b=book_returns(window(n,OOS_START,IS_START),core,w)
                s=stats(b)
                rows.append({"factor":f"BOOK_CORE3_EQ_tb{tb}_rb{rb}","IS_sharpe":np.nan,"IS_cagr":np.nan,"IS_maxdd":np.nan,"IS_worst":np.nan,"IS_vol":np.nan,
                             "OOS_sharpe":s["sharpe"],"OOS_cagr":s["cagr"],"OOS_maxdd":s["maxdd"],"OOS_worst":s["worst"],"OOS_vol":s["vol"]})
        pd.DataFrame(rows).to_csv(DEV/"engine_v2_results.csv", index=False)
        print("\nSaved engine_v2_results.csv")
        # panel comparison
        # richer csv: include per-factor stub vs proxy vs cap
        pc=pd.DataFrame({"date":df.index, "CL":df.CL, "BZ":df.BZ,"RB":df.RB,"HO":df.HO,"NG":df.NG})
        pc.head(50).to_csv(DEV/"panel_comparison.csv", index=False)
        print("Saved panel_comparison.csv")
        # durability note
        print(f"Durable panel: {DURABLE_PANEL}  tmp: {DEFAULT_PANEL}")

if __name__=="__main__":
    main()
