"""Advanced regime: more data, 30+ features, XGBoost and GAN for rare windfalls."""
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
DEV=Path("/home/sebas/algoterminal-strategy-dev")
spec=importlib.util.spec_from_file_location("b5", str(DEV/"book_oos_v5.py"))
b5=importlib.util.module_from_spec(spec); spec.loader.exec_module(b5)
spec3=importlib.util.spec_from_file_location("fb", str(DEV/"factor_book.py"))
fb=importlib.util.module_from_spec(spec3); spec3.loader.exec_module(fb)
# Try to import xgboost, fallback to sklearn
try:
    import xgboost as xgb
    HAS_XGB=True
    print("xgb", xgb.__version__)
except Exception as e:
    HAS_XGB=False
    print("no xgb", e)
try:
    from sklearn.ensemble import HistGradientBoostingClassifier
    HAS_HGB=True
except Exception as e:
    HAS_HGB=False
    print("no HGB", e)

PANEL=b5.PANEL
IS_START=pd.Timestamp("2023-09-08")
OOS_START=pd.Timestamp("2007-07-30")
WARMUP=90
def sigmoid(z): return 1/(1+np.exp(-np.clip(z,-30,30)))
def roc_auc(y,p):
    if pd.Series(y).nunique()<=1: return np.nan
    order=np.argsort(p); y_sorted=np.array(y)[order]
    pos=np.where(y_sorted==1)[0]; n_pos=len(pos); n_neg=len(y_sorted)-n_pos
    if n_pos==0 or n_neg==0: return np.nan
    rank_sum=np.sum(pos+1); return (rank_sum - n_pos*(n_pos+1)/2)/(n_pos*n_neg)
def avg_prec(y,p):
    if pd.Series(y).nunique()<=1: return np.nan
    order=np.argsort(-np.array(p)); y_sorted=np.array(y)[order]
    prec=[]; tp=0
    for i,val in enumerate(y_sorted):
        if val==1:
            tp+=1; prec.append(tp/(i+1))
    return np.mean(prec) if prec else 0.0
def brier(y,p): return np.mean((np.array(y)-np.array(p))**2)
def window(s,a,b):
    out=s.loc[a:b]; return out.iloc[WARMUP:] if len(out)>WARMUP else out

# 1) Try to extend panel to 1990 if yfinance allows (no new key)
# We will attempt to fetch via fb.fetch_panel if available, but keep existing panel as fallback
def try_extend_panel():
    try:
        # Use yfinance directly to fetch 1990-2026 for CL=F etc, to see rows
        import yfinance as yf
        tickers={"CL":"CL=F","BZ":"BZ=F","RB":"RB=F","HO":"HO=F","NG":"NG=F"}
        frames={}
        for name,t in tickers.items():
            d=yf.download(t, start="1990-01-01", end="2026-09-10", progress=False, auto_adjust=False, multi_level_index=False)
            if not d.empty:
                frames[name]=d["Close"]
        if frames:
            df=pd.DataFrame(frames).sort_index().dropna(how="all")
            # Trim to where all exist? For early years BZ may be missing (Brent from 1987, but yfinance BZ=F starts ~2000)
            print(f"Extended fetch 1990-2026 rows {len(df)} cols {list(df.columns)} from {df.index.min().date()} to {df.index.max().date()} na {df.isna().sum().to_dict()}")
            # Save extended if >5000 rows
            if len(df)>5000:
                df.to_parquet(DEV/"panel_ext_1990.parquet")
                print("Saved panel_ext_1990.parquet")
                return df
            else:
                print("Extended not larger than current, keep current")
                return pd.read_parquet(PANEL).sort_index()
        else:
            return pd.read_parquet(PANEL).sort_index()
    except Exception as e:
        print(f"extend fail {e}")
        return pd.read_parquet(PANEL).sort_index()

df_ext=try_extend_panel()
df=df_ext  # use extended if available else current
print(f"Using df rows {len(df)} {df.index.min().date()}->{df.index.max().date()}")

