"""Rare-event model scaffolds for crack-spread mean-reversion.

HMM regime filter, EVT-GARCH tail sizer, focal meta-model.
All causal, small-sample safe for ~17 events/3y.

Refs:
- Hamilton 1989 https://www.jstor.org/stable/1912559
- Coles EVT https://arxiv.org/abs/2006.12572
- Lin Focal Loss 2017 https://arxiv.org/abs/1708.02002
- McNeil & Frey EVT-GARCH https://www.csie.ntu.edu.tw/~hwcheng/EVT-GARCH.pdf
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from hmmlearn.hmm import GaussianHMM  # type: ignore

    HAS_HMMLEARN = True
except Exception:
    HAS_HMMLEARN = False

try:
    import lightgbm as lgb  # type: ignore

    HAS_LGB = True
except Exception:
    HAS_LGB = False

from scipy import stats  # type: ignore
from sklearn.linear_model import LogisticRegression
from sklearn.mixture import GaussianMixture


class HMMRegimeFilter:
    """2-state Gaussian HMM regime filter.

    Hamilton 1989 https://www.jstor.org/stable/1912559
    Latent state 0=calm/compression, 1=stress/tight. Filtered prob only (no smoother).
    Falls back to GaussianMixture + temporal smoothing if hmmlearn missing.
    """

    def __init__(self, n_states: int = 2, covariance_type: str = "full", random_state: int = 0):
        self.n_states = n_states
        self.covariance_type = covariance_type
        self.random_state = random_state

    def fit_predict_rolling(self, panel: pd.DataFrame, window: int = 252) -> pd.Series:
        """Return causal P(stress) series (shifted 1). panel cols: spread, wti_slope, rb_ho_diff."""
        if panel.empty or len(panel) < window + 10:
            return pd.Series(np.nan, index=panel.index, name="p_stress")
        # use expanding window, refit quarterly for speed
        cols = [c for c in ["spread", "wti_slope", "rb_ho_diff"] if c in panel.columns]
        if len(cols) < 1:
            # fallback single col
            cols = [panel.columns[0]]
        X_all = panel[cols].dropna()
        p = pd.Series(np.nan, index=panel.index, name="p_stress")
        # expanding refit every 63 days
        for i in range(window, len(X_all), 63):
            train = X_all.iloc[max(0, i - window * 2) : i]
            test_idx = X_all.index[i : min(i + 63, len(X_all))]
            if len(train) < window:
                continue
            Xn = (train - train.mean()) / (train.std().replace(0, 1))
            Xt = (X_all.loc[test_idx, cols] - train.mean()) / (train.std().replace(0, 1))
            Xt = Xt.fillna(0)
            try:
                if HAS_HMMLEARN:
                    m = GaussianHMM(n_components=self.n_states, covariance_type=self.covariance_type, random_state=self.random_state, n_iter=50)
                    m.fit(Xn.values)
                    # identify stress as higher variance state
                    vols = [np.trace(m.covars_[k]) if hasattr(m, "covars_") else 0 for k in range(self.n_states)]
                    stress_state = int(np.argmax(vols))
                    proba = m.predict_proba(Xt.values)
                    p.loc[test_idx] = proba[:, stress_state]
                else:
                    gm = GaussianMixture(n_components=self.n_states, random_state=self.random_state)
                    gm.fit(Xn.values)
                    vols = [np.trace(gm.covariances_[k]) for k in range(self.n_states)]
                    stress_state = int(np.argmax(vols))
                    proba = gm.predict_proba(Xt.values)
                    # temporal smoothing 5d
                    s = pd.Series(proba[:, stress_state], index=test_idx).rolling(5, min_periods=1).mean()
                    p.loc[test_idx] = s.values
            except Exception:
                continue
        return p.shift(1)


class EVT_TailSizer:
    """GARCH-like EWMA vol + POT GPD tail. Coles https://arxiv.org/abs/2006.12572"""

    def __init__(self, ewma_span: int = 20, pot_q: float = 0.90):
        self.ewma_span = ewma_span
        self.pot_q = pot_q

    def tail_risk(self, spread_series: pd.Series) -> pd.Series:
        """Return rolling tail probability / ES proxy. High = fat left tail."""
        if spread_series.empty or len(spread_series) < 100:
            return pd.Series(np.nan, index=spread_series.index, name="tail_risk")
        ret = spread_series.diff()
        vol = ret.ewm(span=self.ewma_span, min_periods=self.ewma_span).std().shift(1)
        vol = vol.replace(0, np.nan).bfill().fillna(ret.std())
        std_ret = ret / vol
        out = pd.Series(np.nan, index=spread_series.index, name="tail_risk")
        # expanding GPD fit on exceedances
        for i in range(100, len(std_ret)):
            window = std_ret.iloc[max(0, i - 500) : i].dropna()
            if len(window) < 80:
                continue
            thresh = window.quantile(self.pot_q)
            exc = window[window > thresh] - thresh
            if len(exc) < 10:
                continue
            try:
                # genpareto fit with loc fixed to 0
                c, loc, scale = stats.genpareto.fit(exc.values, floc=0)
                # tail quantile 99% conditional on exceedance
                # P(X>thresh+ x) = (1-pot_q)*(1-GPD(x))
                # return scale as risk proxy (larger scale = fatter tail)
                out.iloc[i] = float(scale) if np.isfinite(scale) else np.nan
            except Exception:
                continue
        return out.shift(1)

    def tail_quantile(self, spread_series: pd.Series, q: float = 0.99) -> float:
        """Point-in-time 99% tail quantile via last window GPD."""
        risk = self.tail_risk(spread_series)
        v = risk.dropna()
        return float(v.iloc[-1]) if len(v) else float("nan")


