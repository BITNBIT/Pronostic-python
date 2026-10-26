"""Scaricamento e unificazione dati: risultati, statistiche, quote, calendario. Zero input manuale."""
from __future__ import annotations

import io
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import config as C
from .teams import normalize, register_known

log = logging.getLogger("titan.sources")

COLS = ["date", "time", "league", "season", "home", "away", "fthg", "ftag", "hthg", "htag",
        "hs", "as_", "hst", "ast", "hc", "ac", "hy", "ay", "hr", "ar",
        "odds_h", "odds_d", "odds_a", "pin_h", "pin_d", "pin_a", "max_h", "max_d", "max_a",
        "odds_o25", "odds_u25", "source", "prio"]

NUM = [c for c in COLS if c not in ("date", "time", "league", "home", "away", "source")]


# ----------------------------------------------------------------------------- http
_DEAD_HOSTS: set[str] = set()


def http_get(url: str, retries: int = 3) -> bytes | None:
    host = urllib.parse.urlparse(url).netloc
    if host in _DEAD_HOSTS:
        return None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": C.USER_AGENT})
            with urllib.request.urlopen(req, timeout=C.HTTP_TIMEOUT) as r:
                if r.status == 200:
                    return r.read()
                return None
        except urllib.error.HTTPError as e:  # 404 = stagione inesistente: inutile riprovare
            if e.code == 404:
                return None
            log.debug("HTTP %s %s", e.code, url)
        except Exception as e:  # noqa: BLE001
            log.debug("errore rete %s: %s", url, e)
        time.sleep(1.5 * (i + 1))
    log.warning("host non raggiungibile, salto: %s", host)
    _DEAD_HOSTS.add(host)
    return None


