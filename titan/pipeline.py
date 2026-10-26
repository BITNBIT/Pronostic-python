"""Pipeline completa: dati -> rating -> training -> pronostici -> tracking -> report/notifiche."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

from . import betting, markets, sources, tracker
from . import config as C
from .engine import RatingEngine
from .models import DualModel

log = logging.getLogger("titan.pipeline")
SIGN = np.array(["1", "X", "2"])


def build(matches: pd.DataFrame, fixtures: pd.DataFrame, p: C.Params):
    eng = RatingEngine(p)
    feat = eng.run(matches)
    fx = eng.fixture_features(fixtures)
    return eng, feat, fx


def _signature(matches: pd.DataFrame) -> str:
    s = f"{len(matches)}|{matches['date'].max()}|{matches[['fthg', 'ftag']].sum().sum()}|v6.2"
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def train(feat: pd.DataFrame, matches: pd.DataFrame, p: C.Params, force: bool = False) -> DualModel:
    sig = _signature(matches)
    f = C.MODELS_DIR / "titan.joblib"
    if f.exists() and not force:
        try:
            obj = joblib.load(f)
            if obj.get("sig") == sig:
                log.info("modello in cache (%s)", sig)
                return obj["model"]
        except Exception:  # noqa: BLE001
            pass
    log.info("training modello su %d partite...", int((feat["season"] >= p.train_from_season).sum()))
    model = DualModel().fit(feat[feat["season"] >= p.train_from_season])
    model.meta["trained"] = datetime.now().isoformat(timespec="seconds")
    model.meta["sig"] = sig
    C.ensure_dirs()
    joblib.dump({"sig": sig, "model": model}, f)
    return model


def _form(eng: RatingEngine, team: str) -> str:
    t = eng.teams.get(team)
    if not t:
        return ""
    return "".join({3: "V", 1: "N", 0: "P"}[x[0]] for x in list(t.hist)[-5:])


def predict_fixtures(model: DualModel, fx: pd.DataFrame, eng: RatingEngine, p: C.Params) -> pd.DataFrame:
    if fx is None or fx.empty:
        return pd.DataFrame()
    pr = model.predict(fx)
    vb = betting.pick_value(pr, fx, p).set_index("idx") if len(fx) else pd.DataFrame()
    P = pr[["p1", "px", "p2"]].to_numpy()
    out = pd.DataFrame({
        "date": fx["date"].dt.strftime("%Y-%m-%d"), "time": fx["time"].fillna("").astype(str).str[:5],
        "league": fx["league"], "season": fx["season"].astype(int), "home": fx["home"], "away": fx["away"],
        "p1": P[:, 0], "px": P[:, 1], "p2": P[:, 2], "pick": SIGN[P.argmax(1)], "conf": P.max(1),
        "dc": np.where(pr["p1x"] >= pr["px2"], "1X", "X2"), "dc_p": np.maximum(pr["p1x"], pr["px2"]),
        "xg_h": pr["lam_h"], "xg_a": pr["lam_a"], "score": pr["score"], "top_scores": pr["top_scores"],
        "o15": pr["o15"], "o25": pr["o25"], "o35": pr["o35"], "gg": pr["gg"], "mg13": pr["mg13"], "mg24": pr["mg24"],
        "mk_p1": fx["mk_h"], "mk_px": fx["mk_d"], "mk_p2": fx["mk_a"],
        "odds_1": fx["odds_h"], "odds_x": fx["odds_d"], "odds_2": fx["odds_a"],
        "odds_o25": fx["odds_o25"], "odds_u25": fx["odds_u25"],
        "model": pr["model"], "elo_h": fx["elo_h"].round(0), "elo_a": fx["elo_a"].round(0),
        "form_h": [_form(eng, t) for t in fx["home"]], "form_a": [_form(eng, t) for t in fx["away"]],
    }, index=fx.index)
    for c in ("bet", "odds", "edge"):
        out[f"vb_{c}"] = vb[c] if len(vb) else np.nan
    sp = markets.best_pick(pr).reset_index(drop=True)
    out = out.reset_index(drop=True)
    out["safe_pick"], out["safe_p"] = sp["safe_pick"], sp["safe_p"]
    out["ou_pick"] = np.where(out["o25"] >= 0.5, "Over 2.5", "Under 2.5")
    out["gg_pick"] = np.where(out["gg"] >= 0.5, "GG", "NG")
    # rating sintetico 1-5 stelle per la giocata principale (dal backtest: conf>0.65 ~ 70% hit)
    out["stars"] = pd.cut(out["conf"], [0, 0.45, 0.52, 0.6, 0.68, 1.01], labels=[1, 2, 3, 4, 5]).astype(int)
    return out.reset_index(drop=True)


def run(offline: bool = False, force_train: bool = False, notify: bool = True) -> dict:
    p = C.Params()
    C.ensure_dirs()
    if offline and C.MATCHES_CSV.exists():
        matches, fixtures = sources.load()
    else:
        matches, fixtures = sources.update(offline=offline)
    log.info("partite storiche: %d, prossime partite: %d", len(matches), len(fixtures))
    eng, feat, fx = build(matches, fixtures, p)
    model = train(feat, matches, p, force=force_train)
    preds = predict_fixtures(model, fx, eng, p)
    today = datetime.now().strftime("%Y-%m-%d")
    hist = tracker.update(preds, matches)
    live = tracker.stats(hist)
    tables = {lg: eng.table(lg).to_dict("records") for lg in C.LEAGUES}
    state = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "data": {"matches": int(len(matches)), "last_result": str(matches["date"].max().date()),
                 "sources": matches.groupby("source").size().to_dict(),
                 "fixtures": int(len(fixtures)), "fixtures_by_league": fixtures.groupby("league").size().to_dict(),
                 "diag": sources.DIAG},
        "model": model.meta,
        "predictions": json.loads(preds.to_json(orient="records", double_precision=4)) if len(preds) else [],
        "live": live, "tables": tables,
    }
    (C.OUTPUT_DIR / "latest.json").write_text(json.dumps(state, indent=1, ensure_ascii=False, default=str))
    if len(preds):
        preds.to_csv(C.OUTPUT_DIR / "latest.csv", index=False, float_format="%.4f")
        (C.OUTPUT_DIR / "predictions" / f"{today}.json").write_text(
            json.dumps(state["predictions"], indent=1, ensure_ascii=False))
    from . import report
    report.build(state)
    if notify:
        from . import notify as nt
        nt.send(preds)
    return state


def single(home: str, away: str, league: str | None = None, odds: list[float] | None = None) -> dict:
    """Pronostico immediato per una coppia qualsiasi (sostituisce il menu manuale della v5)."""
    from .teams import resolve
    p = C.Params()
    matches, _ = sources.load()
    teams = pd.concat([matches["home"], matches["away"]]).unique()
    h, a = resolve(home, teams), resolve(away, teams)
    if not h or not a:
        raise SystemExit(f"Squadra non trovata: {home if not h else away}")
    if league is None:
        last = matches[(matches["home"] == h) | (matches["away"] == h)].iloc[-1]
        league = last["league"]
    today = pd.Timestamp(datetime.now().date())
    fx = pd.DataFrame([{"date": today, "time": "", "league": league, "season": C.season_of(today), "home": h, "away": a,
                        "odds_h": odds[0] if odds else np.nan, "odds_d": odds[1] if odds else np.nan,
                        "odds_a": odds[2] if odds else np.nan, "odds_o25": np.nan, "odds_u25": np.nan,
                        "pin_h": np.nan, "pin_d": np.nan, "pin_a": np.nan}])
    eng, feat, fxf = build(matches, fx, p)
    model = train(feat, matches, p)
    return predict_fixtures(model, fxf, eng, p).iloc[0].to_dict()
