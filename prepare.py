#!/usr/bin/env python3
"""
prepare.py – bereitet itch-dl-Downloads für den Launcher auf.

Ablauf:
  1. itch-dl hat alle Jam-Einträge nach <input> geladen (je Spiel ein Ordner mit metadata.json).
  2. Dieses Skript entpackt die Zips nach <output>/<slug>/build/, sucht die Startdatei
     (Windows-.exe oder Web-index.html), entfernt "Mark of the Web" (SmartScreen-Warnung)
     und schreibt <output>/games.json für launcher.py.

Aufruf:
  python prepare.py --input downloads --output games
  python prepare.py --input downloads --output games --prefer web
"""

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

# .exe-Dateien, die nie das eigentliche Spiel sind
EXE_BLACKLIST = re.compile(
    r"(unitycrashhandler|unityplayer|crashhandler|crashreport|unins|setup|install|"
    r"vcredist|vc_redist|dxsetup|dxwebsetup|redist|python|7z|updater|launcher_helper)",
    re.IGNORECASE,
)
# Ordner, in denen keine Haupt-.exe liegt
DIR_BLACKLIST = re.compile(r"(_data|monobleedingedge|redist|__macosx)", re.IGNORECASE)

ARCHIVE_EXT = {".zip"}
UNSUPPORTED_ARCHIVE_EXT = {".rar", ".7z", ".tar", ".gz"}


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_-]+", "-", text)
    return text or "spiel"


