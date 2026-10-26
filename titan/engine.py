"""Motore sequenziale di rating e feature.

Ogni partita viene descritta SOLO con informazioni disponibili prima del calcio d'inizio
(niente leakage: il difetto principale della v5, che calcolava le medie sull'intero storico
compresa la partita da prevedere). Dopo la feature extraction lo stato viene aggiornato col risultato.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Params

LEVEL = {"I1": 1, "I2": 2}


@dataclass
class Team:
    elo: float
    att: float
    dfn: float
    league: str
    season: int
    last: pd.Timestamp | None = None
    hist: deque = field(default_factory=lambda: deque(maxlen=10))      # (pts, gf, ga, sf, sa, stf, sta)
    home: deque = field(default_factory=lambda: deque(maxlen=6))       # (pts, gf, ga)
    away: deque = field(default_factory=lambda: deque(maxlen=6))
    s_pts: int = 0
    s_g: int = 0
    s_gf: int = 0
    s_ga: int = 0


def _nanmean(vals):
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
    return float(np.mean(vals)) if vals else np.nan


def implied(o1, o2, o3=None):
    """Probabilità implicite senza margine del bookmaker (normalizzazione proporzionale)."""
    odds = [o1, o2] + ([o3] if o3 is not None else [])
    if any(o is None or not np.isfinite(o) or o <= 1 for o in odds):
        return [np.nan] * len(odds)
    inv = np.array([1.0 / o for o in odds])
    return list(inv / inv.sum())


class RatingEngine:
    def __init__(self, p: Params | None = None):
        self.p = p or Params()
        self.teams: dict[str, Team] = {}
        self.mu = {"I1": math.log(1.30), "I2": math.log(1.20)}
        self.hg = {"I1": 0.22, "I2": 0.25}
        self.mu_lr = 0.002
        self.latest = 0

    # ------------------------------------------------------------------ stato squadre
    def _league_vals(self, league: str, attr: str):
        return [getattr(t, attr) for t in self.teams.values() if t.league == league and t.season >= self.latest - 1]

    def _q(self, league: str, attr: str, q: float, default: float) -> float:
        v = self._league_vals(league, attr)
        return float(np.quantile(v, q)) if len(v) >= 6 else default

    def _new(self, name: str, league: str, season: int) -> Team:
        q = self.p.q_promoted
        t = Team(elo=self._q(league, "elo", q, 1500.0 if league == "I1" else 1380.0),
                 att=self._q(league, "att", q, 0.0), dfn=self._q(league, "dfn", q, 0.0),
                 league=league, season=season)
        self.teams[name] = t
        return t

    def _prepare(self, name: str, league: str, season: int) -> Team:
        t = self.teams.get(name)
        if t is None:
            return self._new(name, league, season)
        if season != t.season:
            # nuova stagione: regressione verso la media e reset classifica
            if league != t.league:
                # promossa (B->A) parte bassa nella nuova lega, retrocessa (A->B) parte alta
                q = self.p.q_promoted if LEVEL[league] < LEVEL[t.league] else 1 - self.p.q_promoted
                t.att = 0.5 * t.att + 0.5 * self._q(league, "att", q, t.att)
                t.dfn = 0.5 * t.dfn + 0.5 * self._q(league, "dfn", q, t.dfn)
                target = self._q(league, "elo", q, t.elo)
            else:
                v = self._league_vals(league, "elo")
                target = float(np.mean(v)) if v else t.elo
                t.att *= 1 - self.p.pois_regress
                t.dfn *= 1 - self.p.pois_regress
            t.elo = (1 - self.p.elo_regress) * t.elo + self.p.elo_regress * target
            t.league, t.season = league, season
            t.s_pts = t.s_g = t.s_gf = t.s_ga = 0
        return t

    # ------------------------------------------------------------------ feature
    def _form(self, t: Team, pre: str, f: dict):
        h = list(t.hist)
        for n in (5, 10):
            w = h[-n:]
            f[f"{pre}_ppg{n}"] = _nanmean([x[0] for x in w])
            f[f"{pre}_gf{n}"] = _nanmean([x[1] for x in w])
            f[f"{pre}_ga{n}"] = _nanmean([x[2] for x in w])
        sf = [x[3] for x in h if x[3] == x[3]]
        sa = [x[4] for x in h if x[4] == x[4]]
        stf = [x[5] for x in h if x[5] == x[5]]
        sta = [x[6] for x in h if x[6] == x[6]]
        f[f"{pre}_shr"] = sum(sf) / (sum(sf) + sum(sa)) if len(sf) >= 3 and sum(sf) + sum(sa) > 0 else np.nan
        f[f"{pre}_sotr"] = sum(stf) / (sum(stf) + sum(sta)) if len(stf) >= 3 and sum(stf) + sum(sta) > 0 else np.nan
        f[f"{pre}_sg"] = t.s_g
        f[f"{pre}_sppg"] = t.s_pts / t.s_g if t.s_g else np.nan
        f[f"{pre}_sgd"] = (t.s_gf - t.s_ga) / t.s_g if t.s_g else np.nan

    def features(self, home: str, away: str, league: str, date: pd.Timestamp, season: int, row=None) -> dict:
        self.latest = max(self.latest, season)
        th = self._prepare(home, league, season)
        ta = self._prepare(away, league, season)
        hfa = self.p.elo_hfa
        f = {"lvl": LEVEL.get(league, 2)}
        f["elo_h"], f["elo_a"] = th.elo, ta.elo
        f["elo_d"] = th.elo + hfa - ta.elo
        f["elo_e"] = 1.0 / (1.0 + 10 ** (-f["elo_d"] / 400))
        lh = math.exp(self.mu[league] + self.hg[league] + th.att - ta.dfn)
        la = math.exp(self.mu[league] + ta.att - th.dfn)
        f.update(att_h=th.att, dfn_h=th.dfn, att_a=ta.att, dfn_a=ta.dfn, lam_h=lh, lam_a=la,
                 lam_t=lh + la, lam_d=lh - la)
        self._form(th, "h", f)
        self._form(ta, "a", f)
        hh = list(th.home)[-5:]
        aa = list(ta.away)[-5:]
        f["h_home_ppg"] = _nanmean([x[0] for x in hh])
        f["h_home_gd"] = _nanmean([x[1] - x[2] for x in hh])
        f["a_away_ppg"] = _nanmean([x[0] for x in aa])
        f["a_away_gd"] = _nanmean([x[1] - x[2] for x in aa])
        f["rest_h"] = min((date - th.last).days, 30) if th.last is not None else 30
        f["rest_a"] = min((date - ta.last).days, 30) if ta.last is not None else 30
        f["rest_d"] = f["rest_h"] - f["rest_a"]
        f["form_d"] = (f["h_ppg5"] if f["h_ppg5"] == f["h_ppg5"] else 1.4) - (f["a_ppg5"] if f["a_ppg5"] == f["a_ppg5"] else 1.4)
        f["sppg_d"] = (f["h_sppg"] if f["h_sppg"] == f["h_sppg"] else 0) - (f["a_sppg"] if f["a_sppg"] == f["a_sppg"] else 0)
        # mercato (probabilità senza margine). Pinnacle se disponibile, altrimenti media.
        mk = [np.nan] * 3
        o25 = np.nan
        if row is not None:
            mk = implied(row.get("pin_h"), row.get("pin_d"), row.get("pin_a"))
            if not np.isfinite(mk[0]):
                mk = implied(row.get("odds_h"), row.get("odds_d"), row.get("odds_a"))
            o25 = implied(row.get("odds_o25"), row.get("odds_u25"))[0]
        f["mk_h"], f["mk_d"], f["mk_a"] = mk
        f["mk_o25"] = o25
        return f

    # ------------------------------------------------------------------ update
    def update(self, home: str, away: str, league: str, date: pd.Timestamp, hg: int, ag: int, row=None):
        th, ta = self.teams[home], self.teams[away]
        # Elo con moltiplicatore margine (stile World Football Elo)
        e = 1.0 / (1.0 + 10 ** (-(th.elo + self.p.elo_hfa - ta.elo) / 400))
        s = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        gd = abs(hg - ag)
        g = 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8
        d = self.p.elo_k * g * (s - e)
        th.elo += d
        ta.elo -= d
        # Poisson online
        lh = math.exp(self.mu[league] + self.hg[league] + th.att - ta.dfn)
        la = math.exp(self.mu[league] + ta.att - th.dfn)
        rh, ra = hg - lh, ag - la
        lr = self.p.pois_lr
        th.att += lr * rh
        ta.dfn -= lr * rh
        ta.att += lr * ra
        th.dfn -= lr * ra
        self.mu[league] += self.mu_lr * (rh + ra) / 2
        self.hg[league] += self.mu_lr * (rh - ra) / 2
        # forma
        ph = 3 if hg > ag else 1 if hg == ag else 0
        pa = 3 if ag > hg else 1 if hg == ag else 0
        g_ = (lambda k: float(row[k]) if row is not None and k in row and row[k] == row[k] else np.nan)
        th.hist.append((ph, hg, ag, g_("hs"), g_("as_"), g_("hst"), g_("ast")))
        ta.hist.append((pa, ag, hg, g_("as_"), g_("hs"), g_("ast"), g_("hst")))
        th.home.append((ph, hg, ag))
        ta.away.append((pa, ag, hg))
        th.s_pts += ph; th.s_g += 1; th.s_gf += hg; th.s_ga += ag
        ta.s_pts += pa; ta.s_g += 1; ta.s_gf += ag; ta.s_ga += hg
        th.last = ta.last = date

    # ------------------------------------------------------------------ batch
    def run(self, matches: pd.DataFrame) -> pd.DataFrame:
        """Processa lo storico in ordine cronologico e ritorna le feature pre-partita."""
        m = matches.sort_values(["date", "league", "home"]).reset_index(drop=True)
        feats = []
        for row in m.to_dict("records"):
            f = self.features(row["home"], row["away"], row["league"], row["date"], int(row["season"]), row)
            feats.append(f)
            self.update(row["home"], row["away"], row["league"], row["date"], int(row["fthg"]), int(row["ftag"]), row)
        return pd.concat([m, pd.DataFrame(feats)], axis=1)

    def fixture_features(self, fixtures: pd.DataFrame) -> pd.DataFrame:
        if fixtures is None or not len(fixtures):
            return pd.DataFrame()
        fx = fixtures.reset_index(drop=True)
        feats = [self.features(r["home"], r["away"], r["league"], r["date"], int(r["season"]), r)
                 for r in fx.to_dict("records")]
        return pd.concat([fx, pd.DataFrame(feats)], axis=1)

    def table(self, league: str) -> pd.DataFrame:
        """Classifica 'live' calcolata dai risultati (sostituisce i file classifica manuali)."""
        cur = max((t.season for t in self.teams.values() if t.league == league), default=None)
        rows = [{"team": n, "pts": t.s_pts, "g": t.s_g, "gf": t.s_gf, "ga": t.s_ga, "gd": t.s_gf - t.s_ga,
                 "elo": round(t.elo), "form": "".join("WDL"[[3, 1, 0].index(x[0])] for x in list(t.hist)[-5:])}
                for n, t in self.teams.items() if t.league == league and t.season == cur and t.s_g > 0]
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        return df.sort_values(["pts", "gd", "gf"], ascending=False).reset_index(drop=True)
