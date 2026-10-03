# Jam-Launcher

Lädt alle Einträge einer itch.io-Jam, bereitet Windows- und Web-Builds auf und startet sie aus einer Galerie.

## Schnellstart ohne Python: `JamLauncher.exe`
[![Build & Release](https://github.com/KIT-GameJam/JamLauncher/actions/workflows/release.yml/badge.svg)](https://github.com/KIT-GameJam/JamLauncher/actions/workflows/release.yml)

**Download (neueste Version):**
[JamLauncher-x64.exe](https://github.com/KIT-GameJam/JamLauncher/releases/latest/download/JamLauncher-x64.exe) für normale Windows-PCs ·
[JamLauncher-arm64.exe](https://github.com/KIT-GameJam/JamLauncher/releases/latest/download/JamLauncher-arm64.exe) für Windows on ARM ·
[alle Releases](https://github.com/KIT-GameJam/JamLauncher/releases)

Die .exe (~16 MB, inkl. itch-dl) in einen leeren Ordner kopieren und doppelklicken. Ein Menü führt durch
Herunterladen → Aufbereiten → Starten; `downloads\` und `games\` entstehen neben der .exe.
Nötig sind nur noch ein kostenloser itch.io API-Key (siehe unten) und Chrome/Edge für den Kiosk-Modus.

### itch.io API-Key bekommen
1. Bei itch.io einloggen (ein kostenloser Account reicht) und https://itch.io/user/settings/api-keys öffnen.
2. Auf **Generate new API key** klicken, optional einen Namen wie „JamLauncher“ vergeben.
3. Den angezeigten Schlüssel kopieren und beim Herunterladen einfügen (Menüpunkt 1 fragt danach).

Der Key gilt nur für deinen Account und lässt sich auf derselben Seite jederzeit wieder löschen.
Nicht weitergeben und nicht ins Repo committen. Für kostenpflichtige oder passwortgeschützte Einreichungen
muss der Account Zugriff haben; öffentliche Jam-Einreichungen gehen immer.

Selbst bauen: `build.bat` doppelklicken (braucht Python 3.10+), Ergebnis liegt in `dist\JamLauncher.exe`.

Menüpunkt 5 löscht `downloads\` und `games\` wieder, es bleibt nur die .exe übrig.

Ohne Menü, z.B. für Skripte: `JamLauncher.exe download`, `JamLauncher.exe prepare [--prefer web]`,
`JamLauncher.exe run [--no-kiosk]`, `JamLauncher.exe clean [--yes]`.

SmartScreen warnt beim ersten Start vor der unsignierten .exe ("Weitere Informationen" → "Trotzdem ausführen").

### Release veröffentlichen
Ein gepushter Tag `v*` baut die .exe für x64 und ARM64 per GitHub Actions und hängt beide an ein neues Release:
```
git tag v1.0.0
git push origin v1.0.0
```
Pushes auf `main` und Pull Requests bauen die .exe ebenfalls (als Workflow-Artefakt, ohne Release).

## Manuell mit Python
### Voraussetzungen (Windows)
- Python 3.10+ (`python --version`)
- `pip install itch-dl`
- itch.io API-Key: https://itch.io/user/settings/api-keys
- Chrome oder Edge (für den Kiosk-Modus)

### Ablauf
1. **Herunterladen** – `download.bat` doppelklicken (fragt Jam-URL, API-Key und Anzahl paralleler Downloads ab), oder direkt:
   `itch-dl https://itch.io/jam/<slug> --api-key <KEY> --download-to downloads --parallel 4`
   Falls `--download-to` bei deiner Version anders heißt: `itch-dl --help`.
2. **Aufbereiten** – `prepare.bat` doppelklicken, oder direkt `python prepare.py --input downloads --output games`
   Entpackt Zips, findet .exe / index.html, entfernt Mark of the Web, schreibt `games/games.json`.
   Der Jam-Name im Launcher kommt aus `downloads/jam.txt` (legt `download.bat` an) bzw. von der Jam-Seite;
   manuell überschreiben mit `--jam-title "Mein Jam"`. Bei direktem `itch-dl`-Aufruf die Jam-URL selbst in `downloads/jam.txt` schreiben.
   Mit `--prefer web` wird bei Spielen mit beiden Builds die Web-Version als Standard gesetzt.
3. **Starten** – `run.bat` (Kiosk-Vollbild) oder `python launcher.py --games games`.

## Bedienung
Pfeiltasten wählen ein Spiel, Enter startet es, Esc beendet ein laufendes .exe oder verlässt ein Web-Spiel.
`/` springt in die Suche. Maus funktioniert natürlich auch.
Der Jam-Titel und jede Karte haben einen dezenten „itch.io ↗“-Link zur Jam- bzw. Spielseite (öffnet ein neues Fenster).
Das ✕ oben rechts beendet den Launcher: laufende Spiele werden geschlossen, der Server stoppt und im
Kiosk-Modus wird auch der Browser geschlossen.

## Wenn etwas nicht klappt
- **Falsche .exe gewählt** – in `games/games.json` den Pfad bei `"exe"` korrigieren, Launcher neu starten.
- **Web-Spiel lädt nicht / bleibt schwarz** – Browser-Konsole (F12) öffnen. Godot-4-Exporte mit Threads
  brauchen die COOP/COEP-Header, die der Launcher setzt; funktioniert nur über `http://localhost`, nicht per Datei öffnen.
- **Spiel steckt in .rar/.7z** – manuell nach `games/<slug>/build/windows/` entpacken und `"exe"` in games.json eintragen.
- **SmartScreen trotzdem** – `prepare.py` nochmal laufen lassen oder in PowerShell:
  `Get-ChildItem games -Recurse | Unblock-File`
- **Defender löscht eine .exe** – vorher Ausnahme für den `games`-Ordner anlegen.
- **Spiele vorher einmal durchtesten!** Jam-Builds haben gern mal fehlende .pck-Dateien oder falsche Pfade.