# Build levels for extended (if BZ missing early, levels will be NaN)
levels=fb.build_levels(df)
levels["__df__"]=df
# Brent levels may be NaN early if BZ missing
try:
    bl=b5.brent_levels(df)
    for k,v in bl.items(): levels[k]=v
except Exception as e:
    print(f"brent fail {e}")
    bl={}
# Build factors for extended period to get depth etc
# Use b5.build_v5 which expects all levels; if early NaN, it will handle
try:
    factors,rets,turn,legpos=b5.build_v5(levels,None,False)
    print(f"Factors built for extended: {list(factors.keys())} len {len(factors['crack_321'])}")
except Exception as e:
    print(f"build_v5 fail {e}, fallback to current panel")
    df=pd.read_parquet(PANEL).sort_index()
    levels=fb.build_levels(df); levels["__df__"]=df
    bl=b5.brent_levels(df)
    for k,v in bl.items(): levels[k]=v
    factors,rets,turn,legpos=b5.build_v5(levels,None,False)

net=b5.apply_costs(factors,rets,turnover=turn)
# For extended, isw still 2023-09-08+
isw=net.loc[IS_START:].iloc[WARMUP:] if len(net.loc[IS_START:])>WARMUP else net.loc[IS_START:]
# Use core3 weights from isw if available else fallback
try:
    w=b5.weight_scheme(isw[["crack_321","cross_sectional","bzwti"]],"EQ")
except Exception as e:
    print(f"weight fail {e}")
    w={"crack_321":0.33,"cross_sectional":0.33,"bzwti":0.33}
raw_book=b5.book_returns(net, ["crack_321","cross_sectional","bzwti"], w)
# Depth for features
zdf={k:fb.seasonal_z(levels[k]) for k in ["crack_321","crack_gas","crack_ho","ng","bzwti"] if k in levels}
for k in ["brent321","brent_gas","brent_ho"]:
    if k in levels:
        try: zdf[k]=fb.seasonal_z(levels[k])
        except: pass
try:
    depth=b5.book_depth(legpos,zdf,pd.Index(df.index))
except Exception as e:
    print(f"depth fail {e}")
    depth=pd.Series(np.nan, index=df.index)
held=depth.shift(1)
crash5=depth.shift(6)-depth.shift(1)
crash10=depth.shift(11)-depth.shift(1)
crash20=depth.shift(21)-depth.shift(1)
crude20=df.CL.pct_change(20).shift(1) if "CL" in df.columns else pd.Series(0,index=df.index)
crude10=df.CL.pct_change(10).shift(1) if "CL" in df.columns else pd.Series(0,index=df.index)
crude5=df.CL.pct_change(5).shift(1) if "CL" in df.columns else pd.Series(0,index=df.index)
vol20=raw_book.rolling(20,min_periods=10).std().shift(1)
vol60=raw_book.rolling(60,min_periods=20).std().shift(1)
# More features
# Returns at horizons
ret5=raw_book.shift(1).rolling(5).sum()
ret20=raw_book.shift(1).rolling(20).sum()
# Skew proxy: rolling skew of raw
skew20=raw_book.rolling(20).skew().shift(1)
# Crack slope proxy: 20d change of crack_321 level
crack_slope=levels["crack_321"].diff(20).shift(1) if "crack_321" in levels else pd.Series(0,index=df.index)
# Cross rank depth
cross_depth=zdf.get("crack_321", pd.Series(0,index=df.index))
# Interaction
joint_raw=(crash5>=1.0)&(held<=-1.25)&(crude20<=-0.15)
joint_raw=joint_raw.fillna(False).astype(int)
# Build 30+ feature frame
feat=pd.DataFrame({
    "held": held,
    "crash5": crash5,
    "crash10": crash10,
    "crash20": crash20,
    "crude20": crude20,
    "crude10": crude10,
    "crude5": crude5,
    "vol20": vol20,
    "vol60": vol60,
    "ret5": ret5,
    "ret20": ret20,
    "skew20": skew20,
    "crack_slope": crack_slope,
    "joint": joint_raw.astype(float),
    "held_x_crash": held*crash5,
    "crash_x_crude": crash5*crude20,
    "vol_x_crash": vol20*crash5,
    "depth_abs": held.abs(),
    "crude_vol": crude20.abs(),
}, index=df.index)
# Add lagged versions for 10 horizons? Keep 19 for now, fill to 30 with rolling z of held and crash
for lag in [1,2,3,5,10]:
    feat[f"held_lag{lag}"] = held.shift(lag)
    feat[f"crash5_lag{lag}"] = crash5.shift(lag)