def jam_title_from_url(jam_url: str) -> str:
    """Ermittelt den Jam-Namen aus der itch.io-Jam-Seite; Fallback ist der Slug aus der URL."""
    jam_url = jam_url.strip()
    slug = jam_url.rstrip("/").split("/")[-1]
    fallback = re.sub(r"[-_]+", " ", slug).strip().title() or "Game Jam"
    try:
        req = urllib.request.Request(jam_url, headers={"User-Agent": "JamLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="replace")
        m = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        if not m:
            m = re.search(r"<title>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        if m:
            title = re.sub(r"\s*-\s*itch\.io\s*$", "", m.group(1).strip())
            title = title.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
            if title:
                return title
    except Exception as e:
        print(f"  ! Jam-Seite nicht abrufbar ({e}), nutze '{fallback}'")
    return fallback


def detect_jam_title(in_root: Path, override: str | None) -> str:
    """Jam-Titel: explizit per --jam-title, sonst aus <input>/jam.txt (von download.bat), sonst generisch."""
    if override:
        return override
    jam_file = in_root / "jam.txt"
    if jam_file.is_file():
        url = jam_file.read_text(encoding="utf-8", errors="replace").strip()
        if url:
            return jam_title_from_url(url)
    print("  ! Kein jam.txt im Eingabeordner – Titel per --jam-title setzen")
    return "Game Jam"


def load_metadata(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # kaputte/fehlende Metadaten sind kein Grund abzubrechen
        print(f"  ! metadata.json unlesbar ({e}), nutze Ordnernamen")
        return {}


def authors_from_metadata(meta: dict, fallback: str) -> str:
    authors = meta.get("authors")
    if isinstance(authors, list) and authors:
        names = [a.get("name") if isinstance(a, dict) else str(a) for a in authors]
        return ", ".join(n for n in names if n)
    for key in ("author", "author_name", "user"):
        val = meta.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict) and val.get("name"):
            return val["name"]
    return fallback


def classify_zip(zip_path: Path) -> str:
    """'web', 'windows' oder 'other' anhand des Zip-Inhalts."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = [n.lower() for n in z.namelist()]
    except zipfile.BadZipFile:
        return "other"
    if any(n.endswith("index.html") for n in names):
        return "web"
    if any(n.endswith(".exe") for n in names):
        return "windows"
    if any(n.endswith(".html") for n in names) and any(n.endswith((".wasm", ".js")) for n in names):
        return "web"
    return "other"


def classify_by_name(path: Path) -> str:
    n = path.name.lower()
    if any(k in n for k in ("html", "web", "browser", "wasm")):
        return "web"
    if any(k in n for k in ("win", "windows", "pc", "exe")):
        return "windows"
    return "unknown"


def extract(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)


def strip_single_root(folder: Path) -> Path:
    """Wenn das Zip nur einen Unterordner enthält, diesen als Wurzel nehmen."""
    entries = [p for p in folder.iterdir() if p.name != "__MACOSX"]
    while len(entries) == 1 and entries[0].is_dir():
        folder = entries[0]
        entries = [p for p in folder.iterdir() if p.name != "__MACOSX"]
    return folder


def find_exe(root: Path, title: str) -> Path | None:
    candidates = []
    for p in root.rglob("*.exe"):
        rel_dirs = [part for part in p.relative_to(root).parts[:-1]]
        if EXE_BLACKLIST.search(p.stem):
            continue
        if any(DIR_BLACKLIST.search(d) for d in rel_dirs):
            continue
        candidates.append(p)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Bevorzugt: flach liegend, Name ähnlich zum Titel, sonst größte Datei
    def score(p: Path):
        depth = len(p.relative_to(root).parts)
        sim = difflib.SequenceMatcher(None, slugify(p.stem), slugify(title)).ratio()
        return (-depth, sim, p.stat().st_size)
    return max(candidates, key=score)


def find_html(root: Path) -> Path | None:
    htmls = list(root.rglob("*.html"))
    if not htmls:
        return None
    def score(p: Path):
        depth = len(p.relative_to(root).parts)
        return (p.name.lower() == "index.html", -depth)
    return max(htmls, key=score)


def unblock(path: Path) -> int:
    """Entfernt den Zone.Identifier-Stream (Mark of the Web) unter Windows."""
    if os.name != "nt":
        return 0
    count = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                os.remove(str(p) + ":Zone.Identifier")
                count += 1
            except OSError:
                pass
    return count


def find_cover(game_dir: Path) -> Path | None:
    for p in game_dir.iterdir():
        if p.is_file() and p.stem.lower().startswith("cover") and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            return p
    shots = game_dir / "screenshots"
    if shots.is_dir():
        imgs = sorted(x for x in shots.iterdir() if x.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"))
        if imgs:
            return imgs[0]
    return None


def collect_uploads(game_dir: Path) -> list[Path]:
    """Alle Upload-Dateien eines Spiels (direkt im Ordner und in files/)."""
    skip = {"metadata.json", "site.html"}
    files = []
    for folder in (game_dir, game_dir / "files"):
        if not folder.is_dir():
            continue
        for p in folder.iterdir():
            if p.is_file() and p.name not in skip and not p.stem.lower().startswith("cover"):
                files.append(p)
    return files


def process_game(game_dir: Path, out_root: Path, prefer: str, used_slugs: set) -> dict | None:
    meta = load_metadata(game_dir / "metadata.json")
    title = meta.get("title") or game_dir.name
    slug = slugify(title)
    while slug in used_slugs:
        slug += "-2"
    used_slugs.add(slug)

    print(f"\n[{title}]")
    out_dir = out_root / slug
    build_root = out_dir / "build"
    if build_root.exists():
        shutil.rmtree(build_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    builds = {"windows": [], "web": []}
    for f in collect_uploads(game_dir):
        ext = f.suffix.lower()
        if ext in UNSUPPORTED_ARCHIVE_EXT:
            print(f"  ! {f.name}: Format wird nicht automatisch entpackt – bitte manuell nach {build_root}/")
            continue
        if ext in ARCHIVE_EXT:
            kind = classify_zip(f)
            if kind == "other":
                kind = classify_by_name(f)
            if kind in builds:
                dest = build_root / kind / f.stem
                print(f"  entpacke {f.name} -> {kind}")
                try:
                    extract(f, dest)
                except zipfile.BadZipFile:
                    print(f"  ! {f.name} ist kein gültiges Zip")
                    continue
                builds[kind].append(strip_single_root(dest))
            else:
                print(f"  überspringe {f.name} (vermutlich Linux/Mac/Sonstiges)")
        elif ext == ".exe":
            dest = build_root / "windows" / f.stem
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / f.name)
            builds["windows"].append(dest)
        elif ext == ".html":
            dest = build_root / "web" / f.stem
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / "index.html")
            builds["web"].append(dest)

    entry = {
        "slug": slug,
        "title": title,
        "authors": authors_from_metadata(meta, game_dir.parent.name if game_dir.parent != game_dir else ""),
        "description": (meta.get("description") or meta.get("short_text") or "").strip(),
        "url": meta.get("url", ""),
        "cover": None,
        "cover_url": meta.get("cover_url") or meta.get("cover") or "",
        "exe": None,
        "web": None,
        "primary": None,
        "dir": str(out_dir.resolve()),
    }

    for root in builds["windows"]:
        exe = find_exe(root, title)
        if exe:
            entry["exe"] = str(exe.resolve())
            print(f"  exe: {exe.relative_to(out_dir)}")
            break
    if builds["windows"] and not entry["exe"]:
        print("  ! Windows-Build gefunden, aber keine passende .exe")

    for root in builds["web"]:
        html = find_html(root)
        if html:
            entry["web"] = str(html.resolve())
            print(f"  web: {html.relative_to(out_dir)}")
            break

    cover = find_cover(game_dir)
    if cover:
        target = out_dir / ("cover" + cover.suffix.lower())
        shutil.copy2(cover, target)
        entry["cover"] = str(target.resolve())

    order = ["exe", "web"] if prefer == "windows" else ["web", "exe"]
    for k in order:
        if entry[k]:
            entry["primary"] = k
            break

    if not entry["primary"]:
        print("  ! kein startbarer Build – wird trotzdem gelistet, aber ohne Start-Button")

    n = unblock(out_dir)
    if n:
        print(f"  Mark of the Web entfernt bei {n} Dateien")
    return entry


def main():
    ap = argparse.ArgumentParser(description="itch-dl-Downloads für den Jam-Launcher aufbereiten")
    ap.add_argument("--input", required=True, help="Ordner, in den itch-dl geladen hat")
    ap.add_argument("--output", default="games", help="Zielordner (Standard: games)")
    ap.add_argument("--prefer", choices=["windows", "web"], default="windows",
                    help="Welche Version bevorzugt gestartet wird, wenn beide vorhanden sind")
    ap.add_argument("--jam-title", default=None,
                    help="Titel, der im Launcher angezeigt wird (Standard: aus <input>/jam.txt bzw. der Jam-Seite)")
    args = ap.parse_args()

    in_root = Path(args.input)
    out_root = Path(args.output)
    if not in_root.is_dir():
        sys.exit(f"Eingabeordner nicht gefunden: {in_root}")
    out_root.mkdir(parents=True, exist_ok=True)

    jam_title = detect_jam_title(in_root, args.jam_title)
    jam_file = in_root / "jam.txt"
    jam_url = jam_file.read_text(encoding="utf-8", errors="replace").strip() if jam_file.is_file() else ""
    print(f"Jam: {jam_title}")

    # Jeder Ordner mit metadata.json ist ein Spiel; ohne Metadaten gilt jeder Ordner mit Zip/Exe
    game_dirs = sorted({p.parent for p in in_root.rglob("metadata.json")})
    if not game_dirs:
        game_dirs = sorted({p.parent for p in in_root.rglob("*") if p.suffix.lower() in (".zip", ".exe")})
    if not game_dirs:
        sys.exit("Keine Spiele gefunden. Hat itch-dl in diesen Ordner geladen?")

    used = set()
    games = []
    for gd in game_dirs:
        try:
            e = process_game(gd, out_root, args.prefer, used)
            if e:
                games.append(e)
        except Exception as ex:
            print(f"  !! Fehler bei {gd}: {ex}")

    games.sort(key=lambda g: g["title"].lower())
    data = {"jam": jam_title, "jam_url": jam_url, "games": games}
    with open(out_root / "games.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    ok = sum(1 for g in games if g["primary"])
    print(f"\nFertig: {len(games)} Spiele, {ok} startbar. -> {out_root / 'games.json'}")
    print("Jetzt: python launcher.py --games " + str(out_root))


if __name__ == "__main__":
    main()
