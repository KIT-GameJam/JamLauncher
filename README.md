# Jam-Launcher

Lädt alle Einträge einer itch.io-Jam, bereitet Windows- und Web-Builds auf und startet sie aus einer Galerie.

## Voraussetzungen (Windows)
- Python 3.10+ (`python --version`)
- `pip install itch-dl`
- itch.io API-Key: https://itch.io/user/settings/api-keys
- Chrome oder Edge (für den Kiosk-Modus)

## Ablauf
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

## Wenn etwas nicht klappt
- **Falsche .exe gewählt** – in `games/games.json` den Pfad bei `"exe"` korrigieren, Launcher neu starten.
- **Web-Spiel lädt nicht / bleibt schwarz** – Browser-Konsole (F12) öffnen. Godot-4-Exporte mit Threads
  brauchen die COOP/COEP-Header, die der Launcher setzt; funktioniert nur über `http://localhost`, nicht per Datei öffnen.
- **Spiel steckt in .rar/.7z** – manuell nach `games/<slug>/build/windows/` entpacken und `"exe"` in games.json eintragen.
- **SmartScreen trotzdem** – `prepare.py` nochmal laufen lassen oder in PowerShell:
  `Get-ChildItem games -Recurse | Unblock-File`
- **Defender löscht eine .exe** – vorher Ausnahme für den `games`-Ordner anlegen.
- **Spiele vorher einmal durchtesten!** Jam-Builds haben gern mal fehlende .pck-Dateien oder falsche Pfade.