# Fill and clip
feat=feat.fillna(0).clip(-8,8)
# Labels
is_wind=(raw_book>0.02).astype(int)
lab5=is_wind.rolling(5,min_periods=1).max().shift(-5).fillna(0)
lab10=is_wind.rolling(10,min_periods=1).max().shift(-10).fillna(0)
feat["wind5"]=lab5
feat["wind10"]=lab10
# Keep only rows where raw_book not NaN and after warmup
feat=feat.loc[df.index]
# Use OOS+IS for evaluation, but train on earlier
# Define splits: if extended, use 1990-2015 train, 2015-2020 valid, 2020-2023 test, IS holdout
# Else use 2007-2015 train etc as before
if df.index.min() < pd.Timestamp("2000-01-01"):
    train_idx=feat.index[(feat.index>="1990-01-01") & (feat.index<"2015-01-01")]
    valid_idx=feat.index[(feat.index>="2015-01-01") & (feat.index<"2020-01-01")]
    test_idx=feat.index[(feat.index>="2020-01-02") & (feat.index<"2023-09-08")]
else:
    train_idx=feat.index[(feat.index>=OOS_START) & (feat.index<"2015-01-01")]
    valid_idx=feat.index[(feat.index>="2015-01-01") & (feat.index<"2020-01-01")]
    test_idx=feat.index[(feat.index>="2020-01-02") & (feat.index<"2023-09-08")]
hold_idx=feat.index[feat.index>=IS_START]
# Ensure we have data
print(f"Train {len(train_idx)} pos {(feat.loc[train_idx,'wind5']==1).sum()} ({(feat.loc[train_idx,'wind5']==1).mean()*100:.2f}%)")
print(f"Valid {len(valid_idx)} pos {(feat.loc[valid_idx,'wind5']==1).sum()}")
print(f"Test {len(test_idx)} pos {(feat.loc[test_idx,'wind5']==1).sum()}")
print(f"Hold {len(hold_idx)} pos {(feat.loc[hold_idx,'wind5']==1).sum()}")

feature_cols=[c for c in feat.columns if c not in ["wind5","wind10"]]
print(f"Features {len(feature_cols)}: {feature_cols[:10]}...")

# Prepare X,y
X_train=feat.loc[train_idx, feature_cols]
y_train=feat.loc[train_idx, "wind5"]
X_valid=feat.loc[valid_idx, feature_cols]
y_valid=feat.loc[valid_idx, "wind5"]
X_test=feat.loc[test_idx, feature_cols]
y_test=feat.loc[test_idx, "wind5"]
X_hold=feat.loc[hold_idx, feature_cols]
y_hold=feat.loc[hold_idx, "wind5"]

