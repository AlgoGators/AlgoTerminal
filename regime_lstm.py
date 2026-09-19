"""LSTM for windfall regime: 20-day sequence of 7 key features."""
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
    import torch
    import torch.nn as nn
    HAS_TORCH=True
    print(f"torch {torch.__version__}")
except Exception as e:
    HAS_TORCH=False
    print(f"no torch {e}")

PANEL=DEV/"panel_ext_1990.parquet"
if PANEL.exists():
    df=pd.read_parquet(PANEL).sort_index()
else:
    df=pd.read_parquet(b5.PANEL).sort_index()
print(f"df {len(df)} {df.index.min().date()}->{df.index.max().date()}")
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
crude20=df.CL.pct_change(20).shift(1) if "CL" in df.columns else pd.Series(0,index=df.index)
vol20=raw_book.rolling(20,min_periods=10).std().shift(1)
# volume features
vol_df=None
if (DEV/"panel_vol.parquet").exists():
    vol_df=pd.read_parquet(DEV/"panel_vol.parquet").sort_index().reindex(df.index)
    cl_vol=vol_df["CL"] if "CL" in vol_df.columns else pd.Series(0,index=df.index)
    vol_mean20=cl_vol.rolling(20,min_periods=10).mean().shift(1)
    vol_spike=(cl_vol / vol_mean20.replace(0,np.nan)).fillna(1).clip(0,5)
    vol_x_ret=vol_spike * raw_book.shift(1).abs()
else:
    vol_x_ret=pd.Series(0,index=df.index)
crack_slope=levels["crack_321"].diff(20).shift(1) if "crack_321" in levels else pd.Series(0,index=df.index)
crack_term=(levels["crack_321"] - levels["crack_321"].rolling(60).mean()).shift(1) / levels["crack_321"].shift(1).replace(0,np.nan) if "crack_321" in levels else pd.Series(0,index=df.index)
crack_term=crack_term.fillna(0).clip(-0.5,0.5)
# Key series for LSTM: choose top from importance: vol20, crack_slope, vol_x_ret, crack_term, held, crash5, crude20
key_cols=["held","crash5","crude20","vol20","vol_x_ret","crack_slope","crack_term"]
feat=pd.DataFrame({
    "held":held,"crash5":crash5,"crude20":crude20,"vol20":vol20,
    "vol_x_ret":vol_x_ret,"crack_slope":crack_slope,"crack_term":crack_term,
}, index=df.index).fillna(0).clip(-8,8)
is_wind=(raw_book>0.02).astype(int)
lab5=is_wind.rolling(5,min_periods=1).max().shift(-5).fillna(0)
feat["wind5"]=lab5
# splits
train_idx=feat.index[(feat.index>="2000-08-23") & (feat.index<"2015-01-01")]
valid_idx=feat.index[(feat.index>="2015-01-01") & (feat.index<"2020-01-01")]
test_idx=feat.index[(feat.index>="2020-01-02") & (feat.index<"2023-09-08")]
hold_idx=feat.index[feat.index>=pd.Timestamp("2023-09-08")]
print(f"Train {len(train_idx)} pos {(feat.loc[train_idx,'wind5']==1).sum()} valid {len(valid_idx)} test {len(test_idx)} hold {len(hold_idx)}")
SEQ_LEN=20
def build_seq(idx):
    X=[]; y=[]
    # need at least SEQ_LEN prior rows
    for t in idx:
        # get 20 prior days ending at t
        window=feat.loc[:t].iloc[-SEQ_LEN:]
        if len(window)<SEQ_LEN:
            continue
        # check no NaN in key cols
        if window[key_cols].isna().any().any():
            continue
        X.append(window[key_cols].to_numpy(dtype=np.float32))
        y.append(int(feat.loc[t,"wind5"]))
    return np.array(X), np.array(y)

X_train, y_train = build_seq(train_idx)
X_valid, y_valid = build_seq(valid_idx)
X_test, y_test = build_seq(test_idx)
X_hold, y_hold = build_seq(hold_idx)
print(f"Seq shapes train {X_train.shape} {y_train.sum()} valid {X_valid.shape} test {X_test.shape} hold {X_hold.shape}")

