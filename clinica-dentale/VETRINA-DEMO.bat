@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo.
echo ==================================================
echo   VETRINA - il cruscotto acceso, senza spendere
echo   (Claude e HubSpot finti, stesso protocollo)
echo.
echo   Si apre da solo nel browser fra qualche secondo.
echo   Per fermare: chiudi questa finestra.
echo ==================================================
echo.
python demo.py
pause