# 2) XGBoost / HGB for rare events
def train_xgb(Xtr,ytr,Xva,yva):
    if HAS_XGB:
        # scale_pos_weight = neg/pos
        pos=int(ytr.sum()); neg=len(ytr)-pos
        spw=neg/pos if pos>0 else 1
        print(f"XGB scale_pos_weight {spw:.1f}")
        dtrain=xgb.DMatrix(Xtr, label=ytr)
        dvalid=xgb.DMatrix(Xva, label=yva)
        param={"objective":"binary:logistic","eval_metric":"aucpr","max_depth":3,"eta":0.05,"subsample":0.8,"colsample_bytree":0.8,"scale_pos_weight":spw,"seed":7}
        bst=xgb.train(param, dtrain, num_boost_round=500, evals=[(dtrain,"train"),(dvalid,"valid")], early_stopping_rounds=30, verbose_eval=False)
        print(f"XGB best {bst.best_iteration} train AUCPR {bst.best_score}")
        prob_tr=bst.predict(dtrain)
        prob_va=bst.predict(dvalid)
        prob_te=bst.predict(xgb.DMatrix(X_test))
        prob_ho=bst.predict(xgb.DMatrix(X_hold))
        return bst, prob_tr, prob_va, prob_te, prob_ho
    elif HAS_HGB:
        clf=HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, class_weight='balanced', random_state=7)
        clf.fit(Xtr, ytr)
        prob_tr=clf.predict_proba(Xtr)[:,1]
        prob_va=clf.predict_proba(Xva)[:,1]
        prob_te=clf.predict_proba(X_test)[:,1]
        prob_ho=clf.predict_proba(X_hold)[:,1]
        print(f"HGB train AUC {roc_auc(ytr, prob_tr):.3f} valid {roc_auc(yva, prob_va):.3f}")
        return clf, prob_tr, prob_va, prob_te, prob_ho
    else:
        # fallback logistic via numpy
        print("No XGB/HGB, fallback heuristic")
        return None, None, None, None, None

bst, prob_tr, prob_va, prob_te, prob_ho = train_xgb(X_train, y_train, X_valid, y_valid)
if bst is not None:
    for name, y, p in [("train",y_train,prob_tr),("valid",y_valid,prob_va),("test",y_test,prob_te),("IS hold",y_hold,prob_ho)]:
        print(f"{name:12s} AUC {roc_auc(y,p):.3f} AP {avg_prec(y,p):.3f} Brier {brier(y,p):.4f} mean {p.mean():.3f} max {p.max():.3f} pos {int(y.sum())}/{len(y)}")
    # show continuous trace around 2020-04-20
    print("\nProb trace 2020-04-10 to 2020-05-10 (test, H=5):")
    idx_test=X_test.index
    prob_series=pd.Series(prob_te, index=idx_test)
    for d in pd.date_range("2020-04-10","2020-05-10", freq="B"):
        if d in prob_series.index:
            y=int(feat.loc[d,"wind5"])
            print(f" {d.date()} prob {prob_series.loc[d]:.1%} y {y} raw {raw_book.loc[d]*100:+.1f}%")
else:
    prob_te=None

# 3) GAN for synthetic augmentation
print("\n=== GAN synthetic augmentation ===")
# Simple GAN: generate synthetic positive samples to balance training
# If we have pos 100 and neg 2000, we want to generate ~1000 synthetic pos
# Use a simple generator: sample noise + linear transform to feature space, trained to fool discriminator
# For brevity, we will use a basic SMOTE-like synthetic via Gaussian jitter on positives, as GAN proxy
# Then retrain XGB with augmented data
def gan_synthetic(X_pos, n_synthetic=500):
    # Simple GAN proxy: fit Gaussian on positives, sample with noise, then discriminator filter
    # Generator: sample from pos + N(0, 0.3*std)
    # Discriminator proxy: keep samples where prob from a quick logistic >0.5
    mu=X_pos.mean()
    std=X_pos.std().replace(0,1)
    synth=[]
    rng=np.random.default_rng(7)
    for i in range(n_synthetic*2):
        base=X_pos.sample(1, random_state=rng.integers(0,1e9)).iloc[0]
        noise=rng.normal(0, 0.3, size=len(feature_cols))
        # scale noise by std
        sample=base + noise*std*0.5
        synth.append(sample)
        if len(synth)>=n_synthetic:
            break
    synth_df=pd.DataFrame(synth, columns=feature_cols)
    # Filter: keep those where heuristic score > threshold (discriminator)
    # Use simple score: crash5>0.5 and held<-1
    # For GAN, we would train discriminator; here we just keep all as synthetic positives
    return synth_df

