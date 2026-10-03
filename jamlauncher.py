#!/usr/bin/env python3
"""
jamlauncher.py – gemeinsamer Einstiegspunkt für Download, Aufbereitung und Launcher.

Wird mit build.bat zu einer einzelnen JamLauncher.exe gepackt (inkl. itch-dl),
damit andere Nutzer kein Python installieren müssen.

  JamLauncher.exe                 -> interaktives Menü
  JamLauncher.exe download        -> Jam-Spiele herunterladen (fragt URL/API-Key ab)
  JamLauncher.exe prepare         -> Downloads aufbereiten
  JamLauncher.exe run             -> Launcher im Kiosk-Modus starten
  JamLauncher.exe run --no-kiosk  -> Launcher nur im normalen Browser öffnen
  JamLauncher.exe clean           -> downloads/ und games/ löschen (nur die .exe bleibt)

Alle Pfade (downloads/, games/) liegen neben der .exe bzw. neben diesem Skript.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Umlaute auch bei umgeleiteter Ausgabe korrekt ausgeben
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import launcher
import prepare


def base_dir() -> Path:
    """Ordner, in dem die .exe (gefroren) bzw. dieses Skript liegt."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE = base_dir()
DOWNLOADS = BASE / "downloads"
GAMES = BASE / "games"


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        val = ""
    return val or default


def pause():
    try:
        input("\nWeiter mit Enter ...")
    except EOFError:
        pass


# ---------------------------------------------------------------- Download

def cmd_download():
    print("Lädt nur Windows- und Web-Builds einer itch.io-Jam herunter (kein Mac/Linux/Android).")
    print("API-Key anlegen: https://itch.io/user/settings/api-keys\n")
    jam = ask("Jam-URL (z.B. https://itch.io/jam/datteljam)")
    if not jam:
        print("Keine URL angegeben.")
        return 1
    key = ask("itch.io API-Key")
    if not key:
        print("Kein API-Key angegeben.")
        return 1
    par = ask("Parallele Downloads", "4")

    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    # Jam-URL merken, damit prepare den Jam-Namen für den Launcher ermitteln kann
    (DOWNLOADS / "jam.txt").write_text(jam + "\n", encoding="utf-8")

    from itch_dl.cli import run as itch_dl_run
    sys.argv = [
        "itch-dl", jam, "--api-key", key, "--download-to", str(DOWNLOADS),
        "--filter-files-platform", "windows", "native", "--parallel", par,
    ]
    try:
        rc = itch_dl_run() or 0
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
        if e.code and not isinstance(e.code, int):
            print(e.code)
    if rc == 0:
        print("\nFertig. Nächster Schritt: Aufbereiten (Menüpunkt 2).")
    else:
        print("\nDownload fehlgeschlagen oder abgebrochen.")
    return rc


# ---------------------------------------------------------------- Prepare

def cmd_prepare(prefer: str | None = None):
    if not DOWNLOADS.is_dir():
        print(f"Ordner {DOWNLOADS} fehlt – erst herunterladen (Menüpunkt 1).")
        return 1
    if prefer is None:
        prefer = ask("Bevorzugte Version bei Spielen mit Windows- und Web-Build (windows/web)", "windows")
    if prefer not in ("windows", "web"):
        prefer = "windows"
    sys.argv = ["prepare", "--input", str(DOWNLOADS), "--output", str(GAMES), "--prefer", prefer]
    try:
        prepare.main()
    except SystemExit as e:
        if e.code:
            print(e.code)
            return 1
    print("Nächster Schritt: Starten (Menüpunkt 3).")
    return 0


# ---------------------------------------------------------------- Run

