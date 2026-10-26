# Pronostic-python · TITAN v6

> ⚠️ **AVVISO: usa la [versione portatile](#uso-sul-pc-versione-portatile-consigliata).** Non installa nulla sul PC: estrai lo zip, doppio clic su `TITAN.bat`, e per rimuoverlo basta cancellare la cartella. Non serve più il vecchio `pip install` della v5.

Sistema **automatico** di pronostici per Serie A e Serie B. Non va toccato niente a mano: ogni giorno GitHub Actions scarica risultati, quote e calendario, aggiorna i rating, riallena il modello, genera i pronostici, verifica quelli passati e pubblica la dashboard.

☕ Offrimi un caffè: https://buymeacoffee.com/bitnbit · Video (v5): https://youtu.be/kU5DPSxOFEk · Sito: https://bitnbit.com

> **IL GIOCO È VIETATO AI MINORI DI 18 ANNI.** Progetto di analisi statistica a scopo educativo: non è un servizio di scommesse, non contiene link a bookmaker, non è un consiglio di gioco e non promette guadagni. Il gioco può causare dipendenza. L'autore non si assume alcuna responsabilità.

## Cosa fa (giro automatico giornaliero)

| Passo | Dettaglio |
|---|---|
| Dati | football-data.co.uk (risultati, tiri, quote, calendario) + ESPN (risultati recenti e calendario Serie A/B) + openfootball + vecchi file v5. Nomi squadra normalizzati, duplicati rimossi. Lo storico resta nella cache privata delle Actions: nel repo vengono pubblicati solo codice e pronostici |
| Rating | Elo con margine gol e regressione a inizio stagione, attacco/difesa Poisson online, forma 5/10, rendimento casa/trasferta, tiri e tiri in porta, riposo, classifica calcolata dai risultati |
| Modelli | LightGBM + regressione logistica (1X2), Poisson-boosting + Dixon-Coles (gol, risultato esatto, O/U, GG, multigol), probabilità del mercato. Blend con pesi stimati out-of-sample sulle ultime 3 stagioni |
| Doppio modello | con quote (partite già quotate) e "solo campo" (quote non ancora disponibili) |
| Output | 1X2, doppia chance, O/U 1.5/2.5/3.5, GG/NG, multigol, top-5 risultati esatti, xG, stelle di confidenza, **pronostico più probabile**, indice di valore (quota superiore alla probabilità stimata) |
| Verifica | ogni pronostico viene salvato prima della partita e controllato a risultato acquisito (`output/history.csv`): accuratezza reale |
| Report | `docs/index.html` (dashboard, GitHub Pages), `output/PRONOSTICI.md`, `output/latest.json/csv`, Telegram opzionale |

## Accuratezza misurata (backtest walk-forward, 8 stagioni 2018/19 → 2025/26, 6.042 partite mai viste in training)

| Pronostico | Partite coperte | Azzeccati |
|---|---|---|
| **Più probabile** (miglior mercato tra 1X2, doppia chance, Over 1.5, Under 3.5, GG/NG, multigol) | 100% | **81%** |
| Più probabile con probabilità ≥ 80% | 53% | **85%** |
| Più probabile con probabilità ≥ 85% | 20% | **89%** |
| Segno 1 con probabilità ≥ 70% | 7% | 76% |
| Segno 2 con probabilità ≥ 70% | 1,4% | 86% |
| Segno 1X2 secco su tutte le partite | 100% | 50,0% (bookmaker: 49,8%) |

- Le probabilità sono **calibrate**: quando il modello dice 80%, la frequenza reale è circa 80%.
- Sul segno 1X2 secco il ~50% è il limite pratico: nemmeno le quote dei bookmaker fanno meglio. In log-loss TITAN v6 (1,0005) batte il mercato (1,0030).
- Provato anche l'addestramento con altri campionati europei (Premier, Liga, Bundesliga, Ligue 1 e serie B): peggiora le previsioni sull'Italia, quindi non è stato adottato.
- La v5 dichiarava accuratezze più alte perché calcolava le statistiche sull'intero storico, **compresa la partita da prevedere** (leakage). La v6 usa solo informazioni disponibili prima del calcio d'inizio.

## Automazione (zero lavoro manuale)

Il workflow `.github/workflows/titan.yml` gira:
- ogni giorno alle ~07:10 (risultati, rating, pronostici, verifica);
- venerdì, sabato e domenica alle ~12:40 (quote aggiornate);
- il lunedì anche il backtest completo.

Pubblica in automatico solo `output/` e `docs/`. Dashboard: **https://bitnbit.github.io/Pronostic-python/**

Telegram (facoltativo): in *Settings → Secrets → Actions* aggiungi `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Ogni partita viene inviata una sola volta, 48 ore prima.

## Uso sul PC: versione PORTATILE (consigliata)

> ⚠️ **Non installare niente con `pip` sul tuo PC.** Usa la versione portatile: Python e librerie sono già dentro la cartella.

1. Scarica **[TITAN-portatile-win64.zip](https://github.com/BITNBIT/Pronostic-python/releases/download/portatile/TITAN-portatile-win64.zip)** (pagina [Releases](https://github.com/BITNBIT/Pronostic-python/releases/tag/portatile))
2. Estrai **tutto** lo zip in una cartella (va bene anche una chiavetta USB)
3. Doppio clic su **`TITAN.bat`** → opzione **1** (aggiorna i dati, calcola i pronostici, apre la dashboard)

| | |
|---|---|
| Installazioni | nessuna: niente Python di sistema, niente `pip`, niente modifiche a registro o PATH |
| Dove finiscono i file | solo nella cartella: dati e modello in `app\`, file temporanei e cache in `cache\` |
| Disinstallazione | cancella la cartella |
| Requisiti | Windows 10/11 a 64 bit e connessione internet. Il primo avvio scarica lo storico (1-3 minuti) |
| Menu | pronostici + dashboard · partita singola · classifiche Serie A/B · backtest |

Lo zip viene ricostruito e **testato in automatico** da GitHub Actions a ogni modifica del codice. Se Windows mostra "PC protetto" (SmartScreen): *Ulteriori informazioni → Esegui comunque*. `TITAN.bat` è un file di testo e puoi leggerlo prima di avviarlo.

**Senza scaricare nulla**: la dashboard online è sempre aggiornata.

### Per sviluppatori (Linux/macOS o modifiche al codice)

Usa un ambiente virtuale dentro la cartella del progetto, così il Python di sistema resta pulito:

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m titan run                      # tutto il ciclo
python -m titan predict Juve Napoli      # partita qualsiasi
python -m titan table I2                 # classifica + Elo Serie B
python -m titan backtest                 # backtest completo
```

Parametri (Elo, Poisson, soglie, giorni di anticipo) in `titan/config.py`.

## Struttura

```
titan/            sources · teams · engine (rating/feature) · models · markets · betting · backtest · tracker · report · notify · pipeline
data/             storico generato in automatico (cache Actions, non pubblicato) · legacy/ file v5
output/           latest.json/csv · PRONOSTICI.md · history.csv (verifica live) · backtest.json · predictions/AAAA-MM-GG.json
docs/index.html   dashboard
portable/         TITAN.bat, LEGGIMI.txt e note della release portatile
legacy/           TITAN v5 originale (menu manuale) e file classifica
```
