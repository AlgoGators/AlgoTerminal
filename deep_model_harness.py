"""Direction 3: the deep model.

Preregistered in research/direction3_deep_model.md (e896122).
A custom 3-state Gaussian HMM (EM, sklearn kmeans init) on the
standardized deseasonalized crack_321 level; rebuilt median-based
seasonal norm; supply/demand/tech first numbers; mixture forward
model in the crush state.
"""
from __future__ import annotations

import importlib.util
import csv
from pathlib import Path

import numpy as np
import pandas as pd

ENGINE = Path("/home/sebas/algoterminal-strategy-v2/engine")
spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

from sklearn.cluster import KMeans  # noqa: E402

ROOT = Path(__file__).parent
PANEL = ENGINE / "panel_v2.parquet"
EIA = ENGINE / "eia"
WEA = ENGINE / "weather"
BLOCK = 20
WARMUP = 90
OOS = slice("2007-07-30", "2023-09-08")


def log(msg: str) -> None:
    print(msg, flush=True)


def read_csv(path: Path, col: str = "close") -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df[col].astype(float)


def sm_expanding_median(s: pd.Series, min_obs: int = 30) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        med = sub.expanding().median().shift(1)
        med[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = med
    return out


def rob_std_by_month(s: pd.Series, min_obs: int = 30) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        dev = (sub - sub.expanding().median().shift(1)).abs()
        mad = (dev * 1.4826).expanding().median().shift(1)
        mad[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = mad
    return out


def blocks_of(s: pd.Series) -> pd.Series:
    s = s.dropna()
    pos = np.arange(len(s))
    blk = pos // BLOCK
    out = {}
    for b in range(blk.max() + 1):
        seg = s[blk == b]
        if len(seg) == BLOCK:
            out[s.index[blk == b][0]] = seg.sum()
    return pd.Series(out)


def block_t(fwd_vals: pd.Series, label: str):
    if len(fwd_vals) < 5:
        log(f"  {label}: n={len(fwd_vals)} too few")
        return None
    n = len(fwd_vals)
    m = fwd_vals.mean()
    se = fwd_vals.std(ddof=1) / np.sqrt(n)
    log(f"  {label}: n={n} fwd20 {m*100:+6.2f}% t={m/se:+5.2f} "
        f"CI [{m-1.645*se:.4f},{m+1.645*se:.4f}]")
    return {"label": label, "n": n, "mean": m, "t": m / se if se else np.nan,
            "lo": m - 1.645 * se, "hi": m + 1.645 * se}


def hmm_gaussian_fit(obs: np.ndarray, n_states: int = 3, iters: int = 40, seed: int = 23):
    """Compact scaled forward-backward Gaussian HMM."""
    rng = np.random.default_rng(seed)
    T = len(obs)
    km = KMeans(n_clusters=n_states, n_init=5, random_state=seed).fit(obs.reshape(-1, 1))
    means = km.cluster_centers_.ravel().copy()
    stds = np.ones(n_states)
    A = np.full((n_states, n_states), 0.33)
    pi = np.full(n_states, 1 / n_states)
    for _ in range(iters):
        B = np.exp(-0.5 * ((obs[:, None] - means[None, :]) / stds[None, :]) ** 2) \
            / (stds[None, :] * np.sqrt(2 * np.pi)) + 1e-12
        # scaled forward
        alpha = np.zeros((T, n_states))
        alpha[0] = pi * B[0]
        scale = np.zeros(T)
        scale[0] = alpha[0].sum()
        alpha[0] /= scale[0]
        for t in range(1, T):
            alpha[t] = (alpha[t - 1] @ A) * B[t]
            scale[t] = alpha[t].sum()
            alpha[t] /= scale[t]
        beta = np.zeros((T, n_states))
        beta[-1] = 1.0
        for t in range(T - 2, -1, -1):
            beta[t] = (A @ (B[t + 1] * beta[t + 1])) / scale[t + 1]
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True)
        # xi with the CURRENT A (do not zero A before xi)
        xi = np.zeros((T - 1, n_states, n_states))
        for t in range(T - 1):
            joint = (alpha[t][:, None] * A) * B[t + 1][None, :] * beta[t + 1][None, :]
            s = joint.sum()
            if s > 0:
                joint /= s
            xi[t] = joint
        A = xi.sum(axis=0)
        A /= A.sum(axis=1, keepdims=True)
        gsum = gamma.sum(axis=0)
        means = (obs[:, None] * gamma).sum(axis=0) / gsum
        stds = np.sqrt(((obs[:, None] - means[None, :]) ** 2 * gamma).sum(axis=0) / gsum) + 1e-12
        pi = gamma[0]
    # Viterbi decode
    B = np.exp(-0.5 * ((obs[:, None] - means[None, :]) / stds[None, :]) ** 2) \
        / (stds[None, :] * np.sqrt(2 * np.pi)) + 1e-12
    T1 = np.zeros((T, n_states))
    T2 = np.zeros((T, n_states), dtype=int)
    T1[0] = np.log(pi + 1e-12) + np.log(B[0])
    for t in range(1, T):
        for j in range(n_states):
            cand = T1[t - 1] + np.log(A[:, j] + 1e-12)
            T2[t, j] = int(np.argmax(cand))
            T1[t, j] = cand[T2[t, j]] + np.log(B[t, j])
    path = np.zeros(T, dtype=int)
    path[-1] = int(np.argmax(T1[-1]))
    for t in range(T - 2, -1, -1):
        path[t] = T2[t + 1, path[t + 1]]
    return means, stds, A, path


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    oos_idx = full_idx[(full_idx >= "2007-07-30") & (full_idx < "2023-09-08")]
    lvl = levels["crack_321"]
    med = sm_expanding_median(lvl)
    rstd = rob_std_by_month(lvl)
    dz = (lvl - med).dropna()
    z_new = ((lvl - med) / rstd).clip(-8, 8)
    z_old = fb.seasonal_z(lvl)
    obs = ((dz - dz.mean()) / dz.std()).to_numpy() if len(dz) else np.array([])

    fwd20 = (lvl.shift(-20) - lvl) / b4.base_of(lvl).shift(1).replace(0.0, np.nan)
    sampled = full_idx[::20]
    rows = []

    log("=== A HMM regime identity ===")
    means, stds, A, path = hmm_gaussian_fit(obs)
    order = {s: means[s] for s in range(3)}
    names = {s: ("comp" if order[s] == min(order.values()) else "exp" if order[s] == max(order.values()) else "norm")
             for s in range(3)}
    state = pd.Series([names[p] for p in path], index=dz.index).reindex(full_idx)
    occ = state.value_counts()
    log(f"  HMM occupation: {dict(occ)}")
    trans = pd.DataFrame(A, index=range(3), columns=range(3))
    log(f"  HMM transition:\n{trans.round(3).to_string()}")
    # margin states under new z
    margin = pd.Series(np.select([z_old <= -0.75, z_old >= 0.75], ["crush", "stretch"], default="norm"),
                       index=full_idx)
    for rname, mask in (("HMM comp", state == "comp"), ("HMM comp+norm", state.isin(["comp", "norm"]))):
        m = mask & (margin == "crush") & fwd20.notna()
        sel = sampled[m.reindex(sampled).fillna(False).to_numpy(dtype=bool)]
        vals = fwd20.reindex(sel).dropna()
        r = block_t(vals, f"{rname} x crush OOS/block")
        if r:
            rows.append({"item": "hmm", **r})

    log("\n=== B rebuilt seasonal norm (median, robust scale) ===")
    margin_new = pd.Series(np.select([z_new <= -0.75, z_new >= 0.75], ["crush", "stretch"], default="norm"),
                           index=full_idx)
    log(f"  crush days old {int((margin=='crush').sum())} new {int((margin_new=='crush').sum())}; "
        f"stretch old {int((margin=='stretch').sum())} new {int((margin_new=='stretch').sum())}")
    for tag, mz in (("old", margin), ("new", margin_new)):
        m = (mz == "crush") & fwd20.notna()
        sel = sampled[m.reindex(sampled).fillna(False).to_numpy(dtype=bool)]
        vals = fwd20.reindex(sel).dropna()
        r = block_t(vals, f"crush {tag} norm OOS/block")
        if r:
            rows.append({"item": "norm", "norm": tag, **r})
    # temperature co-carrier in residual
    t2m = read_csv(WEA / "raw_T2M_NYC.csv").reindex(full_idx)
    resid = (lvl - med).dropna()
    rho = resid.corr(t2m.reindex(resid.index))
    log(f"  residual vs NYC T2M corr {rho:+.3f}")
    rows.append({"item": "temp_corr", "value": rho})

    log("\n=== C supply/demand/tech first numbers ===")
    util = read_csv(EIA / "raw_WPULEUS3.csv")
    for tag, s in (("utilization", util), ):
        y = s.resample("YE").mean()
        x = np.arange(len(y))
        slope = np.polyfit(x, y.to_numpy(), 1)[0]
        log(f"  {tag} yearly slope {slope:.2f} pts/yr (last10 {y.iloc[-1]-y.iloc[-10]:+.2f})")
        rows.append({"item": "trend", "series": tag, "slope": slope})
    gas = read_csv(EIA / "raw_WGTSTUS1.csv")
    dist = read_csv(EIA / "raw_WDISTUS1.csv")
    prod = gas + dist
    amp = {}
    for y in range(2008, 2027):
        seg = lvl.loc[f"{y}-01-01":f"{y}-12-31"]
        amp[y] = seg.groupby(seg.index.month).mean().std()
    ax = np.array(list(amp.keys()), dtype=float)
    ay = np.array(list(amp.values()), dtype=float)
    slope_amp = np.polyfit(ax, ay, 1)[0]
    log(f"  seasonal amplitude slope {slope_amp:.3f} pts/yr (level units)")
    rows.append({"item": "trend", "series": "seasonal_amplitude", "slope": slope_amp})
    ps_y = prod.resample("YE").mean()
    log(f"  product stocks 2007-09 mean {ps_y.iloc[0]:.0f} vs 2026 mean {ps_y.iloc[-1]:.0f} "
        f"(drift {ps_y.iloc[-1]-ps_y.iloc[0]:+.0f})")
    rows.append({"item": "trend", "series": "product_stocks", "drift": float(ps_y.iloc[-1]-ps_y.iloc[0])})

    log("\n=== D mixture forward in crush state ===")
    from sklearn.mixture import GaussianMixture  # noqa: PLC0415
    for tag, mz in (("crush", margin_new == "crush"), ("normal", margin_new == "norm")):
        vals = fwd20[mz & fwd20.notna()].to_numpy()
        if len(vals) < 30:
            continue
        g = GaussianMixture(n_components=2, random_state=23).fit(vals.reshape(-1, 1))
        w = g.weights_.ravel()
        m = g.means_.ravel()
        sd = np.sqrt(g.covariances_.ravel())
        p10 = float((vals > 0.10).mean())
        es5 = float(np.percentile(vals, 5))
        wl = [round(float(x), 2) for x in w]
        ml = [float(x) for x in m]
        sl = [float(x) for x in sd]
        log(f"  {tag}: w {wl} means {[round(x*100,2) for x in ml]}% stds {[round(x*100,2) for x in sl]}% "
            f"P(>10%) {p10*100:.0f}% ES5 {es5*100:.2f}%")
        rows.append({"item": "mixture", "state": tag, "w": list(w.round(3)),
                     "means": list(m.round(4)), "stds": list(sd.round(4)),
                     "p10": p10, "es5": es5})

    with open(ROOT / "results" / "direction3.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    log("\nSaved results/direction3.csv")


if __name__ == "__main__":
    main()
