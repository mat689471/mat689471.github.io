@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo.
echo ==================================================
echo   VETRINA PUBBLICA - come girera' online
echo.
echo   Claude e HubSpot simulati: nessuna chiave,
echo   nessun costo. E' quello che vedra' il cliente.
echo.
echo   Pagina di vendita : http://127.0.0.1:8000/vetrina
echo   Cruscotto         : http://127.0.0.1:8000
echo ==================================================
echo.
set DEMO_PUBBLICA=1
start "" http://127.0.0.1:8000/vetrina
python -m uvicorn app.main:app --port 8000
pause
