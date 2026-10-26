"""Modelli: gradient boosting + logistica (1X2), Poisson/Dixon-Coles (gol), mercato. Blend ottimizzato."""
from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    import lightgbm as lgb
except Exception:  # noqa: BLE001
    lgb = None
from sklearn.ensemble import HistGradientBoostingClassifier

warnings.filterwarnings("ignore")
log = logging.getLogger("titan.models")

FEATURES = [
    "lvl", "elo_h", "elo_a", "elo_d", "elo_e", "att_h", "dfn_h", "att_a", "dfn_a", "lam_h", "lam_a", "lam_t", "lam_d",
    "h_ppg5", "h_gf5", "h_ga5", "h_ppg10", "h_gf10", "h_ga10", "h_shr", "h_sotr", "h_sg", "h_sppg", "h_sgd",
    "a_ppg5", "a_gf5", "a_ga5", "a_ppg10", "a_gf10", "a_ga10", "a_shr", "a_sotr", "a_sg", "a_sppg", "a_sgd",
    "h_home_ppg", "h_home_gd", "a_away_ppg", "a_away_gd", "rest_h", "rest_a", "rest_d", "form_d", "sppg_d",
    "mk_h", "mk_d", "mk_a", "mk_o25",
]
LR_FEATURES = ["elo_d", "elo_e", "lam_h", "lam_a", "lam_d", "form_d", "sppg_d", "h_shr", "a_shr", "h_sotr", "a_sotr",
               "h_home_ppg", "a_away_ppg", "rest_d", "lvl", "mk_h", "mk_a", "mk_d"]
COMPONENTS = ["gbm", "lr", "dc", "mk"]
MAXG = 10


def target(df: pd.DataFrame) -> np.ndarray:
    return np.select([df["fthg"] > df["ftag"], df["fthg"] == df["ftag"]], [0, 1], 2)


def logloss(y, p) -> float:
    p = np.clip(np.asarray(p, float), 1e-12, 1)
    return float(-np.mean(np.log(p[np.arange(len(y)), y])))


def rps(y, p) -> float:
    oh = np.eye(3)[y]
    cp, co = np.cumsum(p, 1), np.cumsum(oh, 1)
    return float(np.mean(np.sum((cp - co)[:, :2] ** 2, 1) / 2))


# --------------------------------------------------------------------------- Dixon-Coles
def score_matrix(lh: float, la: float, rho: float = 0.0, maxg: int = MAXG) -> np.ndarray:
    g = np.arange(maxg + 1)
    m = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
    if rho:
        m[0, 0] *= max(1 - lh * la * rho, 1e-6)
        m[0, 1] *= max(1 + lh * rho, 1e-6)
        m[1, 0] *= max(1 + la * rho, 1e-6)
        m[1, 1] *= max(1 - rho, 1e-6)
    return m / m.sum()


def matrix_1x2(m: np.ndarray) -> np.ndarray:
    return np.array([np.tril(m, -1).sum(), np.trace(m), np.triu(m, 1).sum()])


def dc_probs(lh: np.ndarray, la: np.ndarray, rho: float) -> np.ndarray:
    return np.vstack([matrix_1x2(score_matrix(a, b, rho)) for a, b in zip(lh, la)])


def fit_rho(lh, la, hg, ag) -> float:
    hg = np.asarray(hg, int)
    ag = np.asarray(ag, int)

    def nll(rho):
        tau = np.ones(len(hg))
        tau = np.where((hg == 0) & (ag == 0), 1 - lh * la * rho, tau)
        tau = np.where((hg == 0) & (ag == 1), 1 + lh * rho, tau)
        tau = np.where((hg == 1) & (ag == 0), 1 + la * rho, tau)
        tau = np.where((hg == 1) & (ag == 1), 1 - rho, tau)
        return -np.sum(np.log(np.clip(tau, 1e-9, None)))

    return float(minimize_scalar(nll, bounds=(-0.25, 0.1), method="bounded").x)


# --------------------------------------------------------------------------- blend
def blend(probs: dict[str, np.ndarray], w: dict[str, float]) -> np.ndarray:
    """Media pesata in log-space (pool geometrico) con rinormalizzazione se un componente manca (NaN)."""
    n = len(next(iter(probs.values())))
    num = np.zeros((n, 3))
    den = np.zeros((n, 1))
    for k, p in probs.items():
        wk = w.get(k, 0.0)
        if wk <= 0:
            continue
        ok = np.isfinite(p).all(1, keepdims=True)
        num += np.where(ok, wk * np.log(np.clip(np.nan_to_num(p, nan=1 / 3), 1e-9, 1)), 0)
        den += np.where(ok, wk, 0)
    out = np.exp(num / np.clip(den, 1e-9, None))
    return out / out.sum(1, keepdims=True)


