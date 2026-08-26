@echo off
setlocal
title L'Ecosistema
REM %~dp0 e' la cartella di QUESTO file: cosi' funziona ovunque tu lo metta,
REM senza dover sapere in che cartella ti trovi.
cd /d "%~dp0"

echo.
echo  ===========================================
echo     L' E C O S I S T E M A
echo  ===========================================
echo.

REM ---- serve Node.js ----
where node >nul 2>nul
if errorlevel 1 (
  echo  [manca] Node.js non risulta installato.
  echo.
  echo  Scaricalo qui:  https://nodejs.org   ^(scegli il pulsante LTS^)
  echo  Poi richiudi e riapri questa finestra.
  echo.
  pause
  exit /b 1
)

REM ---- serve Python: proviamo prima 'py', poi 'python' ----
REM (niente parentesi qui: dentro un blocco cmd valuterebbe %errorlevel%
REM  prima di eseguire il comando, e la ricerca risulterebbe sempre fallita)
set "PY="
where py >nul 2>nul
if %errorlevel%==0 set "PY=py"
if not defined PY where python >nul 2>nul
if not defined PY if %errorlevel%==0 set "PY=python"
if not defined PY (
  echo  [manca] Python non risulta installato.
  echo.
  echo  Scaricalo qui:  https://python.org
  echo  IMPORTANTE: durante l'installazione spunta "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

REM ---- siamo nella cartella giusta? ----
if not exist "mondo\avvia.mjs" (
  echo  [errore] Non trovo mondo\avvia.mjs
  echo.
  echo  Questo file deve stare nella cartella principale, quella che
  echo  contiene sia agente.py sia la cartella mondo.
  echo  Cartella attuale: %CD%
  echo.
  pause
  exit /b 1
)

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
