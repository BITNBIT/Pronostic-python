"""Storico pronostici: salva ogni previsione prima della partita e la verifica automaticamente a risultato acquisito."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from . import config as C

KEY = ["league", "season", "home", "away"]
KEEP = ["date", "time", "league", "season", "home", "away", "p1", "px", "p2", "pick", "conf", "stars", "dc", "o25", "gg",
        "score", "safe_pick", "safe_p", "odds_1", "odds_x", "odds_2", "odds_o25", "odds_u25", "vb_bet", "vb_odds", "vb_edge"]


def load() -> pd.DataFrame:
    if C.HISTORY_CSV.exists():
        return pd.read_csv(C.HISTORY_CSV, low_memory=False)
    return pd.DataFrame(columns=KEEP + ["created", "fthg", "ftag", "result", "hit", "hit_o25", "hit_gg", "hit_score", "hit_safe",
                                        "bet_win", "bet_pnl", "ll", "settled"])


def update(preds: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    h = load()
    now = datetime.now().isoformat(timespec="minutes")
    if preds is not None and len(preds):
        new = preds[[c for c in KEEP if c in preds.columns]].copy()
        new["created"] = now
        new["settled"] = False
        if len(h):
            h["settled"] = h["settled"].astype(str).str.lower().isin(["true", "1"])
            k_set = set(map(tuple, h.loc[h["settled"], KEY].astype(str).to_numpy()))
            new = new[[tuple(map(str, r)) not in k_set for r in new[KEY].to_numpy()]]
            # sostituisce le previsioni non ancora verificate con l'ultima versione (quote/forma aggiornate)
            k_new = set(map(tuple, new[KEY].astype(str).to_numpy()))
            h = h[[h_s or tuple(map(str, r)) not in k_new for h_s, r in zip(h["settled"], h[KEY].to_numpy())]]
        h = pd.concat([h, new], ignore_index=True)
    if h.empty:
        return h
    h["settled"] = h["settled"].astype(str).str.lower().isin(["true", "1"])
    # verifica risultati
    res = matches[KEY + ["fthg", "ftag"]].copy()
    res["season"] = res["season"].astype(int)
    h["season"] = h["season"].astype(int)
    m = h.drop(columns=["fthg", "ftag"], errors="ignore").merge(res, on=KEY, how="left")
    todo = (~m["settled"]) & m["fthg"].notna()
    if todo.any():
        r = m.loc[todo]
        hg, ag = r["fthg"].astype(int), r["ftag"].astype(int)
        result = np.where(hg > ag, "1", np.where(hg == ag, "X", "2"))
        m.loc[todo, "result"] = result
        m.loc[todo, "hit"] = r["pick"].to_numpy() == result
        m.loc[todo, "hit_o25"] = (r["o25"].to_numpy() >= 0.5) == ((hg + ag).to_numpy() > 2.5)
        m.loc[todo, "hit_gg"] = (r["gg"].to_numpy() >= 0.5) == ((hg > 0) & (ag > 0)).to_numpy()
        from .markets import MARKETS
        m.loc[todo, "hit_safe"] = [bool(MARKETS[k][1](x, y)) if k in MARKETS else np.nan
                                   for k, x, y in zip(r["safe_pick"].astype(str), hg, ag)]
        m.loc[todo, "hit_score"] = r["score"].to_numpy() == (hg.astype(str) + "-" + ag.astype(str)).to_numpy()
        pr = r[["p1", "px", "p2"]].to_numpy(float)
        idx = np.select([result == "1", result == "X"], [0, 1], 2)
        m.loc[todo, "ll"] = -np.log(np.clip(pr[np.arange(len(r)), idx], 1e-9, 1))
        bet = r["vb_bet"].astype("string").fillna("").to_numpy()
        has = bet != ""
        win = np.where(bet == "Over 2.5", (hg + ag).to_numpy() > 2.5,
                       np.where(bet == "Under 2.5", (hg + ag).to_numpy() < 2.5, bet == result))
        m.loc[todo, "bet_win"] = np.where(has, win, np.nan)
        m.loc[todo, "bet_pnl"] = np.where(has, np.where(win, r["vb_odds"].to_numpy(float) - 1, -1.0), np.nan)
        m.loc[todo, "settled"] = True
    # partite mai giocate da oltre 10 giorni (rinviate/cancellate): fuori dallo storico
    old = (~m["settled"]) & (pd.to_datetime(m["date"]) < pd.Timestamp.now() - pd.Timedelta(days=10))
    m = m[~old].sort_values(["date", "league", "home"]).reset_index(drop=True)
    C.ensure_dirs()
    m.to_csv(C.HISTORY_CSV, index=False, float_format="%.4f")
    return m


def _b(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1", "1.0"])


def stats(h: pd.DataFrame) -> dict:
    if h is None or h.empty:
        return {"n": 0}
    s = h[_b(h["settled"])].copy()
    if s.empty:
        return {"n": 0, "pending": int(len(h))}
    s["month"] = s["date"].astype(str).str[:7]
    bets = s[s["vb_bet"].astype("string").fillna("") != ""]
    out = {
        "n": int(len(s)), "pending": int((~_b(h["settled"])).sum()),
        "acc_1x2": round(float(_b(s["hit"]).mean()), 4), "acc_o25": round(float(_b(s["hit_o25"]).mean()), 4),
        "acc_gg": round(float(_b(s["hit_gg"]).mean()), 4), "acc_score": round(float(_b(s["hit_score"]).mean()), 4),
        "logloss": round(float(pd.to_numeric(s["ll"]).mean()), 4),
        "acc_safe": round(float(_b(s["hit_safe"]).mean()), 4) if "hit_safe" in s else None,
        "bets": int(len(bets)),
        "bets_hit": round(float(_b(bets["bet_win"]).mean()), 4) if len(bets) else None,
        "bets_units": round(float(pd.to_numeric(bets["bet_pnl"]).sum()), 2) if len(bets) else 0.0,
        "bets_roi": round(float(pd.to_numeric(bets["bet_pnl"]).mean()), 4) if len(bets) else None,
        "by_stars": [{"stars": int(k), "n": int(len(g)), "acc": round(float(_b(g["hit"]).mean()), 4)}
                     for k, g in s.groupby(pd.to_numeric(s["stars"], errors="coerce").fillna(0).astype(int))],
        "by_month": [{"month": k, "n": int(len(g)), "acc": round(float(_b(g["hit"]).mean()), 4),
                      "units": round(float(pd.to_numeric(g["bet_pnl"]).sum()), 2)} for k, g in s.groupby("month")],
        "pnl_curve": [round(float(x), 2) for x in pd.to_numeric(bets["bet_pnl"]).cumsum()] if len(bets) else [],
        "recent": s.tail(30)[["date", "league", "home", "away", "pick", "conf", "result", "fthg", "ftag", "hit",
                              "safe_pick", "hit_safe",
                              "vb_bet", "vb_odds", "bet_pnl"]].iloc[::-1].to_dict("records"),
    }
    return out
