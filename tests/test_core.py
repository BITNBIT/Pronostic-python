import numpy as np
import pandas as pd

from titan import config as C
from titan.engine import RatingEngine, implied
from titan.models import blend, matrix_1x2, score_matrix
from titan.sources import COLS, merge_sources
from titan.teams import normalize


def test_season():
    assert C.season_of(pd.Timestamp("2025-08-20")) == 2025
    assert C.season_of(pd.Timestamp("2026-05-30")) == 2025
    assert C.season_of(pd.Timestamp("2020-08-02")) == 2019  # stagione covid


def test_names():
    assert normalize("FC Internazionale Milano") == "Inter"
    assert normalize("Hellas Verona FC") == "Verona"


def test_implied_and_matrix():
    p = implied(2.0, 3.4, 4.0)
    assert abs(sum(p) - 1) < 1e-9 and p[0] > p[2]
    m = score_matrix(1.5, 1.1, -0.05)
    assert abs(m.sum() - 1) < 1e-9
    assert abs(matrix_1x2(m).sum() - 1) < 1e-9


def test_blend_missing_market():
    a = np.array([[0.5, 0.3, 0.2]])
    out = blend({"x": a, "mk": np.array([[np.nan] * 3])}, {"x": 0.5, "mk": 0.5})
    assert np.allclose(out, a)


def _row(d, h, a, hg, ag, prio, src):
    r = dict.fromkeys(COLS, np.nan)
    r.update(date=pd.Timestamp(d), league="I1", season=C.season_of(pd.Timestamp(d)), home=h, away=a,
             fthg=hg, ftag=ag, prio=prio, source=src)
    return r


def test_merge_dedup():
    df = pd.DataFrame([_row("2025-09-01", "Inter", "Milan", 1, 0, 0, "fd"),
                       _row("2025-09-20", "Inter", "Milan", 1, 0, 3, "of"),   # data diversa, fonte peggiore
                       _row("2025-09-02", "Inter", "Milan", 1, 0, 4, "legacy")])
    out = merge_sources([df])
    assert len(out) == 1 and out.iloc[0]["source"] == "fd"


def test_no_leakage():
    m = pd.DataFrame([_row("2025-09-01", "A", "B", 5, 0, 0, "x"), _row("2025-09-08", "B", "A", 0, 0, 0, "x")])
    f = RatingEngine().run(m)
    assert f.loc[0, "elo_h"] == f.loc[0, "elo_a"]       # prima partita: nessuna info sul risultato
    assert f.loc[1, "elo_a"] > f.loc[1, "elo_h"]        # seconda: A ha guadagnato Elo
