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

REM ---- il Python scelto ha la libreria che serve? ----
REM Su Windows convivono spesso due Python: 'py' e 'python' possono essere due
REM installazioni diverse, e 'anthropic' puo' stare solo su una delle due.
REM Prima di arrendersi si prova l'altra, poi la si installa.
%PY% -c "import anthropic" >nul 2>nul
if %errorlevel%==0 goto python_pronto

set "ALTRO="
if /i "%PY%"=="py" set "ALTRO=python"
if /i "%PY%"=="python" set "ALTRO=py"
if not defined ALTRO goto installa_libreria
where %ALTRO% >nul 2>nul
if errorlevel 1 goto installa_libreria
%ALTRO% -c "import anthropic" >nul 2>nul
if errorlevel 1 goto installa_libreria
echo  Uso %ALTRO%: e' quello che ha la libreria 'anthropic'.
set "PY=%ALTRO%"
goto python_pronto

:installa_libreria
echo  Manca la libreria 'anthropic', senza la quale gli agenti non partono.
echo  La installo adesso ^(serve internet, ci vuole qualche secondo^)...
echo.
%PY% -m pip install anthropic
echo.
%PY% -c "import anthropic" >nul 2>nul
if errorlevel 1 goto libreria_ko
echo  Installata.
echo.

:python_pronto

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


:libreria_ko
echo.
echo  [errore] Non sono riuscito a installare 'anthropic'.
echo.
echo  Provala a mano, con questo comando:
echo     %PY% -m pip install anthropic
echo.
echo  Se dice che pip non esiste, reinstalla Python da https://python.org
echo  spuntando "Add Python to PATH".
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
