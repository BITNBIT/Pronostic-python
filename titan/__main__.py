"""CLI TITAN v6.

  python -m titan run              # tutto automatico: aggiorna dati, allena, pronostica, verifica, report
  python -m titan backtest         # backtest walk-forward ultime stagioni -> output/backtest.json
  python -m titan predict Inter Milan [--odds 2.1 3.3 3.6]
  python -m titan table [I1|I2]
  python -m titan update [--full]
"""
from __future__ import annotations

import argparse
import logging
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog="titan", description="TITAN v6 – pronostici calcio automatici")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--offline", action="store_true", help="non scarica nulla, usa i dati locali")
    r.add_argument("--retrain", action="store_true")
    r.add_argument("--no-notify", action="store_true")
    u = sub.add_parser("update")
    u.add_argument("--full", action="store_true", help="ricostruisce lo storico da zero")
    sub.add_parser("backtest")
    sub.add_parser("report")
    pr = sub.add_parser("predict")
    pr.add_argument("home")
    pr.add_argument("away")
    pr.add_argument("--league", choices=["I1", "I2"])
    pr.add_argument("--odds", nargs=3, type=float, metavar=("Q1", "QX", "Q2"))
    t = sub.add_parser("table")
    t.add_argument("league", nargs="?", default="I1")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    from . import config as C

    if a.cmd == "run":
        from .pipeline import run
        st = run(offline=a.offline, force_train=a.retrain, notify=not a.no_notify)
        print((C.OUTPUT_DIR / "PRONOSTICI.md").read_text(encoding="utf-8"))
        print(f"Dashboard: {C.DOCS_DIR / 'index.html'}  ·  pronostici: {len(st['predictions'])}")
    elif a.cmd == "update":
        from .sources import update
        m, f = update(full=a.full)
        print(f"partite: {len(m)}  prossime: {len(f)}  ultimo risultato: {m['date'].max().date()}")
    elif a.cmd == "backtest":
        from . import backtest, sources
        from .engine import RatingEngine
        m, _ = sources.load()
        res = backtest.run(RatingEngine().run(m))
        o = res["overall"]
        for s in res["seasons"]:
            b = s["bets"]
            print(f"{s['season']}: acc {s['acc']:.1%} (mercato {s['acc_mk'] or 0:.1%})  logloss {s['ll']:.4f} "
                  f"(mercato {s['ll_mk']})  value bet {b['n']} ROI {b['roi'] if b['roi'] is not None else '-'}")
        print(f"TOTALE {o['n']} partite: acc {o['acc']:.1%}  logloss {o['ll']}  mercato {o['ll_mk']}")
        from .report import build
        import json
        f = C.OUTPUT_DIR / "latest.json"
        if f.exists():
            build(json.loads(f.read_text()))
    elif a.cmd == "report":
        import json
        from .report import build
        build(json.loads((C.OUTPUT_DIR / "latest.json").read_text()))
    elif a.cmd == "predict":
        from .pipeline import single
        p = single(a.home, a.away, a.league, a.odds)
        print(f"\n{p['home']} - {p['away']} ({C.LEAGUES[p['league']]['name']})")
        print(f"  1 {p['p1']:.1%}   X {p['px']:.1%}   2 {p['p2']:.1%}   -> {p['pick']} {'*' * p['stars']}")
        print(f"  doppia {p['dc']} {p['dc_p']:.1%}  |  Over2.5 {p['o25']:.1%}  GG {p['gg']:.1%}")
        print(f"  xG {p['xg_h']:.2f}-{p['xg_a']:.2f}  esatti: {p['top_scores']}")
        print(f"  Elo {p['elo_h']:.0f} vs {p['elo_a']:.0f}  forma {p['form_h']} / {p['form_a']}")
        if isinstance(p.get("vb_bet"), str):
            print(f"  VALUE BET: {p['vb_bet']} @{p['vb_odds']:.2f} edge {p['vb_edge']:+.1%}")
    elif a.cmd == "table":
        from . import sources
        from .engine import RatingEngine
        m, _ = sources.load()
        e = RatingEngine()
        e.run(m)
        print(e.table(a.league).to_string())


if __name__ == "__main__":
    main()
