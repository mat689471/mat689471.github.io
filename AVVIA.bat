@echo off
setlocal
title L'Ecosistema
REM %~dp0 e' la cartella di QUESTO file: cosi' funziona ovunque tu lo metta,
REM senza dover sapere in che cartella ti trovi.
cd /d "%~dp0"

REM  NOTA per chi mette mano qui: in questo file niente blocchi  if ... ( ... )
REM  Il percorso puo' contenere parentesi -- Windows le aggiunge da solo quando
REM  scarichi due volte lo stesso file, tipo "cartella (1)" -- e una parentesi
REM  dentro un blocco lo chiude in anticipo. Lo script muore subito e la
REM  finestra sparisce prima che si riesca a leggere l'errore. Con i salti
REM  (goto) il problema non esiste.

echo.
echo  ===========================================
echo     L' E C O S I S T E M A
echo  ===========================================
echo.

REM ---- serve Node.js ----
where node >nul 2>nul
if errorlevel 1 goto manca_node

REM ---- serve Python: proviamo prima 'py', poi 'python' ----
set "PY="
where py >nul 2>nul
if %errorlevel%==0 set "PY=py"
if not defined PY where python >nul 2>nul
if not defined PY if %errorlevel%==0 set "PY=python"
if not defined PY goto manca_python

REM ---- siamo nella cartella giusta? ----
if not exist "mondo\avvia.mjs" goto cartella_sbagliata
if not exist "agente.py" goto cartella_sbagliata

echo  [1 di 2] Apro il mondo...
start "Ecosistema - mondo" cmd /k node "%~dp0mondo\avvia.mjs"

REM il server ha bisogno di un attimo per accendersi prima che l'agente si colleghi
timeout /t 4 /nobreak >nul

echo  [2 di 2] Sveglio gli agenti...
start "Ecosistema - agenti" cmd /k %PY% "%~dp0agente.py" --mondo

echo.
echo  Fatto. Si sono aperte due finestre nere:
echo.
echo     "Ecosistema - mondo"    il mondo, apre il browser da solo
echo     "Ecosistema - agenti"   l'Orchestratore e il suo sciame
echo.
echo  Servono tutte e due accese. Per fermare tutto, chiudile.
echo  Questa finestra la puoi chiudere subito.
echo.
pause
exit /b 0


:manca_node
echo  [manca] Node.js non risulta installato.
echo.
echo  Scaricalo da   https://nodejs.org   -- pulsante verde LTS
echo  Poi richiudi e riapri questa finestra.
echo.
pause
exit /b 1


:manca_python
echo  [manca] Python non risulta installato.
echo.
echo  Scaricalo da   https://python.org
echo  IMPORTANTE: durante l'installazione spunta "Add Python to PATH",
echo  altrimenti Windows non lo trova.
echo.
pause
exit /b 1


:cartella_sbagliata
echo  [errore] Non trovo i file dell'Ecosistema.
echo.
echo  Questo file deve stare nella cartella principale, quella che
echo  contiene sia agente.py sia la cartella mondo.
echo.
echo  Cartella attuale:
echo  %CD%
echo.
pause
exit /b 1
