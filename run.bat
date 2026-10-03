@echo off
REM Startet den Launcher im Kiosk-Modus (Vollbild, ohne Browserleiste).
REM Beenden: Alt+F4 im Browser, dann Strg+C im Terminal.
cd /d "%~dp0"
start "" python launcher.py --games games --no-browser
timeout /t 2 >nul
set CHROME="%ProgramFiles%\Google\Chrome\Application\chrome.exe"
set EDGE="%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist %CHROME% (
  start "" %CHROME% --kiosk --new-window --user-data-dir="%TEMP%\jam-kiosk" http://localhost:8000/
) else (
  start "" %EDGE% --kiosk --new-window --user-data-dir="%TEMP%\jam-kiosk" http://localhost:8000/
)
