@echo off
setlocal
title Salva i miei dati
cd /d "%~dp0"

REM  Niente blocchi if (...) in questo file: il percorso puo' contenere
REM  parentesi - Windows le mette da solo su "cartella (1)" - e dentro un
REM  blocco chiuderebbero tutto in anticipo, facendo sparire la finestra.

echo.
echo  ===========================================
echo     S A L V A   I   M I E I   D A T I
echo  ===========================================
echo.
echo  Copia in un posto sicuro le cose che NON stanno nel repository,
echo  perche' sono tue e non vanno pubblicate:
echo.
echo     dati    - cassaforte, chiavi, conti, contabilita'
echo     lavori  - quello che gli agenti hanno prodotto
echo     avatar  - i modelli 3D generati
echo.

REM una cartella con la data, cosi' i salvataggi non si sovrascrivono
for /f "tokens=1-3 delims=/-. " %%a in ("%date%") do set OGGI=%%c-%%b-%%a
set ORA=%time:~0,2%%time:~3,2%
set ORA=%ORA: =0%
set DOVE=%USERPROFILE%\Documenti\Ecosistema-salvataggi\%OGGI%_%ORA%

echo  Salvo in:
echo  %DOVE%
echo.

if not exist "%USERPROFILE%\Documenti" set DOVE=%USERPROFILE%\Documents\Ecosistema-salvataggi\%OGGI%_%ORA%
mkdir "%DOVE%" 2>nul

set TROVATO=0
if exist "dati"   call :copia dati
if exist "lavori" call :copia lavori
if exist "avatar" call :copia avatar

if %TROVATO%==0 goto niente

echo.
echo  Fatto. Adesso puoi scaricare un archivio nuovo senza pensieri:
echo  quando lo estrai, ricopia queste cartelle dentro la cartella nuova.
echo.
echo  Apro il salvataggio...
start "" "%DOVE%"
echo.
pause
exit /b 0

:copia
REM xcopy /E sottocartelle comprese, /I crea la destinazione, /H anche i file
REM nascosti - serve per .masterkey, senza il quale la cassaforte non si apre
echo   copio %1 ...
xcopy "%1" "%DOVE%\%1\" /E /I /H /Y /Q >nul
if errorlevel 1 echo      ATTENZIONE: %1 non copiata del tutto
set TROVATO=1
exit /b 0

:niente
echo  Non ho trovato niente da salvare: nessuna delle tre cartelle esiste
echo  ancora. Succede se non hai mai avviato l'ecosistema da qui.
echo.
pause
exit /b 0
