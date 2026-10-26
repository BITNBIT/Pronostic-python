@echo off
REM TITAN v6 - avvio locale su Windows: installa le dipendenze (solo la prima volta), aggiorna tutto e apre la dashboard
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python -m titan run
start "" "docs\index.html"
pause
