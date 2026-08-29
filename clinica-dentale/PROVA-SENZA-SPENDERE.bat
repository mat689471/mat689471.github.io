@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo.
echo ==================================================
echo   PROVA COMPLETA - non costa un centesimo
echo   (servizi finti, stesso protocollo di quelli veri)
echo ==================================================
echo.
python tests\acceptance.py --finto
echo.
python tests\scenari.py
echo.
python tests\multicliente.py
echo.
pause