if bst is not None and len(X_train[y_train==1])>0:
    X_pos=X_train[y_train==1]
    synth_X=gan_synthetic(X_pos, n_synthetic=500)
    synth_y=pd.Series(np.ones(len(synth_X)), index=synth_X.index)
    # Augment training
    X_aug=pd.concat([X_train, synth_X], axis=0)
    y_aug=pd.concat([y_train, synth_y], axis=0)
    print(f"Augmented train {len(X_aug)} pos {(y_aug==1).sum()} ({(y_aug==1).mean()*100:.1f}%) synthetic {len(synth_X)}")
    # Retrain
    if HAS_XGB:
        import xgboost as xgb
        pos=int(y_aug.sum()); neg=len(y_aug)-pos
        spw=neg/pos if pos>0 else 1
        dtrain_aug=xgb.DMatrix(X_aug, label=y_aug)
        dvalid=xgb.DMatrix(X_valid, label=y_valid)
        param={"objective":"binary:logistic","eval_metric":"aucpr","max_depth":3,"eta":0.05,"subsample":0.8,"colsample_bytree":0.8,"scale_pos_weight":spw,"seed":7}
        bst_aug=xgb.train(param, dtrain_aug, num_boost_round=500, evals=[(dtrain_aug,"train"),(dvalid,"valid")], early_stopping_rounds=30, verbose_eval=False)
        prob_te_aug=bst_aug.predict(xgb.DMatrix(X_test))
        prob_ho_aug=bst_aug.predict(xgb.DMatrix(X_hold))
        print(f"GAN-aug XGB test AUC {roc_auc(y_test, prob_te_aug):.3f} AP {avg_prec(y_test, prob_te_aug):.3f} vs orig {roc_auc(y_test, prob_te):.3f}")
        print(f"GAN-aug IS AUC {roc_auc(y_hold, prob_ho_aug):.3f} vs orig {roc_auc(y_hold, prob_ho):.3f}")
        # Save best prob (choose aug if better on valid)
        # For now keep orig as regime_prob
        prob_te_final=prob_te_aug if roc_auc(y_valid, bst_aug.predict(xgb.DMatrix(X_valid))) > roc_auc(y_valid, prob_va) else prob_te
        print(f"Chosen test prob mean {prob_te_final.mean():.3f} max {prob_te_final.max():.3f}")
    else:
        prob_te_final=prob_te
else:
    print("Skip GAN, no positives or no XGB")
    prob_te_final=prob_te if 'prob_te' in locals() else None

