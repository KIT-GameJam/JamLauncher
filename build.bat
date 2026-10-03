@echo off
REM Baut aus jamlauncher.py + launcher.py + prepare.py + itch-dl eine einzelne JamLauncher.exe (dist\JamLauncher.exe).
REM Voraussetzung: Python 3.10+. Es wird eine eigene virtuelle Umgebung (.venv-build) angelegt,
REM damit nur itch-dl und seine Abhaengigkeiten in die .exe wandern und nicht alles aus der globalen Installation.
cd /d "%~dp0"
if not exist .venv-build\Scripts\python.exe (
  python -m venv .venv-build || goto :fail
)
set PY=.venv-build\Scripts\python.exe
%PY% -m pip install --upgrade --quiet pip pyinstaller itch-dl || goto :fail
%PY% -m PyInstaller --noconfirm --clean --onefile --console --name JamLauncher ^
  --collect-all itch_dl ^
  --hidden-import itch_dl.cli ^
  jamlauncher.py || goto :fail
echo.
echo Fertig: dist\JamLauncher.exe
echo Die .exe in einen leeren Ordner kopieren und doppelklicken; downloads\ und games\ entstehen daneben.
pause
exit /b 0
:fail
echo.
echo Build fehlgeschlagen.
pause
exit /b 1
