@echo off
setlocal
chcp 65001 >nul
title TITAN v6 - pronostici Serie A / Serie B
cd /d "%~dp0"
rem ---------------------------------------------------------------------------
rem  Versione PORTATILE: usa solo il Python incluso in questa cartella.
rem  Non installa nulla, non modifica il PC; file temporanei e cache restano qui.
rem  Per rimuovere TITAN basta cancellare la cartella.
rem ---------------------------------------------------------------------------
set "PY=%~dp0python\python.exe"
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "PYTHONPYCACHEPREFIX=%~dp0cache\pycache"
set "TEMP=%~dp0cache\tmp"
set "TMP=%~dp0cache\tmp"
set "DASH=%~dp0app\docs\index.html"
if not exist "%~dp0cache\tmp" mkdir "%~dp0cache\tmp"
if not exist "%PY%" (
  echo Python portatile non trovato: estrai TUTTO lo zip e avvia TITAN.bat dalla cartella estratta.
  pause
  exit /b 1
)

:menu
cls
echo.
echo   ==========================================================
echo    TITAN v6  -  pronostici Serie A / Serie B  (portatile)
echo   ==========================================================
echo.
echo    1  Aggiorna dati e calcola i pronostici (apre la dashboard)
echo    2  Apri l'ultima dashboard
echo    3  Pronostico di una partita
echo    4  Classifica Serie A
echo    5  Classifica Serie B
echo    6  Backtest - verifica accuratezza (alcuni minuti)
echo    0  Esci
echo.
echo    Analisi statistica, non consiglio di gioco. Vietato ai minori di 18 anni.
echo.
set "c="
set /p "c=   Scelta: "
if "%c%"=="1" goto run
if "%c%"=="2" goto dash
if "%c%"=="3" goto single
if "%c%"=="4" goto tabA
if "%c%"=="5" goto tabB
if "%c%"=="6" goto backtest
if "%c%"=="0" exit /b 0
goto menu

:run
echo.
echo   Il primo avvio scarica lo storico partite: 1-3 minuti.
"%PY%" -m titan run --no-notify
if exist "%DASH%" start "" "%DASH%"
pause
goto menu

:dash
if exist "%DASH%" (start "" "%DASH%") else (echo   Nessuna dashboard: esegui prima l'opzione 1. & pause)
goto menu

:single
echo.
set "h="
set "a="
set /p "h=   Squadra di casa: "
set /p "a=   Squadra in trasferta: "
"%PY%" -m titan predict "%h%" "%a%"
pause
goto menu

:tabA
"%PY%" -m titan table I1
pause
goto menu

:tabB
"%PY%" -m titan table I2
pause
goto menu

:backtest
"%PY%" -m titan backtest
pause
goto menu
