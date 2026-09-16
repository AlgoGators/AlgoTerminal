"""Better features: volume, term structure, and temporal sequence."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
DEV=Path("/home/sebas/algoterminal-strategy-dev")
spec=importlib.util.spec_from_file_location("b5", str(DEV/"book_oos_v5.py"))
b5=importlib.util.module_from_spec(spec); spec.loader.exec_module(b5)
spec3=importlib.util.spec_from_file_location("fb", str(DEV/"factor_book.py"))
fb=importlib.util.module_from_spec(spec3); spec3.loader.exec_module(fb)
try:
    import yfinance as yf
    HAS_YF=True
except: HAS_YF=False
PANEL=DEV/"panel_ext_1990.parquet"
if PANEL.exists():
    df=pd.read_parquet(PANEL).sort_index()
else:
    df=pd.read_parquet(b5.PANEL).sort_index()
print(f"df {len(df)} {df.index.min().date()}->{df.index.max().date()} cols {list(df.columns)}")

# Try to fetch volume panel for same tickers if not already have volume
vol_df=None
try:
    # Check if df has volume already? Our panel only has Close, but yfinance download can give Volume
    # Try to fetch volume for last 5 years to test
    if HAS_YF:
        tickers={"CL":"CL=F","BZ":"BZ=F","RB":"RB=F","HO":"HO=F","NG":"NG=F"}
        vols={}
        for name,t in tickers.items():
            d=yf.download(t, start="2000-08-23", end="2026-09-10", progress=False, auto_adjust=False, multi_level_index=False)
            if not d.empty and "Volume" in d.columns:
                vols[name]=d["Volume"]
        if vols:
            vol_df=pd.DataFrame(vols).sort_index()
            print(f"Volume fetched {vol_df.shape} {vol_df.index.min().date()}->{vol_df.index.max().date()} na {vol_df.isna().sum().to_dict()}")
            vol_df.to_parquet(DEV/"panel_vol.parquet")
            print("Saved panel_vol.parquet")
        else:
            print("No volume in yf")
    else:
        print("No yf")
except Exception as e:
    print(f"vol fetch fail {e}")
    vol_df=None

if vol_df is None and (DEV/"panel_vol.parquet").exists():
    vol_df=pd.read_parquet(DEV/"panel_vol.parquet").sort_index()
    print(f"Loaded vol parquet {vol_df.shape}")

levels=fb.build_levels(df)
levels["__df__"]=df
bl=b5.brent_levels(df)
for k,v in bl.items(): levels[k]=v
factors,rets,turn,legpos=b5.build_v5(levels,None,False)
net=b5.apply_costs(factors,rets,turnover=turn)
isw=net.loc[pd.Timestamp("2023-09-08"):].iloc[90:]
try: w=b5.weight_scheme(isw[["crack_321","cross_sectional","bzwti"]],"EQ")
except: w={"crack_321":0.33,"cross_sectional":0.33,"bzwti":0.33}
raw_book=b5.book_returns(net, ["crack_321","cross_sectional","bzwti"], w)
zdf={k:fb.seasonal_z(levels[k]) for k in ["crack_321","crack_gas","crack_ho","ng","bzwti"] if k in levels}
for k in ["brent321","brent_gas","brent_ho"]:
    if k in levels:
        try: zdf[k]=fb.seasonal_z(levels[k])
        except: pass
depth=b5.book_depth(legpos,zdf,pd.Index(df.index))
held=depth.shift(1)
crash5=depth.shift(6)-depth.shift(1)
crash10=depth.shift(11)-depth.shift(1)
crash20=depth.shift(21)-depth.shift(1)
crude20=df.CL.pct_change(20).shift(1) if "CL" in df.columns else pd.Series(0,index=df.index)
crude10=df.CL.pct_change(10).shift(1) if "CL" in df.columns else pd.Series(0,index=df.index)
crude5=df.CL.pct_change(5).shift(1) if "CL" in df.columns else pd.Series(0,index=df.index)
vol20=raw_book.rolling(20,min_periods=10).std().shift(1)
vol60=raw_book.rolling(60,min_periods=20).std().shift(1)
ret5=raw_book.shift(1).rolling(5).sum()
ret20=raw_book.shift(1).rolling(20).sum()
skew20=raw_book.rolling(20).skew().shift(1)
kurt20=raw_book.rolling(20).kurt().shift(1)
crack_slope=levels["crack_321"].diff(20).shift(1) if "crack_321" in levels else pd.Series(0,index=df.index)
crack_slope5=levels["crack_321"].diff(5).shift(1) if "crack_321" in levels else pd.Series(0,index=df.index)
bzwti_level=levels["bzwti"] if "bzwti" in levels else pd.Series(0,index=df.index)
bzwti_slope=bzwti_level.diff(20).shift(1)
joint_raw=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
joint_raw=joint_raw.fillna(False).astype(int)

# New: volume features
if vol_df is not None:
    # Align to df index
    vol_df=vol_df.reindex(df.index)
    # CL volume z: same-month expanding z, causal
    cl_vol=vol_df["CL"] if "CL" in vol_df.columns else pd.Series(0,index=df.index)
    # volume spike: vol / rolling mean
    vol_mean20=cl_vol.rolling(20,min_periods=10).mean().shift(1)
    vol_spike=(cl_vol / vol_mean20.replace(0,np.nan)).fillna(1).clip(0,5)
    # log vol
    log_vol=np.log1p(cl_vol.fillna(0)).replace([np.inf,-np.inf],0).fillna(0)
    log_vol_z=(log_vol - log_vol.rolling(60,min_periods=20).mean().shift(1))/log_vol.rolling(60,min_periods=20).std().shift(1).replace(0,np.nan)
    log_vol_z=log_vol_z.fillna(0).clip(-5,5)
    # volume * price move interaction (flow)
    vol_x_ret = vol_spike * raw_book.shift(1).abs()
    # RB volume similarly for crack
    rb_vol=vol_df["RB"] if "RB" in vol_df.columns else cl_vol
    rb_spike=(rb_vol / rb_vol.rolling(20,min_periods=10).mean().shift(1).replace(0,np.nan)).fillna(1).clip(0,5)
else:
    vol_spike=pd.Series(1.0,index=df.index)
    log_vol_z=pd.Series(0.0,index=df.index)
    vol_x_ret=pd.Series(0.0,index=df.index)
    rb_spike=pd.Series(1.0,index=df.index)

# New: term structure proxy
# Since we have no second month, proxy via front price vs 60-day MA slope and via calendar
# front - MA60
term_proxy=(df.CL - df.CL.rolling(60).mean()).shift(1) / df.CL.shift(1).replace(0,np.nan) if "CL" in df.columns else pd.Series(0,index=df.index)
term_proxy=term_proxy.fillna(0).clip(-0.2,0.2)
# 20d roll yield proxy: (CL - CL.shift(20))/CL.shift(1)
roll_yield=(df.CL - df.CL.shift(20))/df.CL.shift(1).replace(0,np.nan) if "CL" in df.columns else pd.Series(0,index=df.index)
roll_yield=roll_yield.shift(1).fillna(0).clip(-0.1,0.1)
# crack term: crack_321 vs its MA
crack_term=(levels["crack_321"] - levels["crack_321"].rolling(60).mean()).shift(1) / levels["crack_321"].shift(1).replace(0,np.nan) if "crack_321" in levels else pd.Series(0,index=df.index)
crack_term=crack_term.fillna(0).clip(-0.5,0.5)

# Cross rank distance
# distance between most crushed and second most crushed
zdf_df=pd.DataFrame({k:zdf[k] for k in ["crack_321","crack_gas","crack_ho"] if k in zdf})
if len(zdf_df.columns)>=2:
    sorted_z=zdf_df.apply(lambda row: sorted(row.dropna()), axis=1)
    # crude distance: min vs second min
    def dist(row):
        vals=sorted([v for v in row if not pd.isna(v)])
        if len(vals)>=2:
            return vals[1]-vals[0]
        return 0
    cross_dist=zdf_df.apply(dist, axis=1).shift(1).fillna(0).clip(0,3)
else:
    cross_dist=pd.Series(0,index=df.index)

feat=pd.DataFrame({
    "held":held,"crash5":crash5,"crash10":crash10,"crash20":crash20,
    "crude20":crude20,"crude10":crude10,"crude5":crude5,
    "vol20":vol20,"vol60":vol60,"ret5":ret5,"ret20":ret20,"skew20":skew20,"kurt20":kurt20,
    "crack_slope":crack_slope,"crack_slope5":crack_slope5,"bzwti_slope":bzwti_slope,
    "joint":joint_raw.astype(float),
    "held_x_crash":held*crash5,"crash_x_crude":crash5*crude20,"vol_x_crash":vol20*crash5,
    "depth_abs":held.abs(),"crude_vol":crude20.abs(),
    "vol_spike":vol_spike,"log_vol_z":log_vol_z,"vol_x_ret":vol_x_ret,"rb_spike":rb_spike,
    "term_proxy":term_proxy,"roll_yield":roll_yield,"crack_term":crack_term,"cross_dist":cross_dist,
}, index=df.index)
for lag in [1,2,3,5,10]:
    feat[f"held_lag{lag}"]=held.shift(lag)
    feat[f"crash5_lag{lag}"]=crash5.shift(lag)
feat=feat.fillna(0).clip(-8,8)
is_wind=(raw_book>0.02).astype(int)
lab5=is_wind.rolling(5,min_periods=1).max().shift(-5).fillna(0)
lab10=is_wind.rolling(10,min_periods=1).max().shift(-10).fillna(0)
feat["wind5"]=lab5
feat["wind10"]=lab10
train_idx=feat.index[(feat.index>="2000-08-23") & (feat.index<"2015-01-01")]
valid_idx=feat.index[(feat.index>="2015-01-01") & (feat.index<"2020-01-01")]
test_idx=feat.index[(feat.index>="2020-01-02") & (feat.index<"2023-09-08")]
hold_idx=feat.index[feat.index>=pd.Timestamp("2023-09-08")]
feature_cols=[c for c in feat.columns if c not in ["wind5","wind10"]]
print(f"Features {len(feature_cols)} train {len(train_idx)} valid {len(valid_idx)} test {len(test_idx)} hold {len(hold_idx)}")
print(f"New features: vol_spike, log_vol_z, vol_x_ret, rb_spike, term_proxy, roll_yield, crack_term, cross_dist, kurt, etc.")

# Quick correlation with wind5 on train
print("\n=== New feature corr with wind5 (train) ===")
for c in ["vol_spike","log_vol_z","vol_x_ret","rb_spike","term_proxy","roll_yield","crack_term","cross_dist","kurt20"]:
    print(f" {c:16s} corr {feat.loc[train_idx, c].corr(feat.loc[train_idx,'wind5']):+.3f} valid {feat.loc[valid_idx, c].corr(feat.loc[valid_idx,'wind5']):+.3f}")

# Train CatBoost with expanded features
from catboost import CatBoostClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
def brier(y,p): return np.mean((np.array(y)-np.array(p))**2)
X_train=feat.loc[train_idx, feature_cols]
y_train=feat.loc[train_idx, "wind5"]
X_valid=feat.loc[valid_idx, feature_cols]
y_valid=feat.loc[valid_idx, "wind5"]
X_test=feat.loc[test_idx, feature_cols]
y_test=feat.loc[test_idx, "wind5"]
X_hold=feat.loc[hold_idx, feature_cols]
y_hold=feat.loc[hold_idx, "wind5"]
cat=CatBoostClassifier(depth=4, learning_rate=0.05, iterations=500, auto_class_weights='Balanced', verbose=False, random_seed=7)
cat.fit(X_train, y_train, eval_set=(X_valid, y_valid), verbose=False)
for name, X, y in [("train",X_train,y_train),("valid",X_valid,y_valid),("test",X_test,y_test),("hold",X_hold,y_hold)]:
    p=cat.predict_proba(X)[:,1]
    print(f"{name:6s} AUC {roc_auc_score(y,p):.3f} AP {average_precision_score(y,p):.3f} Brier {brier(y,p):.4f} mean {p.mean():.3f} max {p.max():.3f}")
imp=cat.get_feature_importance()
order=np.argsort(imp)[::-1]
print("\nTop 15 expanded CatBoost importance:")
for i in order[:15]:
    print(f" {feature_cols[i]:16s} {imp[i]:.1f}")
print("\nBottom 10:")
for i in order[-10:]:
    print(f" {feature_cols[i]:16s} {imp[i]:.1f}")

# Now temporal sequence model: 20-day window as flat features
# Build sequence features: for each t, take last 20 days of 5 key series as 100-dim vector
# Use HistGradientBoosting on flattened sequence
from sklearn.ensemble import HistGradientBoostingClassifier
key_series=["held","crash5","crude20","vol20","log_vol_z"]
seq_len=20
# Build seq dataset
def build_seq(feat, key_series, seq_len, idx):
    X=[]
    y=[]
    for t in idx:
        # need 20 prior days including t
        window=feat.loc[:t].iloc[-seq_len:]
        if len(window)<seq_len:
            continue
        vec=window[key_series].to_numpy().flatten()
        X.append(vec)
        y.append(int(feat.loc[t,"wind5"]))
    return np.array(X), np.array(y)

X_train_seq, y_train_seq = build_seq(feat, key_series, seq_len, train_idx)
X_valid_seq, y_valid_seq = build_seq(feat, key_series, seq_len, valid_idx)
X_test_seq, y_test_seq = build_seq(feat, key_series, seq_len, test_idx)
X_hold_seq, y_hold_seq = build_seq(feat, key_series, seq_len, hold_idx)
print(f"\nSeq train {len(X_train_seq)} valid {len(X_valid_seq)} test {len(X_test_seq)}")
if len(X_train_seq)>0:
    hgb=HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, class_weight='balanced', random_state=7)
    hgb.fit(X_train_seq, y_train_seq)
    for name, X, y in [("train",X_train_seq,y_train_seq),("valid",X_valid_seq,y_valid_seq),("test",X_test_seq,y_test_seq),("hold",X_hold_seq,y_hold_seq)]:
        p=hgb.predict_proba(X)[:,1]
        print(f"SEQ HGB {name:6s} AUC {roc_auc_score(y,p):.3f} AP {average_precision_score(y,p):.3f} Brier {brier(y,p):.4f}")
    # Compare to single-day CatBoost on same test
    p_cat_test=cat.predict_proba(X_test)[:,1]
    print(f"Single-day CatBoost test AUC {roc_auc_score(y_test, p_cat_test):.3f} for comparison")
    # Also try a simple temporal: average of last 5 crash5 etc as feature already in set, but sequence should capture shape
else:
    print("Seq build failed")

# Save feature importance for next
pd.DataFrame({"feature":feature_cols, "importance":imp}).sort_values("importance", ascending=False).to_csv(DEV/"feature_importance_expanded.csv", index=False)
print("Saved feature_importance_expanded.csv")
