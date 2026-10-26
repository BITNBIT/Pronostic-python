# Pronostic-python · TITAN v6

Sistema **automatico** di pronostici per Serie A e Serie B. Non va toccato niente a mano: ogni giorno GitHub Actions scarica risultati, quote e calendario, aggiorna i rating, riallena il modello, genera i pronostici, verifica quelli passati e pubblica la dashboard.

☕ Offrimi un caffè: https://buymeacoffee.com/bitnbit · Video (v5): https://youtu.be/kU5DPSxOFEk · Sito: https://bitnbit.com

> **IL GIOCO È VIETATO AI MINORI DI 18 ANNI.** Progetto a scopo educativo/statistico. Nessuna garanzia di vincita: le scommesse comportano perdite. L'autore non si assume alcuna responsabilità.

## Cosa fa (giro automatico giornaliero)

| Passo | Dettaglio |
|---|---|
| Dati | football-data.co.uk (risultati, tiri, quote medie/Pinnacle/max, Over/Under, calendario con quote) + openfootball (risultati/calendario di riserva) + mirror storico + vecchi file v5. Nomi squadra normalizzati, duplicati rimossi |
| Rating | Elo con margine gol e regressione a inizio stagione, attacco/difesa Poisson online, forma 5/10, rendimento casa/trasferta, tiri e tiri in porta, riposo, classifica calcolata dai risultati |
| Modelli | LightGBM + regressione logistica (1X2), Poisson-boosting + Dixon-Coles (gol, risultato esatto, O/U, GG, multigol), probabilità del mercato. Blend con pesi stimati out-of-sample sulle ultime 3 stagioni |
| Doppio modello | con quote (partite già quotate) e "solo campo" (quote non ancora disponibili) |
| Output | 1X2, doppia chance, O/U 1.5/2.5/3.5, GG/NG, multigol, top-5 risultati esatti, xG, stelle di confidenza, **value bet** (edge ≥ 5%, stake Kelly 1/4, max 3%) |
| Verifica | ogni pronostico viene salvato prima della partita e controllato a risultato acquisito (`output/history.csv`): accuratezza e ROI reali |
| Report | `docs/index.html` (dashboard, GitHub Pages), `output/PRONOSTICI.md`, `output/latest.json/csv`, Telegram opzionale |

## Risultati del backtest (walk-forward, 8 stagioni 2018/19 → 2025/26, 6.042 partite mai viste in training)

| | Accuratezza 1X2 | Log-loss |
|---|---|---|
| TITAN v6 (con quote) | **49,9%** | **1,0010** |
| Mercato (quote bookmaker) | 49,7% | 1,0043 |
| TITAN v6 solo campo | 48,5% | 1,0157 |
| Caso | 33,3% | 1,0986 |

- Probabilità ben calibrate: quando dice 70%, succede circa il 70% delle volte. Confidenza ≥ 65%: 69–80% di pronostici azzeccati.
- Value bet (edge ≥ 5%, quote medie): 521 giocate, ROI simulato **+14%**. È un segnale interessante ma **non una certezza**: campione piccolo e concentrato nelle ultime stagioni, quote medie non sempre disponibili, mercati che si adattano. Lo storico live in dashboard dice la verità nel tempo.
- La v5 dichiarava accuratezze più alte perché calcolava le statistiche sull'intero storico, **compresa la partita da prevedere** (leakage). La v6 usa solo informazioni disponibili prima del calcio d'inizio.

## Automazione (zero lavoro manuale)

Il workflow `.github/workflows/titan.yml` gira:
- ogni giorno alle ~07:10 (risultati, rating, pronostici, verifica);
- venerdì, sabato e domenica alle ~12:40 (quote aggiornate);
- il lunedì anche il backtest completo.

Pubblica in automatico `data/`, `output/` e `docs/`. Dashboard: **https://bitnbit.github.io/Pronostic-python/**

Telegram (facoltativo): in *Settings → Secrets → Actions* aggiungi `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Ogni partita viene inviata una sola volta, 48 ore prima.

## Uso locale (facoltativo)

Windows: doppio clic su `avvia_titan.bat` (installa, aggiorna e apre la dashboard).

```bash
pip install -r requirements.txt
python -m titan run                      # tutto il ciclo
python -m titan predict Juve Napoli      # partita qualsiasi
python -m titan predict Bari Palermo --odds 2.40 3.10 3.20   # con quote -> value bet
python -m titan table I2                 # classifica + Elo Serie B
python -m titan backtest                 # backtest completo
python -m titan update --full            # ricostruisce lo storico da zero
```

Parametri (soglie value bet, Kelly, Elo, giorni di anticipo) in `titan/config.py`.

## Struttura

```
titan/            sources · teams · engine (rating/feature) · models · betting · backtest · tracker · report · notify · pipeline
data/matches.csv  storico unificato (aggiornato dal bot) · data/fixtures.csv prossime partite
output/           latest.json/csv · PRONOSTICI.md · history.csv (verifica live) · backtest.json · predictions/AAAA-MM-GG.json
docs/index.html   dashboard
legacy/           TITAN v5 originale (menu manuale) e file classifica
```