def find_browser() -> Path | None:
    candidates = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        root = os.environ.get(env)
        if not root:
            continue
        candidates += [
            Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def cmd_run(kiosk: bool = True, port: int = 8000):
    if not (GAMES / "games.json").is_file():
        print(f"{GAMES / 'games.json'} fehlt – erst aufbereiten (Menüpunkt 2).")
        return 1

    url = f"http://localhost:{port}/"
    browser = find_browser() if kiosk else None
    if kiosk and not browser:
        print("Chrome/Edge nicht gefunden – öffne stattdessen den Standardbrowser.")

    if browser:
        kiosk_proc: list[subprocess.Popen] = []

        def open_kiosk():
            time.sleep(1.5)
            kiosk_proc.append(subprocess.Popen([
                str(browser), "--kiosk", "--new-window",
                f"--user-data-dir={Path(os.environ.get('TEMP', '.')) / 'jam-kiosk'}", url,
            ]))

        def close_kiosk():
            # Browser samt Kindprozessen beenden, wenn in der Oberfläche auf das X geklickt wird
            time.sleep(0.5)
            for p in kiosk_proc:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        launcher.QUIT_HOOKS.append(close_kiosk)
        import threading
        threading.Thread(target=open_kiosk, daemon=True).start()
        print("Launcher läuft im Kiosk-Modus. Beenden über das X oben rechts (oder Strg+C hier).")

    sys.argv = ["launcher", "--games", str(GAMES), "--port", str(port)]
    if browser:
        sys.argv.append("--no-browser")
    try:
        launcher.main()
    except SystemExit as e:
        if e.code:
            print(e.code)
            return 1
    return 0


# ---------------------------------------------------------------- Clean

def cmd_clean(force: bool = False):
    kiosk_profile = Path(os.environ.get("TEMP", ".")) / "jam-kiosk"
    targets = [d for d in (DOWNLOADS, GAMES, kiosk_profile) if d.exists()]
    if not targets:
        print("Nichts zu entfernen – downloads und games existieren nicht.")
        return 0
    print("Folgende Ordner werden unwiderruflich gelöscht:")
    for d in targets:
        print(f"  {d}")
    if not force and ask("Wirklich löschen? (ja/nein)", "nein").lower() not in ("ja", "j", "y", "yes"):
        print("Abgebrochen.")
        return 1
    rc = 0
    for d in targets:
        try:
            shutil.rmtree(d, onexc=_rm_readonly) if sys.version_info >= (3, 12) else shutil.rmtree(d, onerror=_rm_readonly)
            print(f"  gelöscht: {d}")
        except Exception as ex:
            print(f"  !! konnte {d} nicht löschen: {ex}")
            rc = 1
    print("Fertig. Es bleibt nur noch die .exe übrig.")
    return rc


def _rm_readonly(func, path, _exc):
    """Schreibgeschützte Dateien (z.B. aus Zips) vor dem Löschen freigeben."""
    import stat
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


# ---------------------------------------------------------------- Menü

def menu():
    while True:
        print("\n=== Jam-Launcher ===")
        print(f"Arbeitsordner: {BASE}")
        print("  1) Jam-Spiele herunterladen (itch.io)")
        print("  2) Downloads aufbereiten")
        print("  3) Launcher starten (Kiosk-Vollbild)")
        print("  4) Launcher starten (normales Browserfenster)")
        print("  5) Alles entfernen (downloads, games – nur die .exe bleibt)")
        print("  0) Beenden")
        choice = ask("Auswahl")
        if choice == "1":
            cmd_download(); pause()
        elif choice == "2":
            cmd_prepare(); pause()
        elif choice == "3":
            cmd_run(kiosk=True)
        elif choice == "4":
            cmd_run(kiosk=False)
        elif choice == "5":
            cmd_clean(); pause()
        elif choice in ("0", "q", ""):
            return 0
        else:
            print("Ungültige Auswahl.")


def main():
    args = sys.argv[1:]
    if not args:
        return menu()
    cmd, rest = args[0], args[1:]
    if cmd == "download":
        return cmd_download()
    if cmd == "prepare":
        prefer = None
        if "--prefer" in rest:
            prefer = (rest[rest.index("--prefer") + 1:] or ["windows"])[0]
        return cmd_prepare(prefer)
    if cmd == "run":
        return cmd_run(kiosk="--no-kiosk" not in rest)
    if cmd == "clean":
        return cmd_clean(force="--yes" in rest or "-y" in rest)
    print(__doc__)
    return 0 if cmd in ("help", "--help", "-h") else 2


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(130)
