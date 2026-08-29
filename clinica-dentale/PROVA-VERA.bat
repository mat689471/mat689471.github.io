@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

if not exist CHIAVI.bat goto manca
call CHIAVI.bat

if "%ANTHROPIC_API_KEY%"=="" goto vuota
if "%ANTHROPIC_API_KEY%"=="sk-ant-metti-qui-la-tua-chiave" goto vuota

echo.
echo ==================================================
echo   PROVA CONTRO I SERVIZI VERI
echo   Claude + HubSpot. Costa due chiamate al modello,
echo   cioe' pochi centesimi.
echo ==================================================
echo.
python tests\acceptance.py
echo.
pause
goto fine

:manca
echo.
echo  Non trovo CHIAVI.bat.
echo  Copia CHIAVI.bat.esempio in CHIAVI.bat e mettici le tue chiavi.
echo.
pause
goto fine

:vuota
echo.
echo  In CHIAVI.bat la chiave Anthropic e' ancora quella di esempio.
echo  Aprilo col Blocco note e mettici la tua chiave vera.
echo.
echo  Ricorda: niente virgolette, niente spazi attorno all'uguale.
echo.
pause

:fine