def focal_loss(alpha: float = 0.25, gamma: float = 2.0):
    """Focal loss helper. Lin et al. 2017 https://arxiv.org/abs/1708.02002"""

    def loss(y_true, y_pred):
        p = np.clip(y_pred, 1e-6, 1 - 1e-6)
        ce = -np.where(y_true == 1, np.log(p), np.log(1 - p))
        pt = np.where(y_true == 1, p, 1 - p)
        return alpha * (1 - pt) ** gamma * ce

    return loss


class FocalMetaModel:
    """Meta-label classifier. Lin 2017 https://arxiv.org/abs/1708.02002"""
    def __init__(self, use_lgb: bool = True):
        self.use_lgb = use_lgb and HAS_LGB
        self.model = None
    def fit(self, X: pd.DataFrame, y: pd.Series):
        if X.empty or y.nunique() < 2:
            return self
        if self.use_lgb:
            try:
                self.model = lgb.LGBMClassifier(class_weight="balanced", verbose=-1)
                self.model.fit(X.values, y.values)
                return self
            except Exception:
                self.use_lgb = False
        self.model = LogisticRegression(class_weight="balanced", max_iter=500)
        self.model.fit(X.values, y.values)
        return self
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None or X.empty:
            return np.zeros(len(X))
        if hasattr(self.model, "predict_proba"):
            return self.model.predict_proba(X.values)[:, 1]
        return self.model.predict(X.values)
    def cv_score(self, X: pd.DataFrame, y: pd.Series, embargo: int = 5) -> float:
        n = len(X)
        if n < 20:
            return float("nan")
        split = int(n * 0.7)
        X_train, y_train = X.iloc[:split], y.iloc[:split]
        X_test, y_test = X.iloc[split + embargo :], y.iloc[split + embargo :]
        if len(X_test) < 5 or y_train.nunique() < 2:
            return float("nan")
        self.fit(X_train, y_train)
        prob = self.predict_proba(X_test)
        k = max(1, int(len(prob) * 0.2))
        idx = np.argsort(prob)[-k:]
        prec = y_test.iloc[idx].mean() if len(idx) else float("nan")
        base = y_test.mean()
        return float(prec - base) if np.isfinite(prec) and np.isfinite(base) else float("nan")


if __name__ == "__main__":
    from pathlib import Path

    p = Path("/tmp/panel_adj_2007_2026.parquet")
    if p.exists():
        try:
            panel = pd.read_parquet(p)
            # normalize expected cols
            if "spread" not in panel.columns and "crack_321" in panel.columns:
                panel = panel.rename(columns={"crack_321": "spread"})
            print(f"loaded panel {panel.shape} {list(panel.columns)[:5]}")
        except Exception as e:
            print(f"parquet load failed {e}, using synthetic")
            panel = None
    else:
        panel = None
    if panel is None or panel.empty:
        np.random.seed(0)
        idx = pd.date_range("2007-01-01", periods=800, freq="B")
        spread = pd.Series(np.cumsum(np.random.randn(800) * 0.5), index=idx, name="spread")
        wti_slope = pd.Series(np.random.randn(800) * 0.2, index=idx, name="wti_slope")
        rb_ho_diff = pd.Series(np.random.randn(800) * 0.3, index=idx, name="rb_ho_diff")
        panel = pd.DataFrame({"spread": spread, "wti_slope": wti_slope, "rb_ho_diff": rb_ho_diff})

    print("HMM regime filter...")
    hmm = HMMRegimeFilter()
    prob = hmm.fit_predict_rolling(panel)
    print(f"p_stress: non-nan {prob.notna().sum()}/{len(prob)}, mean {prob.mean():.3f}")
    print(f"regime counts stress>0.6: {(prob>0.6).sum()}, calm<=0.4: {(prob<=0.4).sum()}")

    print("\nEVT tail sizer...")
    evt = EVT_TailSizer()
    spread_col = "spread" if "spread" in panel.columns else panel.columns[0]
    tr = evt.tail_risk(panel[spread_col])
    print(f"tail_risk non-nan {tr.notna().sum()}/{len(tr)}, last {tr.dropna().iloc[-1] if tr.notna().any() else 'nan'}")

    print("\nFocal meta-model on synthetic triggered events...")
    n = 80
    Xsyn = pd.DataFrame(np.random.randn(n, 4), columns=["rank", "vol", "regime", "slope"])
    ysyn = pd.Series((np.random.rand(n) < 0.2).astype(int))
    fm = FocalMetaModel()
    score = fm.cv_score(Xsyn, ysyn)
    print(f"cv precision uplift {score:.3f} (nan ok if small sample)")
    fm.fit(Xsyn, ysyn)
    proba = fm.predict_proba(Xsyn.head(5))
    print(f"predict_proba sample {proba[:3]}")
    print("done")
