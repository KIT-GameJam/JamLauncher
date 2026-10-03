@echo off
REM Laedt nur Windows- und Web-Builds einer itch.io-Jam herunter (kein Mac/Linux/Android).
REM Vorher: pip install itch-dl   und API-Key unter https://itch.io/user/settings/api-keys anlegen.
REM --filter-files-platform gilt nur fuer ausfuehrbare Uploads; HTML/Web-Builds werden immer geladen.
REM "native" = Uploads ohne Plattform-Tag (werden oft vergessen), prepare.py sortiert Mac/Linux danach aus.
cd /d "%~dp0"
set /p JAM=Jam-URL (z.B. https://itch.io/jam/datteljam): 
set /p KEY=itch.io API-Key: 
if not exist downloads mkdir downloads
REM Jam-URL merken, damit prepare.py den Jam-Namen fuer den Launcher ermitteln kann
echo %JAM%> downloads\jam.txt
itch-dl "%JAM%" --api-key %KEY% --download-to downloads --filter-files-platform windows native
echo.
echo Fertig. Jetzt: python prepare.py --input downloads --output games
pause