def roc_auc(y,p):
    if len(np.unique(y))<=1: return np.nan
    order=np.argsort(p); y_sorted=y[order]
    pos=np.where(y_sorted==1)[0]; n_pos=len(pos); n_neg=len(y_sorted)-n_pos
    if n_pos==0 or n_neg==0: return np.nan
    rank_sum=np.sum(pos+1); return (rank_sum - n_pos*(n_pos+1)/2)/(n_pos*n_neg)
def avg_prec(y,p):
    if len(np.unique(y))<=1: return np.nan
    order=np.argsort(-p); y_sorted=y[order]
    prec=[]; tp=0
    for i,val in enumerate(y_sorted):
        if val==1:
            tp+=1; prec.append(tp/(i+1))
    return np.mean(prec) if prec else 0.0
def brier(y,p): return np.mean((y-p)**2)

if not HAS_TORCH:
    print("No torch, fallback to HGB on flattened seq already did 0.638, skip LSTM")
    # Still show that LSTM would need torch
    import sys; sys.exit(0)

# LSTM model
class LSTMRegime(nn.Module):
    def __init__(self, input_dim=7, hidden_dim=16, num_layers=1, dropout=0.2):
        super().__init__()
        self.lstm=nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.0)
        self.fc=nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(16, 1)
        )
    def forward(self, x):
        # x: (batch, seq, dim)
        out, (h_n, c_n)=self.lstm(x)
        # take last hidden
        last=out[:,-1,:]
        logit=self.fc(last).squeeze(-1)
        return logit

device=torch.device("cpu")
model=LSTMRegime(input_dim=len(key_cols), hidden_dim=16, num_layers=1, dropout=0.2).to(device)
criterion=nn.BCEWithLogitsLoss(pos_weight=torch.tensor([ (len(y_train)-y_train.sum())/max(y_train.sum(),1) ], dtype=torch.float32))
optimizer=torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-4)
scheduler=torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=5)

# Data loaders
from torch.utils.data import TensorDataset, DataLoader
train_ds=TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train.astype(np.float32)))
valid_ds=TensorDataset(torch.from_numpy(X_valid), torch.from_numpy(y_valid.astype(np.float32)))
train_loader=DataLoader(train_ds, batch_size=64, shuffle=True)
valid_loader=DataLoader(valid_ds, batch_size=256, shuffle=False)

best_auc=0
best_state=None
patience=10
bad=0
for epoch in range(60):
    model.train()
    for xb, yb in train_loader:
        xb, yb = xb.to(device), yb.to(device)
        optimizer.zero_grad()
        logit=model(xb)
        loss=criterion(logit, yb)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
    # eval valid
    model.eval()
    with torch.no_grad():
        # train AUC for monitoring
        all_p=[]
        all_y=[]
        for xb, yb in DataLoader(TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train.astype(np.float32))), batch_size=512):
            all_p.append(torch.sigmoid(model(xb.to(device))).cpu().numpy())
            all_y.append(yb.numpy())
        p_train=np.concatenate(all_p); y_train_np=np.concatenate(all_y)
        auc_train=roc_auc(y_train_np, p_train)
        # valid
        all_p=[]; all_y=[]
        for xb, yb in valid_loader:
            all_p.append(torch.sigmoid(model(xb.to(device))).cpu().numpy())
            all_y.append(yb.numpy())
        p_valid=np.concatenate(all_p); y_valid_np=np.concatenate(all_y)
        auc_valid=roc_auc(y_valid_np, p_valid)
        ap_valid=avg_prec(y_valid_np, p_valid)
    scheduler.step(auc_valid)
    print(f"Epoch {epoch+1:2d} train AUC {auc_train:.3f} valid AUC {auc_valid:.3f} AP {ap_valid:.3f}")
    if auc_valid > best_auc + 0.001:
        best_auc=auc_valid
        best_state={k:v.cpu() for k,v in model.state_dict().items()}
        bad=0
    else:
        bad+=1
        if bad>=patience:
            print(f"Early stop at {epoch+1} best {best_auc:.3f}")
            break

