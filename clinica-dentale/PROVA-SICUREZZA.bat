@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo.
echo ==================================================
echo   PROVA SICUREZZA - i dati dei pazienti sono chiusi?
echo   (servizi finti: non costa niente)
echo ==================================================
echo.
python tests\sicurezza.py
echo.
pause
