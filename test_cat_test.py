import importlib.util
from pathlib import Path
import numpy as np, pandas as pd
DEV=Path("/home/sebas/algoterminal-strategy-dev")
spec=importlib.util.spec_from_file_location("b5", str(DEV/"book_oos_v5.py"))
b5=importlib.util.module_from_spec(spec); spec.loader.exec_module(b5)
spec3=importlib.util.spec_from_file_location("fb", str(DEV/"factor_book.py"))
fb=importlib.util.module_from_spec(spec3); spec3.loader.exec_module(fb)
PANEL=DEV/"panel_ext_1990.parquet"
if PANEL.exists():
    df=pd.read_parquet(PANEL).sort_index()
else:
    df=pd.read_parquet(b5.PANEL).sort_index()
levels=fb.build_levels(df)
levels["__df__"]=df
bl=b5.brent_levels(df)
for k,v in bl.items(): levels[k]=v
factors,rets,turn,legpos=b5.build_v5(levels,None,False)
net=b5.apply_costs(factors,rets,turnover=turn)
isw=net.loc[pd.Timestamp("2023-09-08"):].iloc[90:]
w=b5.weight_scheme(isw[["crack_321","cross_sectional","bzwti"]],"EQ")
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
crack_slope=levels["crack_321"].diff(20).shift(1) if "crack_321" in levels else pd.Series(0,index=df.index)
joint_raw=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
joint_raw=joint_raw.fillna(False).astype(int)
feat=pd.DataFrame({
    "held":held,"crash5":crash5,"crash10":crash10,"crash20":crash20,
    "crude20":crude20,"crude10":crude10,"crude5":crude5,
    "vol20":vol20,"vol60":vol60,"ret5":ret5,"ret20":ret20,"skew20":skew20,
    "crack_slope":crack_slope,"joint":joint_raw.astype(float),
    "held_x_crash":held*crash5,"crash_x_crude":crash5*crude20,"vol_x_crash":vol20*crash5,
    "depth_abs":held.abs(),"crude_vol":crude20.abs(),
}, index=df.index)
for lag in [1,2,3,5,10]:
    feat[f"held_lag{lag}"]=held.shift(lag)
    feat[f"crash5_lag{lag}"]=crash5.shift(lag)
feat=feat.fillna(0).clip(-8,8)
is_wind=(raw_book>0.02).astype(int)
lab5=is_wind.rolling(5,min_periods=1).max().shift(-5).fillna(0)
feat["wind5"]=lab5
train_idx=feat.index[(feat.index>="2000-08-23") & (feat.index<"2015-01-01")]
valid_idx=feat.index[(feat.index>="2015-01-01") & (feat.index<"2020-01-01")]
test_idx=feat.index[(feat.index>="2020-01-02") & (feat.index<"2023-09-08")]
hold_idx=feat.index[feat.index>=pd.Timestamp("2023-09-08")]
feature_cols=[c for c in feat.columns if c not in ["wind5"]]
from catboost import CatBoostClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
cat=CatBoostClassifier(depth=4, learning_rate=0.05, iterations=500, auto_class_weights='Balanced', verbose=False, random_seed=7)
cat.fit(feat.loc[train_idx, feature_cols], feat.loc[train_idx,"wind5"], eval_set=(feat.loc[valid_idx, feature_cols], feat.loc[valid_idx,"wind5"]), verbose=False)
for name, idx in [("train",train_idx),("valid",valid_idx),("test",test_idx),("hold",hold_idx)]:
    p=cat.predict_proba(feat.loc[idx, feature_cols])[:,1]
    y=feat.loc[idx,"wind5"]
    print(f"{name} AUC {roc_auc_score(y,p):.3f} AP {average_precision_score(y,p):.3f} mean {p.mean():.3f} max {p.max():.3f}")
imp=cat.get_feature_importance()
order=np.argsort(imp)[::-1]
print("Top 10 CatBoost importance:")
for i in order[:10]:
    print(f" {feature_cols[i]} {imp[i]:.1f}")