if best_state is not None:
    model.load_state_dict(best_state)

# Evaluate on test and hold
model.eval()
with torch.no_grad():
    for name, X, y in [("train",X_train,y_train),("valid",X_valid,y_valid),("test",X_test,y_test),("hold",X_hold,y_hold)]:
        loader=DataLoader(TensorDataset(torch.from_numpy(X), torch.from_numpy(y.astype(np.float32))), batch_size=512)
        all_p=[]
        for xb, _ in loader:
            all_p.append(torch.sigmoid(model(xb.to(device))).cpu().numpy())
        p=np.concatenate(all_p)
        print(f"{name:6s} LSTM AUC {roc_auc(y,p):.3f} AP {avg_prec(y,p):.3f} Brier {brier(y,p):.4f} mean {p.mean():.3f} max {p.max():.3f} pos {int(y.sum())}/{len(y)}")
        if name=="test":
            # save trace around 2020-04-20
            # need to map test idx to dates
            # X_test corresponds to test_idx filtered to those with seq len 20, so we need to reconstruct dates
            # For simplicity, show few probs
            idx_test_seq=[]
            for t in test_idx:
                window=feat.loc[:t].iloc[-SEQ_LEN:]
                if len(window)>=SEQ_LEN and not window[key_cols].isna().any().any():
                    idx_test_seq.append(t)
            idx_test_seq=pd.Index(idx_test_seq)
            ser=pd.Series(p, index=idx_test_seq)
            print("\nLSTM prob trace 2020-04-10 to 2020-05-10:")
            for d in pd.date_range("2020-04-10","2020-05-08", freq="B"):
                if d in ser.index:
                    yv=int(feat.loc[d,"wind5"])
                    print(f" {d.date()} prob {ser.loc[d]:.1%} y {yv} raw {raw_book.loc[d]*100:+.1f}%")
            # also show 2019 bleed
            print("\nLSTM 2019 bleed:")
            for d in pd.date_range("2019-08-01","2019-08-14", freq="B"):
                if d in ser.index:
                    print(f" {d.date()} prob {ser.loc[d]:.1%} y {int(feat.loc[d,'wind5'])}")
            # Save
            pd.DataFrame({"prob":ser, "wind5":feat.loc[ser.index,"wind5"], "raw":raw_book.loc[ser.index]}).to_csv(DEV/"regime_lstm_probs.csv")
            print("Saved regime_lstm_probs.csv")
            # Compare to single-day CatBoost test 0.735 vs LSTM
            # Also compute prob buckets
            y_test_np=y
            p_test=p
            bins=[0,0.02,0.05,0.10,0.20,0.5,1.0]
            print("\nLSTM buckets vs actual wind rate test:")
            for lo,hi in zip(bins[:-1],bins[1:]):
                m=(p_test>=lo)&(p_test<hi)
                if m.sum()>0:
                    print(f" {lo:.0%}-{hi:.0%} n={int(m.sum())} meanProb {p_test[m].mean():.1%} actual {y_test_np[m].mean():.1%}")
            # Sizing comparison on test period
            # Use prob scaled to size as before
            p10,p90=np.percentile(p, [10,90])
            prob_scaled=((p - p10)/(p90-p10)).clip(0,1) if p90>p10 else np.zeros_like(p)
            # Build raw_test for sizing
            raw_test=raw_book.loc[idx_test_seq]
            # V2, half joint, LSTM prob
            # For half joint, need joint series
            depth_series=depth.loc[idx_test_seq]
            # Use half joint logic quickly
            # We'll just report that LSTM sizing would be evaluated similarly to before
            # For brevity, just stats of prob wiring would be similar to before
            print(f"\nLSTM p10 {p10:.3f} p90 {p90:.3f} mean {p.mean():.3f}")
