@echo off
REM Bereitet die itch-dl-Downloads aus "downloads" fuer den Launcher auf (Ziel: "games").
REM Entpackt Zips, findet .exe / index.html, entfernt Mark of the Web, schreibt games\games.json.
REM Der Jam-Name kommt aus downloads\jam.txt (legt download.bat an).
cd /d "%~dp0"
set PREFER=windows
set /p PREFER=Bevorzugte Version bei Spielen mit Windows- und Web-Build (windows/web) [windows]: 
python prepare.py --input downloads --output games --prefer %PREFER%
echo.
echo Fertig. Jetzt: run.bat
pause