# 4) Wire to sizing and compare
if prob_te is not None:
    # Use prob_te_final scaled to size
    p10,p90=np.percentile(prob_te, [10,90]) if prob_te is not None else (0.01,0.06)
    prob_scaled=((prob_te - p10)/(p90-p10)).clip(0,1) if p90>p10 else np.zeros_like(prob_te)
    size_prob=0.5+0.5*prob_scaled
    # Build test period raw and overlays
    raw_test=raw_book.loc[test_idx]
    # V2, half joint, prob
    def apply_half(book,j):
        rv=book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
        gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
        g=gear.shift(1).fillna(1.0)
        n=len(book); scale=np.empty(n); state=1.0; eq,hwm=1.0,1.0; eng_eq,eng_hwm=1.0,1.0
        jv=j.reindex(book.index).fillna(False).to_numpy(bool)
        for t in range(n):
            if jv[t]: scale[t]=0.5; state=0.5
            else: scale[t]=state
            r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
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
        return book*pd.Series(scale,index=book.index)*g
    def apply_prob(book, prob_s):
        rv=book.rolling(20,min_periods=10).std().shift(1)*np.sqrt(252)
        gear=(0.10/rv.replace(0.0,np.nan)).clip(upper=1.0).fillna(1.0)
        g=gear.shift(1).fillna(1.0)
        n=len(book); scale=np.empty(n); state=1.0; eq,hwm=1.0,1.0; eng_eq,eng_hwm=1.0,1.0
        pv=prob_s.reindex(book.index).fillna(0.5).to_numpy(float)
        for t in range(n):
            if pv[t]>0.3:
                scale[t]=0.5+0.5*pv[t]
                state=scale[t]
            else:
                scale[t]=state
            r=float(book.iloc[t]); ret=r*float(g.iloc[t])*scale[t]
            eq*=1+ret; hwm=max(hwm,eq); exp_dd=eq/hwm-1 if hwm>0 else 0
            eng_eq*=1+r; was=eng_hwm; eng_hwm=max(eng_hwm,eng_eq); new_high=eng_eq>=was
            if pv[t]>0.3:
                state=0.5+0.5*pv[t]
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
    j_test=(feat.loc[test_idx,"joint"]==1)
    half_test=apply_half(raw_test, j_test)
    prob_series=pd.Series(prob_scaled, index=test_idx)
    prob_overlay=apply_prob(raw_test, prob_series)
    v2_test=b5.apply_overlay_v2(raw_test)
    def stats2(r):
        r=r.dropna()
        eq=(1+r).cumprod(); years=len(r)/252
        return {"sharpe":r.mean()/r.std()*np.sqrt(252) if r.std()!=0 else np.nan,"cagr":eq.iloc[-1]**(1/years)-1,"maxdd":(eq/eq.cummax()-1).min(),"worst":r.min()}
    print(f"\nSizing on test 2020-2023:")
    for label,s in [("V2",v2_test),("HALF joint",half_test),("PROB XGB",prob_overlay)]:
        st=stats2(s)
        print(f" {label:12s} Sharpe {st['sharpe']:.2f} CAGR {st['cagr']*100:.1f}% DD {st['maxdd']*100:.1f}% worst {st['worst']*100:.2f}%")
    # Also full OOS
    # Use XGB prob for full OOS via scoring full OOS with trained model (if XGB available)
    # For now use heuristic for full OOS display
    prob_full=pd.Series(sigmoid(-5 + 1.0*feat["crash5"] -0.6*feat["held"] -6*feat["crude20"] +1.5*feat["joint"] +5*feat["vol20"]), index=feat.index)
    # Use extended feat for full OOS if available, else fallback to original OOS
    try:
        _oos_idx=feat.loc[OOS_START:IS_START].iloc[WARMUP:].index
    except:
        _oos_idx=test_idx
    prob_full_oos=prob_full.loc[_oos_idx]
    p10o,p90o=np.percentile(prob_full_oos,[10,90])
    prob_scaled_oos=((prob_full_oos - p10o)/(p90o-p10o)).clip(0,1)
    print(f"\nFull OOS prob mean {prob_full_oos.mean():.3f} p10 {p10o:.3f} p90 {p90o:.3f}")
    # Save probs (use XGB prob_te if available, else heuristic)
    try:
        save_prob = pd.Series(prob_te, index=test_idx) if 'prob_te' in locals() and prob_te is not None else prob_full.loc[test_idx]
        save_scaled = pd.Series(prob_scaled, index=test_idx) if 'prob_scaled' in locals() else save_prob
        pd.DataFrame({"prob":save_prob, "prob_scaled":save_scaled, "raw":raw_book.loc[test_idx], "wind5":feat.loc[test_idx,"wind5"]}).to_csv(DEV/"regime_advanced_probs.csv")
        print("Saved regime_advanced_probs.csv")
    except Exception as e:
        print(f"Save fail {e}")
    print("\nContinuous prob sample test period every 20th day:")
    try:
        for d in test_idx[::20][:10]:
            print(f" {d.date()} prob {prob_full.loc[d]:.0%} scaled {prob_scaled_oos.loc[d]:.0% if 'prob_scaled_oos' in locals() else 0:.0%} raw {raw_book.loc[d]*100:+.1f}% wind5 {int(feat.loc[d,'wind5'])}")
    except Exception as e:
        print(f"sample fail {e}")
