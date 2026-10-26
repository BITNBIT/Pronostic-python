"""Configurazione centrale TITAN v6. Tutto modificabile da variabili d'ambiente."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("TITAN_ROOT", Path(__file__).resolve().parent.parent))
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
LEGACY_DIR = DATA_DIR / "legacy"
MODELS_DIR = ROOT / "models"
OUTPUT_DIR = ROOT / "output"
DOCS_DIR = ROOT / "docs"

MATCHES_CSV = DATA_DIR / "matches.csv"
FIXTURES_CSV = DATA_DIR / "fixtures.csv"
HISTORY_CSV = OUTPUT_DIR / "history.csv"

LEAGUES = {
    "I1": {"name": "Serie A", "level": 1, "fd_first": 1993, "of_code": "it.1", "espn": "ita.1", "legacy": "storicoseriea.txt"},
    "I2": {"name": "Serie B", "level": 2, "fd_first": 1997, "of_code": "it.2", "espn": "ita.2", "legacy": "storicoserieb.txt"},
}

FD_BASE = "https://www.football-data.co.uk/mmz4281/{code}/{div}.csv"
FD_FIXTURES = "https://www.football-data.co.uk/fixtures.csv"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard?dates={d1}-{d2}&limit=300"
OF_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{code}.json"
# mirror GitHub del dataset football-data (quote incluse) usato come fallback storico
CLUBDATA_URL = "https://raw.githubusercontent.com/xgabora/Club-Football-Match-Data-2000-2025/main/data/Matches.csv"

HTTP_TIMEOUT = int(os.environ.get("TITAN_HTTP_TIMEOUT", 30))
USER_AGENT = "TITAN-v6 (+https://github.com/BITNBIT/Pronostic-python)"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


def season_of(d) -> int:
    """Anno di inizio stagione: da agosto -> anno, prima -> anno-1 (2019/20 finita ad agosto 2020)."""
    start = (9, 1) if d.year == 2020 else (8, 1)
    return d.year if (d.month, d.day) >= start else d.year - 1


def current_season() -> int:
    return season_of(date.today())


def fd_code(season: int) -> str:
    return f"{season % 100:02d}{(season + 1) % 100:02d}"


@dataclass
class Params:
    # Elo
    elo_k: float = 20.0
    elo_hfa: float = 60.0
    elo_regress: float = 0.20          # regressione verso la media della lega a inizio stagione
    # Poisson online (attacco/difesa)
    pois_lr: float = 0.045
    pois_regress: float = 0.25
    # inserimento squadre nuove (quantile della lega di arrivo)
    q_promoted: float = 0.20
    # training
    train_from_season: int = 2000      # prima di questa stagione i dati servono solo a scaldare i rating
    backtest_seasons: int = 8
    # value bet
    min_prob_value: float = 0.20       # prob minima per proporre value bet
    min_edge: float = 0.05             # edge minimo (p*quota-1)
    max_odds_value: float = 6.0        # niente quote troppo alte (varianza)
    kelly_fraction: float = 0.25
    kelly_cap: float = 0.03            # max 3% bankroll per giocata
    fixtures_days_ahead: int = int(os.environ.get("TITAN_DAYS_AHEAD", 10))
    extra: dict = field(default_factory=dict)


def ensure_dirs() -> None:
    for d in (DATA_DIR, RAW_DIR, MODELS_DIR, OUTPUT_DIR, DOCS_DIR, OUTPUT_DIR / "predictions"):
        d.mkdir(parents=True, exist_ok=True)
