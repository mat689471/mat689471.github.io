@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo.
echo ==================================================
echo   PROVA MULTI-CLIENTE - due studi, nessuno sconfina
echo   (servizi finti: non costa niente)
echo ==================================================
echo.
python tests\multicliente.py
echo.
pause
