@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

if exist CHIAVI.bat call CHIAVI.bat

if not "%ANTHROPIC_API_KEY%"=="" goto avvia
echo.
echo  ATTENZIONE: ANTHROPIC_API_KEY non e' impostata.
echo  Il server parte lo stesso, ma ogni paziente finira' in coda operatore
echo  invece di essere qualificato da Claude.
echo.
echo  Per impostarla: copia CHIAVI.bat.esempio in CHIAVI.bat e mettici la chiave.
echo.
pause

:avvia
echo.
echo ==================================================
echo   Clinica dentale - risposta automatica ai lead
echo.
echo   Apri nel browser:  http://127.0.0.1:8000
echo   Per fermare: chiudi questa finestra
echo ==================================================
echo.
python -m uvicorn app.main:app --port 8000
echo.
echo Il server si e' fermato.
pause
