"""Mercati derivati e "pronostico più probabile" per partita (alta accuratezza scegliendo il mercato)."""
from __future__ import annotations

import numpy as np
import pandas as pd

# nome mercato -> (colonna probabilità o funzione, esito vincente dato (gol casa, gol trasferta))
MARKETS = {
    "1": (lambda r: r["p1"], lambda h, a: h > a),
    "X": (lambda r: r["px"], lambda h, a: h == a),
    "2": (lambda r: r["p2"], lambda h, a: h < a),
    "1X": (lambda r: r["p1x"], lambda h, a: h >= a),
    "X2": (lambda r: r["px2"], lambda h, a: h <= a),
    "12": (lambda r: r["p12"], lambda h, a: h != a),
    "Over 1.5": (lambda r: r["o15"], lambda h, a: h + a >= 2),
    "Over 2.5": (lambda r: r["o25"], lambda h, a: h + a >= 3),
    "Under 2.5": (lambda r: 1 - r["o25"], lambda h, a: h + a <= 2),
    "Under 3.5": (lambda r: 1 - r["o35"], lambda h, a: h + a <= 3),
    "GG": (lambda r: r["gg"], lambda h, a: h > 0 and a > 0),
    "NG": (lambda r: 1 - r["gg"], lambda h, a: h == 0 or a == 0),
    "Multigol 1-3": (lambda r: r["mg13"], lambda h, a: 1 <= h + a <= 3),
    "Multigol 2-4": (lambda r: r["mg24"], lambda h, a: 2 <= h + a <= 4),
}


def probs(pred: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({k: f(pred) for k, (f, _) in MARKETS.items()}, index=pred.index)


def best_pick(pred: pd.DataFrame, exclude: tuple = ()) -> pd.DataFrame:
    """Per ogni partita il mercato con la probabilità più alta."""
    P = probs(pred).drop(columns=list(exclude), errors="ignore")
    return pd.DataFrame({"safe_pick": P.idxmax(1), "safe_p": P.max(1)}, index=pred.index)


def hit(market: str, hg, ag) -> np.ndarray:
    f = MARKETS[market][1]
    return np.array([bool(f(h, a)) for h, a in zip(hg, ag)])
