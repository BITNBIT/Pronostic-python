"""Backtest walk-forward onesto: per ogni stagione S si allena solo su stagioni < S e si prevede S."""
from __future__ import annotations

import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from . import betting, markets
from . import config as C
from .models import DualModel, logloss, rps, target

log = logging.getLogger("titan.backtest")


def run(feat: pd.DataFrame, p: C.Params | None = None, seasons: list[int] | None = None) -> dict:
    p = p or C.Params()
    data = feat[feat["season"] >= p.train_from_season].copy()
    all_s = sorted(data["season"].unique())
    complete = [s for s in all_s if (data["season"] == s).sum() >= 300]
    seasons = seasons or complete[-p.backtest_seasons:]
    preds = []
    per = []
    for s in seasons:
        tr = data[data["season"] < s]
        te = data[data["season"] == s]
        if len(te) == 0 or tr["season"].nunique() < 4:
            continue
        m = DualModel().fit(tr)
        pr = m.predict(te)
        pp = m.pure.predict(te)  # modello senza quote, per confronto
        y = target(te)
        P = pr[["p1", "px", "p2"]].to_numpy()
        mk = te[["mk_h", "mk_d", "mk_a"]].to_numpy(float)
        ok = np.isfinite(mk).all(1)
        o25y = (te["fthg"] + te["ftag"] > 2.5).to_numpy(int)
        bets = betting.settle(betting.pick_value(pr, te, p), te)
        row = {"season": f"{s}/{(s + 1) % 100:02d}", "n": int(len(te)),
               "acc": round(float((P.argmax(1) == y).mean()), 4),
               "acc_mk": round(float((mk[ok].argmax(1) == y[ok]).mean()), 4) if ok.any() else None,
               "ll": round(logloss(y, P), 4),
               "ll_mk": round(logloss(y[ok], mk[ok]), 4) if ok.any() else None,
               "ll_model_on_mk_rows": round(logloss(y[ok], P[ok]), 4) if ok.any() else None,
               "rps": round(rps(y, P), 4),
               "acc_pure": round(float((pp[["p1", "px", "p2"]].to_numpy().argmax(1) == y).mean()), 4),
               "ll_pure": round(logloss(y, pp[["p1", "px", "p2"]].to_numpy()), 4),
               "acc_o25": round(float(((pr["o25"].to_numpy() > 0.5) == o25y).mean()), 4),
               "bets": betting.summary(bets), "weights": m.mk.meta.get("weights"), "weights_pure": m.pure.meta.get("weights")}
        per.append(row)
        log.info("backtest %s: acc %.3f ll %.4f (mk %s) bets %s", row["season"], row["acc"], row["ll"], row["ll_mk"],
                 row["bets"])
        pr = pr.assign(pure_p1=pp["p1"], pure_px=pp["px"], pure_p2=pp["p2"], y=y, season=s, o25y=o25y, date=te["date"].to_numpy(), league=te["league"].to_numpy())
        preds.append((pr, te))

    allp = pd.concat([x[0] for x in preds])
    allt = pd.concat([x[1] for x in preds])
    y = allp["y"].to_numpy()
    P = allp[["p1", "px", "p2"]].to_numpy()
    mk = allt[["mk_h", "mk_d", "mk_a"]].to_numpy(float)
    ok = np.isfinite(mk).all(1)

    # calibrazione: probabilità prevista vs frequenza reale (tutti gli esiti)
    flat_p = P.ravel()
    flat_y = np.eye(3)[y].ravel()
    bins = np.linspace(0, 1, 11)
    cal = []
    for a, b in zip(bins[:-1], bins[1:]):
        sel = (flat_p >= a) & (flat_p < b)
        if sel.sum() >= 30:
            cal.append({"bin": f"{a:.1f}-{b:.1f}", "pred": round(float(flat_p[sel].mean()), 4),
                        "real": round(float(flat_y[sel].mean()), 4), "n": int(sel.sum())})

    # sensibilità soglia edge (quote medie e quote massime)
    sweep = []
    for e in (0.0, 0.02, 0.05, 0.08, 0.12, 0.2):
        s_avg = betting.summary(betting.settle(betting.pick_value(allp, allt.set_index(allp.index), p, "odds", e), allt.set_index(allp.index)))
        s_max = betting.summary(betting.settle(betting.pick_value(allp, allt.set_index(allp.index), p, "max", e), allt.set_index(allp.index)))
        sweep.append({"edge": e, "avg_odds": s_avg, "max_odds": s_max})

    # fasce di confidenza (prob. massima)
    conf = []
    pm = P.max(1)
    for a, b in ((0.0, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 1.01)):
        sel = (pm >= a) & (pm < b)
        if sel.sum():
            conf.append({"range": f"{a:.0%}-{min(b, 1):.0%}", "n": int(sel.sum()),
                         "acc": round(float((P[sel].argmax(1) == y[sel]).mean()), 4)})

    # mercati: calibrazione e "pronostico più probabile"
    hg, ag = allt["fthg"].to_numpy(int), allt["ftag"].to_numpy(int)
    MP = markets.probs(allp)
    mk_cal = []
    for k in MP.columns:
        h = markets.hit(k, hg, ag)
        top = MP[k].to_numpy() >= 0.70
        mk_cal.append({"market": k, "pred": round(float(MP[k].mean()), 4), "real": round(float(h.mean()), 4),
                       "n70": int(top.sum()), "hit70": round(float(h[top].mean()), 4) if top.any() else None})
    sp = markets.best_pick(allp)
    sh = np.array([markets.hit(m, [a], [b])[0] for m, a, b in zip(sp["safe_pick"], hg, ag)])
    safe = []
    for thr in (0.0, 0.65, 0.70, 0.75, 0.80, 0.85):
        sel = sp["safe_p"].to_numpy() >= thr
        if sel.sum() >= 20:
            safe.append({"min_p": thr, "n": int(sel.sum()), "share": round(float(sel.mean()), 4),
                         "pred": round(float(sp["safe_p"].to_numpy()[sel].mean()), 4),
                         "hit": round(float(sh[sel].mean()), 4)})
    safe_mix = sp["safe_pick"].value_counts(normalize=True).round(3).to_dict()

    res = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "markets": mk_cal, "safe": safe, "safe_mix": safe_mix,
        "seasons": per,
        "overall": {"n": int(len(y)), "acc": round(float((P.argmax(1) == y).mean()), 4), "ll": round(logloss(y, P), 4),
                    "rps": round(rps(y, P), 4),
                    "ll_mk": round(logloss(y[ok], mk[ok]), 4) if ok.any() else None,
                    "ll_model_on_mk_rows": round(logloss(y[ok], P[ok]), 4) if ok.any() else None,
                    "acc_mk": round(float((mk[ok].argmax(1) == y[ok]).mean()), 4) if ok.any() else None,
                    "ll_uniform": round(float(np.log(3)), 4),
                    "acc_pure": round(float((allp[["pure_p1", "pure_px", "pure_p2"]].to_numpy().argmax(1) == y).mean()), 4),
                    "ll_pure": round(logloss(y, allp[["pure_p1", "pure_px", "pure_p2"]].to_numpy()), 4),
                    "acc_o25": round(float(((allp["o25"].to_numpy() > 0.5) == allp["o25y"].to_numpy()).mean()), 4)},
        "calibration": cal, "edge_sweep": sweep, "confidence": conf,
    }
    C.ensure_dirs()
    (C.OUTPUT_DIR / "backtest.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    return res
