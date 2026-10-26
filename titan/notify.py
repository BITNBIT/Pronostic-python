"""Notifiche Telegram (opzionali): imposta TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (secrets GitHub)."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

from . import config as C

log = logging.getLogger("titan.notify")
SENT = C.OUTPUT_DIR / "telegram_sent.json"


def _post(text: str) -> bool:
    url = f"https://api.telegram.org/bot{C.TELEGRAM_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": C.TELEGRAM_CHAT, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram: %s", e)
        return False


def send(preds: pd.DataFrame, hours: int = 48) -> int:
    """Invia una sola volta i pronostici delle partite nelle prossime `hours` ore."""
    if not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT) or preds is None or preds.empty:
        return 0
    sent = set(json.loads(SENT.read_text())) if SENT.exists() else set()
    lim = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d")
    p = preds[(preds["date"] <= lim)]
    p = p[[f"{r.league}-{r.season}-{r.home}-{r.away}" not in sent for r in p.itertuples()]]
    if p.empty:
        return 0
    lines = ["<b>⚽ TITAN v6 – pronostici</b>"]
    for r in p.itertuples():
        star = "★" * int(r.stars)
        vb = f"\n   📊 valore statistico: {r.vb_bet} @{r.vb_odds:.2f}" if isinstance(r.vb_bet, str) else ""
        lines.append(f"\n<b>{r.home} - {r.away}</b> ({C.LEAGUES[r.league]['name']}, {r.date} {r.time})\n"
                     f"   {r.pick} {r.conf:.0%} {star} | 1 {r.p1:.0%} X {r.px:.0%} 2 {r.p2:.0%}\n"
                     f"   più probabile: <b>{r.safe_pick}</b> {r.safe_p:.0%} · {r.ou_pick} · {r.gg_pick} · esatto {r.score}{vb}")
    lines.append("\n<i>Analisi statistica, non consiglio di gioco. Vietato ai minori di 18 anni.</i>")
    text, ok = "", True
    for ln in lines:  # Telegram: max 4096 caratteri per messaggio
        if len(text) + len(ln) > 3800:
            ok &= _post(text)
            text = ""
        text += ln + "\n"
    ok &= _post(text)
    if ok:
        sent |= {f"{r.league}-{r.season}-{r.home}-{r.away}" for r in p.itertuples()}
        SENT.write_text(json.dumps(sorted(sent)))
    return len(p)
