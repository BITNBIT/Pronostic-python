"""Normalizzazione nomi squadra. Nome canonico = stile football-data.co.uk ("Inter", "Milan", ...)."""
from __future__ import annotations

import difflib
import re
import unicodedata

ALIASES = {
    "fc internazionale milano": "Inter", "internazionale": "Inter", "inter milan": "Inter",
    "ac milan": "Milan", "juventus fc": "Juventus", "juve": "Juventus",
    "as roma": "Roma", "ss lazio": "Lazio", "ssc napoli": "Napoli", "atalanta bc": "Atalanta",
    "acf fiorentina": "Fiorentina", "bologna fc 1909": "Bologna", "torino fc": "Torino",
    "udinese calcio": "Udinese", "genoa cfc": "Genoa", "hellas verona fc": "Verona", "hellas verona": "Verona",
    "chievo verona": "Chievo", "ac chievo verona": "Chievo",
    "us lecce": "Lecce", "cagliari calcio": "Cagliari", "como 1907": "Como",
    "parma calcio 1913": "Parma", "us cremonese": "Cremonese", "ac pisa 1909": "Pisa", "pisa sc": "Pisa",
    "us sassuolo calcio": "Sassuolo", "sassuolo calcio": "Sassuolo", "ac monza": "Monza",
    "empoli fc": "Empoli", "venezia fc": "Venezia", "frosinone calcio": "Frosinone",
    "us salernitana 1919": "Salernitana", "spezia calcio": "Spezia", "uc sampdoria": "Sampdoria",
    "palermo fc": "Palermo", "ssc bari": "Bari", "brescia calcio": "Brescia", "as cittadella": "Cittadella",
    "calcio padova": "Padova", "carrarese calcio": "Carrarese", "cesena fc": "Cesena",
    "cosenza calcio": "Cosenza", "delfino pescara": "Pescara", "delfino pescara 1936": "Pescara",
    "fc sudtirol": "Sudtirol", "sudtirol": "Sudtirol", "juve stabia": "Juve Stabia", "ss juve stabia": "Juve Stabia",
    "mantova 1911 ssd": "Mantova", "mantova 1911": "Mantova", "modena fc": "Modena", "us avellino": "Avellino",
    "us avellino 1912": "Avellino", "us catanzaro": "Catanzaro", "us catanzaro 1929": "Catanzaro",
    "virtus entella": "Virtus Entella", "entella": "Virtus Entella", "ac reggiana 1919": "Reggiana",
    "ac reggiana": "Reggiana", "spal 2013": "Spal", "ternana calcio": "Ternana", "ascoli calcio": "Ascoli",
    "benevento calcio": "Benevento", "us arezzo": "Arezzo", "ss arezzo": "Arezzo", "lr vicenza": "Vicenza",
    "calcio lecco 1912": "Lecco", "feralpisalo": "FeralpiSalo", "feralpi salo": "FeralpiSalo",
    "ac perugia calcio": "Perugia", "reggina 1914": "Reggina", "us triestina": "Triestina",
    "calcio foggia 1920": "Foggia", "us alessandria": "Alessandria", "pordenone calcio": "Pordenone",
    "virtus francavilla": "Francavilla", "crotone fc": "Crotone", "fc crotone": "Crotone",
    "novara calcio": "Novara", "l r vicenza": "Vicenza", "vicenza calcio": "Vicenza",
    "south tyrol": "Sudtirol", "us livorno": "Livorno", "as livorno": "Livorno",
}

_STOP = {"fc", "ac", "as", "us", "ss", "ssc", "acf", "cfc", "bc", "calcio", "sc", "ssd", "uc", "asd", "1909",
         "1907", "1913", "1919", "1912", "1929", "1911", "1914", "1920", "1936", "srl", "spa"}

_known: set[str] = set()


def _strip(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9 ]+", " ", s).lower()
    return re.sub(r"\s+", " ", s).strip()


def _core(s: str) -> str:
    return " ".join(w for w in _strip(s).split() if w not in _STOP and not w.isdigit())


def register_known(names) -> None:
    for n in names:
        if isinstance(n, str) and n.strip():
            _known.add(n.strip())


def normalize(name) -> str:
    if not isinstance(name, str):
        return ""
    raw = name.strip()
    if raw in _known:
        return raw
    key = _strip(raw)
    if key in ALIASES:
        return ALIASES[key]
    core = _core(raw)
    if core in ALIASES:
        return ALIASES[core]
    if _known:
        by_core = {_core(k): k for k in _known}
        if core in by_core:
            return by_core[core]
        m = difflib.get_close_matches(core, list(by_core), n=1, cutoff=0.86)
        if m:
            return by_core[m[0]]
        # nome noto contenuto come parola intera ("Calcio Lecco" -> "Lecco"), solo se univoco
        toks = core.split()
        hits = [v for k, v in by_core.items() if k and all(t in toks for t in k.split())]
        if len(hits) == 1:
            return hits[0]
    return raw if raw == raw.title() or raw[:1].isupper() else raw.title()


def resolve(name: str, candidates) -> str | None:
    """Ricerca tollerante per input utente (es. 'juve' -> 'Juventus')."""
    n = normalize(name)
    cands = list(candidates)
    if n in cands:
        return n
    low = {c.lower(): c for c in cands}
    if name.strip().lower() in low:
        return low[name.strip().lower()]
    m = difflib.get_close_matches(name.strip().lower(), list(low), n=1, cutoff=0.6)
    return low[m[0]] if m else None
