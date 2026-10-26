"""Selezione value bet + staking Kelly frazionato."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Params

MARKETS = [("1", "p1", "h"), ("X", "px", "d"), ("2", "p2", "a")]


def pick_value(pred: pd.DataFrame, df: pd.DataFrame, p: Params, prefix: str = "odds",
               min_edge: float | None = None) -> pd.DataFrame:
    """Per ogni partita la giocata (1/X/2/Over/Under 2.5) col miglior edge sopra soglia."""
    min_edge = p.min_edge if min_edge is None else min_edge
    rows = []
    for i in pred.index:
        best = None
        cands = [(lab, pred.at[i, pc], df.at[i, f"{prefix}_{oc}"]) for lab, pc, oc in MARKETS]
        if prefix == "odds":
            cands += [("Over 2.5", pred.at[i, "o25"], df.at[i, "odds_o25"]),
                      ("Under 2.5", 1 - pred.at[i, "o25"], df.at[i, "odds_u25"])]
        for lab, prob, o in cands:
            if not (np.isfinite(o) and np.isfinite(prob)) or o <= 1 or o > p.max_odds_value or prob < p.min_prob_value:
                continue
            edge = prob * o - 1
            if edge >= min_edge and (best is None or edge > best[3]):
                best = (lab, prob, o, edge)
        if best:
            lab, prob, o, edge = best
            k = min(p.kelly_cap, p.kelly_fraction * edge / (o - 1))
            rows.append({"idx": i, "bet": lab, "prob": prob, "odds": o, "edge": edge, "stake": k})
    return pd.DataFrame(rows, columns=["idx", "bet", "prob", "odds", "edge", "stake"])


def settle(bets: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    if bets.empty:
        return bets.assign(win=[], pnl=[], pnl_k=[])
    hg = df.loc[bets["idx"], "fthg"].to_numpy()
    ag = df.loc[bets["idx"], "ftag"].to_numpy()
    res = np.where(hg > ag, "1", np.where(hg == ag, "X", "2"))
    b = bets["bet"].to_numpy()
    win = np.where(b == "Over 2.5", hg + ag > 2.5, np.where(b == "Under 2.5", hg + ag < 2.5, b == res))
    out = bets.copy()
    out["win"] = win
    out["pnl"] = np.where(win, out["odds"] - 1, -1.0)
    out["pnl_k"] = out["stake"] * out["pnl"]
    return out


def summary(settled: pd.DataFrame) -> dict:
    if settled is None or settled.empty:
        return {"n": 0, "hit": None, "roi": None, "units": 0.0, "kelly_growth": None}
    n = len(settled)
    return {"n": int(n), "hit": round(float(settled["win"].mean()), 4),
            "roi": round(float(settled["pnl"].sum() / n), 4), "units": round(float(settled["pnl"].sum()), 2),
            "avg_odds": round(float(settled["odds"].mean()), 2),
            "kelly_growth": round(float(np.prod(1 + settled["pnl_k"].to_numpy()) - 1), 4)}