def _first(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    out = pd.Series(np.nan, index=df.index, dtype="float64")
    for c in cols:
        if c in df.columns:
            out = out.fillna(pd.to_numeric(df[c], errors="coerce"))
    return out


def _parse_dates(s: pd.Series) -> pd.Series:
    s = s.astype("string").str.strip().str.replace('"', "", regex=False)
    d = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    d = d.fillna(pd.to_datetime(s, format="%d/%m/%y", errors="coerce"))
    d = d.fillna(pd.to_datetime(s, format="%Y-%m-%d", errors="coerce"))
    return d


def _finish(df: pd.DataFrame, source: str, prio: int) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df[df["date"].notna() & df["home"].notna() & df["away"].notna()]
    df["home"] = df["home"].map(normalize)
    df["away"] = df["away"].map(normalize)
    df = df[(df["home"] != "") & (df["away"] != "")]
    df["season"] = df["date"].map(C.season_of).astype(int)
    df["source"] = source
    df["prio"] = prio
    for c in COLS:
        if c not in df.columns:
            df[c] = np.nan
    return df[COLS]


# ----------------------------------------------------------------------------- football-data.co.uk
def _canon_fd(raw: pd.DataFrame, league: str | None = None) -> pd.DataFrame:
    raw = raw.rename(columns=lambda c: str(c).strip().replace("﻿", ""))
    if "HomeTeam" not in raw.columns and "Home" in raw.columns:
        raw = raw.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam", "HG": "FTHG", "AG": "FTAG"})
    if "HomeTeam" not in raw.columns:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(index=raw.index)
    df["date"] = _parse_dates(raw["Date"])
    # football-data usa l'ora UK: +1h per l'ora italiana (stesso cambio ora legale)
    if "Time" in raw.columns:
        t = pd.to_datetime(raw["Time"].astype("string").str.strip(), format="%H:%M", errors="coerce") + pd.Timedelta(hours=1)
        df["time"] = t.dt.strftime("%H:%M")
    else:
        df["time"] = pd.NA
    df["league"] = raw["Div"].astype("string").str.strip() if "Div" in raw.columns else league
    df["home"] = raw["HomeTeam"]
    df["away"] = raw["AwayTeam"]
    m = {"fthg": ["FTHG"], "ftag": ["FTAG"], "hthg": ["HTHG"], "htag": ["HTAG"], "hs": ["HS"], "as_": ["AS"],
         "hst": ["HST"], "ast": ["AST"], "hc": ["HC"], "ac": ["AC"], "hy": ["HY"], "ay": ["AY"],
         "hr": ["HR"], "ar": ["AR"],
         "odds_h": ["AvgH", "BbAvH", "B365H", "WHH", "BWH", "IWH", "LBH", "SBH", "GBH", "VCH"],
         "odds_d": ["AvgD", "BbAvD", "B365D", "WHD", "BWD", "IWD", "LBD", "SBD", "GBD", "VCD"],
         "odds_a": ["AvgA", "BbAvA", "B365A", "WHA", "BWA", "IWA", "LBA", "SBA", "GBA", "VCA"],
         "pin_h": ["PSH", "PSCH"], "pin_d": ["PSD", "PSCD"], "pin_a": ["PSA", "PSCA"],
         "max_h": ["MaxH", "BbMxH"], "max_d": ["MaxD", "BbMxD"], "max_a": ["MaxA", "BbMxA"],
         "odds_o25": ["Avg>2.5", "BbAv>2.5", "B365>2.5", "P>2.5", "GB>2.5"],
         "odds_u25": ["Avg<2.5", "BbAv<2.5", "B365<2.5", "P<2.5", "GB<2.5"]}
    for k, cols in m.items():
        df[k] = _first(raw, cols)
    return df


def _read_fd_bytes(b: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(b), encoding="latin1", on_bad_lines="skip", low_memory=False)


def fetch_football_data(seasons: list[int], refresh: set[int]) -> pd.DataFrame:
    cache = C.RAW_DIR / "fd"
    cache.mkdir(parents=True, exist_ok=True)
    frames = []
    for div, meta in C.LEAGUES.items():
        for s in seasons:
            if s < meta["fd_first"]:
                continue
            f = cache / f"{div}_{C.fd_code(s)}.csv"
            if s in refresh or not f.exists():
                b = http_get(C.FD_BASE.format(code=C.fd_code(s), div=div))
                if b and len(b) > 200:
                    f.write_bytes(b)
            if f.exists():
                try:
                    frames.append(_canon_fd(_read_fd_bytes(f.read_bytes()), div).assign(league=div))
                except Exception as e:  # noqa: BLE001
                    log.warning("football-data %s parse error: %s", f.name, e)
    if not frames:
        return pd.DataFrame(columns=COLS)
    out = pd.concat(frames, ignore_index=True)
    out = out[out["fthg"].notna() & out["ftag"].notna()]
    return _finish(out, "football-data", 0)


def fetch_fd_fixtures() -> pd.DataFrame:
    b = http_get(C.FD_FIXTURES)
    if not b:
        return pd.DataFrame(columns=COLS)
    (C.RAW_DIR / "fd_fixtures.csv").write_bytes(b)
    df = _canon_fd(_read_fd_bytes(b))
    df = df[df["league"].isin(list(C.LEAGUES))]
    df["fthg"] = np.nan
    df["ftag"] = np.nan
    return _finish(df, "football-data", 0)


# ----------------------------------------------------------------------------- clubdata mirror (GitHub)
def fetch_clubdata(force: bool = False) -> pd.DataFrame:
    f = C.RAW_DIR / "clubdata_it.csv"
    if force or not f.exists():
        b = http_get(C.CLUBDATA_URL)
        if b:
            raw = pd.read_csv(io.BytesIO(b), low_memory=False)
            raw[raw["Division"].isin(list(C.LEAGUES))].to_csv(f, index=False)
    if not f.exists():
        return pd.DataFrame(columns=COLS)
    raw = pd.read_csv(f, low_memory=False)
    df = pd.DataFrame({
        "date": pd.to_datetime(raw["MatchDate"], errors="coerce"),
        "time": raw.get("MatchTime"),
        "league": raw["Division"], "home": raw["HomeTeam"], "away": raw["AwayTeam"],
        "fthg": raw["FTHome"], "ftag": raw["FTAway"], "hthg": raw["HTHome"], "htag": raw["HTAway"],
        "hs": raw["HomeShots"], "as_": raw["AwayShots"], "hst": raw["HomeTarget"], "ast": raw["AwayTarget"],
        "hc": raw["HomeCorners"], "ac": raw["AwayCorners"], "hy": raw["HomeYellow"], "ay": raw["AwayYellow"],
        "hr": raw["HomeRed"], "ar": raw["AwayRed"],
        "odds_h": raw["OddHome"], "odds_d": raw["OddDraw"], "odds_a": raw["OddAway"],
        "max_h": raw["MaxHome"], "max_d": raw["MaxDraw"], "max_a": raw["MaxAway"],
        "odds_o25": raw["Over25"], "odds_u25": raw["Under25"],
    })
    df = df[df["fthg"].notna()]
    return _finish(df, "clubdata", 1)


# ----------------------------------------------------------------------------- openfootball
def _of_score(m: dict):
    sc = m.get("score")
    if isinstance(sc, dict):
        ft, ht = sc.get("ft"), sc.get("ht")
    elif isinstance(sc, list):
        ft, ht = sc, None
    else:
        ft, ht = None, None
    if ft is None and "score1" in m:
        ft = [m.get("score1"), m.get("score2")]
    ok = isinstance(ft, list) and len(ft) == 2 and all(isinstance(x, int) for x in ft)
    okh = isinstance(ht, list) and len(ht) == 2 and all(isinstance(x, int) for x in ht)
    return (ft if ok else [None, None]), (ht if okh else [None, None])


def fetch_openfootball(seasons: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for div, meta in C.LEAGUES.items():
        for s in seasons:
            tag = f"{s}-{(s + 1) % 100:02d}"
            b = http_get(C.OF_BASE.format(season=tag, code=meta["of_code"]), retries=2)
            if not b:
                continue
            try:
                data = json.loads(b)
            except Exception:  # noqa: BLE001
                continue
            for m in data.get("matches", []):
                ft, ht = _of_score(m)
                rows.append({"date": m.get("date"), "time": m.get("time"), "league": div,
                             "home": m.get("team1"), "away": m.get("team2"),
                             "fthg": ft[0], "ftag": ft[1], "hthg": ht[0], "htag": ht[1]})
    if not rows:
        e = pd.DataFrame(columns=COLS)
        return e, e
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = _finish(df, "openfootball", 3)
    played = df[df["fthg"].notna()]
    future = df[df["fthg"].isna()]
    return played, future


# ----------------------------------------------------------------------------- legacy txt (v5)
def load_legacy() -> pd.DataFrame:
    frames = []
    for div, meta in C.LEAGUES.items():
        f = C.LEGACY_DIR / meta["legacy"]
        if not f.exists():
            continue
        raw = pd.read_csv(f, header=None, names=["d", "h", "a", "hg", "ag"], quotechar='"',
                          skipinitialspace=True, encoding="latin1", on_bad_lines="skip", dtype=str)
        df = pd.DataFrame({"date": _parse_dates(raw["d"]), "league": div,
                           "home": raw["h"].str.strip(), "away": raw["a"].str.strip(),
                           "fthg": pd.to_numeric(raw["hg"], errors="coerce"),
                           "ftag": pd.to_numeric(raw["ag"], errors="coerce")})
        frames.append(df[df["fthg"].notna()])
    if not frames:
        return pd.DataFrame(columns=COLS)
    return _finish(pd.concat(frames, ignore_index=True), "legacy", 4)


# ----------------------------------------------------------------------------- merge
def merge_sources(frames: list[pd.DataFrame], gap_days: int = 4) -> pd.DataFrame:
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return pd.DataFrame(columns=COLS)
    df = pd.concat(frames, ignore_index=True)
    df = df[df["home"] != df["away"]]
    df = df.sort_values(["league", "season", "home", "away", "date", "prio"]).reset_index(drop=True)
    key = ["league", "season", "home", "away"]
    same = (df[key].eq(df[key].shift())).all(axis=1)
    gap = df["date"].diff().dt.days.abs().fillna(999) > gap_days
    df["_cl"] = (~same | gap).cumsum()
    # stessa partita con date diverse tra fonti (rinvii/errori): tieni solo i cluster della fonte migliore
    gmin = df.groupby(key)["prio"].transform("min")
    cmin = df.groupby("_cl")["prio"].transform("min")
    df = df[cmin == gmin]
    df = df.sort_values(["_cl", "prio"])
    out = df.groupby("_cl", sort=False).first().reset_index(drop=True)
    for c in NUM:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["season"] = out["season"].astype(int)
    return out.sort_values(["date", "league", "home"]).reset_index(drop=True)[COLS]


def _validate_odds(df: pd.DataFrame) -> pd.DataFrame:
    for p in ("odds", "pin", "max"):
        cols = [f"{p}_h", f"{p}_d", f"{p}_a"]
        bad = (df[cols] <= 1.0).any(axis=1) | (df[cols] > 100).any(axis=1)
        df.loc[bad, cols] = np.nan
    return df


def update(full: bool = False, offline: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggiorna data/matches.csv e data/fixtures.csv. Ritorna (matches, fixtures)."""
    C.ensure_dirs()
    cur = C.current_season()
    frames = []
    existing = None
    if C.MATCHES_CSV.exists() and not full:
        existing = pd.read_csv(C.MATCHES_CSV, parse_dates=["date"], low_memory=False)
        existing["source"] = existing["source"].fillna("cache")
        existing["prio"] = 2
        frames.append(existing)
    legacy = load_legacy()
    register_known(pd.concat([legacy["home"], legacy["away"]]).unique()) if len(legacy) else None
    if existing is not None:
        register_known(pd.concat([existing["home"], existing["away"]]).unique())
    frames.append(legacy)

    fx = []
    if not offline:
        if existing is None:
            seasons = list(range(1993, cur + 1))
            refresh = {cur, cur - 1}
            cd = fetch_clubdata()
            if len(cd):
                register_known(pd.concat([cd["home"], cd["away"]]).unique())
            frames.append(cd)
        else:
            seasons = [cur - 1, cur]
            refresh = {cur, cur - 1}
        fd = fetch_football_data(seasons, refresh)
        log.info("football-data: %d partite", len(fd))
        if len(fd):
            register_known(pd.concat([fd["home"], fd["away"]]).unique())
        frames.append(fd)
        of_played, of_future = fetch_openfootball([cur - 1, cur])
        log.info("openfootball: %d giocate, %d future", len(of_played), len(of_future))
        frames.append(of_played)
        fx = [fetch_fd_fixtures(), of_future]

    matches = _validate_odds(merge_sources(frames))
    matches = matches[matches["date"] <= pd.Timestamp(date.today() + timedelta(days=1))]
    matches.to_csv(C.MATCHES_CSV, index=False, date_format="%Y-%m-%d")

    fixtures = build_fixtures(fx, matches)
    fixtures.to_csv(C.FIXTURES_CSV, index=False, date_format="%Y-%m-%d")
    return matches, fixtures


def build_fixtures(fx: list[pd.DataFrame], matches: pd.DataFrame, days: int | None = None) -> pd.DataFrame:
    days = days or C.Params().fixtures_days_ahead
    fx = [f for f in fx if f is not None and len(f)]
    if not fx:
        if C.FIXTURES_CSV.exists():
            old = pd.read_csv(C.FIXTURES_CSV, parse_dates=["date"])
            today = pd.Timestamp(date.today())
            return old[old["date"] >= today]
        return pd.DataFrame(columns=COLS)
    df = merge_sources(fx, gap_days=10)
    today = pd.Timestamp(date.today())
    df = df[(df["date"] >= today) & (df["date"] <= today + pd.Timedelta(days=days))]
    # rimuovi partite già giocate
    played = set(zip(matches["league"], matches["season"], matches["home"], matches["away"]))
    df = df[[k not in played for k in zip(df["league"], df["season"], df["home"], df["away"])]]
    df = _validate_odds(df.drop(columns=["fthg", "ftag"]).assign(fthg=np.nan, ftag=np.nan))
    return df.sort_values(["date", "time", "league"], na_position="last").reset_index(drop=True)[COLS]


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    m = pd.read_csv(C.MATCHES_CSV, parse_dates=["date"], low_memory=False)
    f = pd.read_csv(C.FIXTURES_CSV, parse_dates=["date"]) if C.FIXTURES_CSV.exists() else pd.DataFrame(columns=COLS)
    register_known(pd.concat([m["home"], m["away"]]).unique())
    return m, f