def fit_weights(probs: dict[str, np.ndarray], y: np.ndarray) -> dict[str, float]:
    keys = list(probs)

    def f(z):
        w = dict(zip(keys, np.exp(z) / np.exp(z).sum()))
        return logloss(y, blend(probs, w))

    r = minimize(f, np.zeros(len(keys)), method="L-BFGS-B", bounds=[(-6, 6)] * len(keys), options={"eps": 1e-4})
    w = np.exp(r.x) / np.exp(r.x).sum()
    return {k: round(float(v), 4) for k, v in zip(keys, w)}


def fit_o25_weight(p_dc, p_mk, y) -> float:
    ok = np.isfinite(p_mk)
    if ok.sum() < 200:
        return 0.0

    def f(w):
        p = np.clip((1 - w) * p_dc[ok] + w * p_mk[ok], 1e-9, 1 - 1e-9)
        return -np.mean(y[ok] * np.log(p) + (1 - y[ok]) * np.log(1 - p))

    return float(minimize_scalar(f, bounds=(0, 1), method="bounded").x)


# --------------------------------------------------------------------------- modello completo
MK = ["mk_h", "mk_d", "mk_a", "mk_o25"]


class TitanModel:
    """use_market=True: usa le quote come feature e componente del blend (partite con quote).
    use_market=False: modello puro da dati di campo (partite senza quote disponibili)."""

    def __init__(self, seed: int = 7, use_market: bool = True):
        self.seed = seed
        self.use_market = use_market
        self.F = FEATURES if use_market else [f for f in FEATURES if f not in MK]
        self.LF = LR_FEATURES if use_market else [f for f in LR_FEATURES if f not in MK]
        self.w = {"gbm": 0.3, "lr": 0.2, "dc": 0.2, "mk": 0.3}
        self.rho = -0.05
        self.w_o25 = 0.5
        self.gbm_iter = 400
        self.meta: dict = {}

    # -- base models
    def _gbm(self, n_iter):
        if lgb is not None:
            return lgb.LGBMClassifier(objective="multiclass", n_estimators=n_iter, learning_rate=0.02, num_leaves=15,
                                      min_child_samples=80, subsample=0.8, subsample_freq=1, colsample_bytree=0.7,
                                      reg_lambda=5.0, random_state=self.seed, verbose=-1)
        return HistGradientBoostingClassifier(max_iter=n_iter, learning_rate=0.03, max_leaf_nodes=15,
                                              min_samples_leaf=80, l2_regularization=5.0, random_state=self.seed)

    def _fit_base(self, tr: pd.DataFrame, n_iter: int):
        X, y = tr[self.F], target(tr)
        self.gbm = self._gbm(n_iter).fit(X, y)
        self.lr = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                                LogisticRegression(C=0.3, max_iter=2000)).fit(tr[self.LF], y)
        kw = dict(loss="poisson", max_iter=250, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=80,
                  l2_regularization=1.0, random_state=self.seed)
        self.gh = HistGradientBoostingRegressor(**kw).fit(X, tr["fthg"].clip(upper=MAXG))
        self.ga = HistGradientBoostingRegressor(**kw).fit(X, tr["ftag"].clip(upper=MAXG))

    def _components(self, df: pd.DataFrame) -> tuple[dict, np.ndarray, np.ndarray]:
        X = df[self.F]
        lh = np.clip(self.gh.predict(X), 0.15, 5)
        la = np.clip(self.ga.predict(X), 0.15, 5)
        comps = {"gbm": self.gbm.predict_proba(X), "lr": self.lr.predict_proba(df[self.LF]),
                 "dc": dc_probs(lh, la, self.rho)}
        if self.use_market:
            comps["mk"] = df[["mk_h", "mk_d", "mk_a"]].to_numpy(float)
        return comps, lh, la

    def _best_iter(self, tr, va) -> int:
        if lgb is None:
            return 300
        m = self._gbm(2000)
        m.fit(tr[self.F], target(tr), eval_set=[(va[self.F], target(va))],
              callbacks=[lgb.early_stopping(100, verbose=False)])
        return int(max(100, m.best_iteration_ or 400))

    def fit(self, data: pd.DataFrame, n_valid: int = 3):
        """Stacking walk-forward: per le ultime n_valid stagioni complete si allena su quelle precedenti,
        si raccolgono le previsioni out-of-sample e su queste si stimano pesi del blend, rho Dixon-Coles e
        peso mercato Over/Under. Poi refit finale su tutti i dati."""
        data = data.sort_values("date")
        counts = data.groupby("season").size()
        full = [s for s, n in counts.items() if n >= 300]
        vseasons = full[-n_valid:] if len(full) > n_valid + 3 else full[-1:]
        tr0 = data[data["season"] < vseasons[-1]]
        self.gbm_iter = self._best_iter(tr0, data[data["season"] == vseasons[-1]])
        folds = []
        for v in vseasons:
            tr, va = data[data["season"] < v], data[data["season"] == v]
            self._fit_base(tr, self.gbm_iter)
            X = va[self.F]
            folds.append((va, np.clip(self.gh.predict(X), 0.15, 5), np.clip(self.ga.predict(X), 0.15, 5),
                          self.gbm.predict_proba(X), self.lr.predict_proba(va[self.LF])))
        va = pd.concat([f[0] for f in folds])
        lh = np.concatenate([f[1] for f in folds])
        la = np.concatenate([f[2] for f in folds])
        self.rho = fit_rho(lh, la, va["fthg"].to_numpy(), va["ftag"].to_numpy())
        comps = {"gbm": np.vstack([f[3] for f in folds]), "lr": np.vstack([f[4] for f in folds]),
                 "dc": dc_probs(lh, la, self.rho)}
        if self.use_market:
            comps["mk"] = va[["mk_h", "mk_d", "mk_a"]].to_numpy(float)
        yv = target(va)
        self.w = fit_weights(comps, yv)
        tot = np.add.outer(range(MAXG + 1), range(MAXG + 1))
        p_dc = np.array([1 - score_matrix(a, b, self.rho)[tot <= 2].sum() for a, b in zip(lh, la)])
        self.w_o25 = fit_o25_weight(p_dc, va["mk_o25"].to_numpy(float), (va["fthg"] + va["ftag"] > 2.5).to_numpy(int)) \
            if self.use_market else 0.0
        ok = np.isfinite(comps["mk"]).all(1) if self.use_market else np.ones(len(yv), bool)
        val = {k: logloss(yv[ok], p[ok]) for k, p in comps.items()}
        val["blend"] = logloss(yv[ok], blend(comps, self.w)[ok])
        self.meta = {"valid_seasons": [int(s) for s in vseasons], "gbm_iter": self.gbm_iter, "rho": round(self.rho, 4),
                     "weights": self.w, "w_o25": round(self.w_o25, 3),
                     "valid_logloss": {k: round(v, 4) for k, v in val.items()}, "n_train": int(len(data))}
        self._fit_base(data, self.gbm_iter)
        return self

    # -- inferenza
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        comps, lh, la = self._components(df)
        p = blend(comps, self.w)
        out = pd.DataFrame(p, columns=["p1", "px", "p2"], index=df.index)
        out["lam_h"], out["lam_a"] = lh, la
        for k in [c for c in ("gbm", "dc", "mk") if c in comps]:
            out[f"{k}_p1"], out[f"{k}_px"], out[f"{k}_p2"] = comps[k][:, 0], comps[k][:, 1], comps[k][:, 2]
        tot = np.add.outer(range(MAXG + 1), range(MAXG + 1))
        mats, extra = [], []
        for i, (a, b) in enumerate(zip(lh, la)):
            m = score_matrix(a, b, self.rho)
            # riallinea la matrice punteggi alle probabilità 1X2 finali (coerenza tra mercati)
            base = matrix_1x2(m)
            scale = p[i] / np.clip(base, 1e-9, None)
            m = m * np.where(np.tri(MAXG + 1, k=-1, dtype=bool), scale[0], np.where(np.eye(MAXG + 1, dtype=bool), scale[1], scale[2]))
            m /= m.sum()
            mats.append(m)
            o25 = 1 - m[tot <= 2].sum()
            mk = df["mk_o25"].iloc[i]
            if self.use_market and np.isfinite(mk) and self.w_o25 > 0:
                o25 = (1 - self.w_o25) * o25 + self.w_o25 * mk
            top = np.dstack(np.unravel_index(np.argsort(m.ravel())[::-1][:5], m.shape))[0]
            extra.append({
                "o15": 1 - m[tot <= 1].sum(), "o25": o25, "o35": 1 - m[tot <= 3].sum(),
                "gg": m[1:, 1:].sum(), "score": f"{top[0][0]}-{top[0][1]}",
                "top_scores": ", ".join(f"{a}-{b} {m[a, b]:.0%}" for a, b in top),
                "mg13": m[(tot >= 1) & (tot <= 3)].sum(), "mg24": m[(tot >= 2) & (tot <= 4)].sum(),
            })
        out = pd.concat([out, pd.DataFrame(extra, index=df.index)], axis=1)
        out["p1x"], out["px2"], out["p12"] = out.p1 + out.px, out.px + out.p2, out.p1 + out.p2
        return out


class DualModel:
    """Due modelli: con quote (quando il bookmaker ha già quotato la partita) e senza quote."""

    def __init__(self):
        self.mk = TitanModel(use_market=True)
        self.pure = TitanModel(use_market=False)
        self.meta: dict = {}

    def fit(self, data: pd.DataFrame):
        self.mk.fit(data)
        self.pure.fit(data)
        self.meta = {"market_model": self.mk.meta, "pure_model": self.pure.meta}
        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        has = df[["mk_h", "mk_d", "mk_a"]].notna().all(1).to_numpy()
        parts = []
        if has.any():
            parts.append(self.mk.predict(df[has]).assign(model="quote+campo"))
        if (~has).any():
            parts.append(self.pure.predict(df[~has]).assign(model="campo"))
        return pd.concat(parts).loc[df.index]
