#!/usr/bin/env python3
"""
launcher.py – lokaler Jam-Launcher (nur Python-Standardbibliothek).

  python launcher.py --games games
  -> http://localhost:8000  (am besten im Kiosk-Modus öffnen, siehe run.bat)

- zeigt alle Spiele aus games.json als Galerie
- hostet Web-Builds selbst, mit COOP/COEP-Headern (nötig für Godot 4 / Unity mit Threads)
- startet Windows-.exe-Dateien und kann sie wieder beenden
- Tastatur: Pfeiltasten wählen, Enter startet, Esc verlässt ein Web-Spiel
"""

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/octet-stream", ".pck")
mimetypes.add_type("application/octet-stream", ".data")

GAMES: dict = {}
JAM_TITLE = "Game Jam"
RUNNING: dict[str, subprocess.Popen] = {}
LOCK = threading.Lock()


def load_games(folder: Path):
    global GAMES, JAM_TITLE
    with open(folder / "games.json", encoding="utf-8") as f:
        data = json.load(f)
    JAM_TITLE = data.get("jam") or JAM_TITLE
    GAMES = {g["slug"]: g for g in data["games"]}


def public_games():
    out = []
    for g in GAMES.values():
        out.append({
            "slug": g["slug"],
            "title": g["title"],
            "authors": g.get("authors", ""),
            "description": g.get("description", ""),
            "url": g.get("url", ""),
            "cover": f"/cover/{g['slug']}" if (g.get("cover") or g.get("cover_url")) else None,
            "hasExe": bool(g.get("exe")),
            "hasWeb": bool(g.get("web")),
            "primary": g.get("primary"),
        })
    return out


def start_exe(slug: str) -> str:
    g = GAMES[slug]
    exe = g.get("exe")
    if not exe or not Path(exe).is_file():
        return "Keine .exe für dieses Spiel gefunden"
    with LOCK:
        p = RUNNING.get(slug)
        if p and p.poll() is None:
            return "läuft bereits"
        try:
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            RUNNING[slug] = subprocess.Popen([exe], cwd=str(Path(exe).parent), creationflags=flags)
        except OSError as e:
            return f"Start fehlgeschlagen: {e}"
    return "ok"


def stop_exe(slug: str) -> str:
    with LOCK:
        p = RUNNING.get(slug)
        if not p or p.poll() is not None:
            return "läuft nicht"
        p.terminate()
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()
    return "ok"


def running_slugs():
    with LOCK:
        return [s for s, p in RUNNING.items() if p.poll() is None]


class Handler(BaseHTTPRequestHandler):
    server_version = "JamLauncher/1.0"

    def log_message(self, fmt, *args):  # ruhiger Log
        if "/status" not in (args[0] if args else ""):
            super().log_message(fmt, *args)

    # --- Hilfsfunktionen ---------------------------------------------------
    def _headers(self, status=HTTPStatus.OK, ctype="text/html; charset=utf-8", length=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        # Für SharedArrayBuffer (Godot 4 Threads, Unity) zwingend:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send(self, body, status=HTTPStatus.OK, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self._headers(status, ctype, len(body))
        self.wfile.write(body)

    def _json(self, obj, status=HTTPStatus.OK):
        self._send(json.dumps(obj, ensure_ascii=False), status, "application/json; charset=utf-8")

    def _file(self, path: Path):
        if not path.is_file():
            return self._send("Datei nicht gefunden", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        size = path.stat().st_size
        self._headers(HTTPStatus.OK, ctype, size)
        with open(path, "rb") as f:
            while chunk := f.read(1 << 16):
                self.wfile.write(chunk)

    # --- Routing -----------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]

        if not parts:
            return self._send(INDEX_HTML.replace("{{JAM}}", JAM_TITLE))
        if parts == ["games.json"]:
            return self._json({"jam": JAM_TITLE, "games": public_games()})
        if parts == ["status"]:
            return self._json({"running": running_slugs()})

        if len(parts) >= 2 and parts[1] in GAMES:
            g = GAMES[parts[1]]
            kind = parts[0]
            if kind == "cover":
                if g.get("cover") and Path(g["cover"]).is_file():
                    return self._file(Path(g["cover"]))
                if g.get("cover_url"):
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", g["cover_url"])
                    self.end_headers()
                    return
                return self._send("", HTTPStatus.NOT_FOUND)
            if kind == "play":
                if not g.get("web"):
                    return self._send("Kein Web-Build", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")
                html = PLAY_HTML.replace("{{TITLE}}", g["title"]).replace("{{SRC}}", f"/web/{g['slug']}/{Path(g['web']).name}")
                return self._send(html)
            if kind == "web":
                if not g.get("web"):
                    return self._send("", HTTPStatus.NOT_FOUND)
                root = Path(g["web"]).parent.resolve()
                rel = "/".join(parts[2:]) or Path(g["web"]).name
                target = (root / rel).resolve()
                if root not in target.parents and target != root:
                    return self._send("", HTTPStatus.FORBIDDEN)
                if target.is_dir():
                    target = target / "index.html"
                return self._file(target)

        self._send("Nicht gefunden", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")

    def do_POST(self):
        parts = [unquote(p) for p in urlparse(self.path).path.strip("/").split("/") if p]
        if len(parts) == 2 and parts[1] in GAMES:
            if parts[0] == "launch":
                return self._json({"result": start_exe(parts[1])})
            if parts[0] == "stop":
                return self._json({"result": stop_exe(parts[1])})
        self._json({"result": "unbekannt"}, HTTPStatus.NOT_FOUND)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{JAM}} – Spiele</title>
<style>
  :root {
    --bg: #0d1b19;
    --bg-raised: #132824;
    --ink: #f3efe6;
    --ink-soft: #b5c6c0;
    --pink: #d8124a;
    --teal: #009682;
    --teal-soft: #1d6b60;
    --radius: 14px;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--ink);
    font-family: "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif; }
  body { padding: 40px 48px 64px; min-height: 100vh; }

  header { display: flex; align-items: baseline; justify-content: space-between; gap: 24px;
    margin-bottom: 36px; flex-wrap: wrap; }
  header h1 { margin: 0; font-size: clamp(32px, 4vw, 52px); font-weight: 700; letter-spacing: -0.02em; }
  header h1 span { color: var(--teal); }
  header p { margin: 0; color: var(--ink-soft); font-size: 18px; }
  header .count { color: var(--ink); }

  .search { margin-bottom: 28px; }
  .search input { width: min(420px, 100%); padding: 12px 16px; font: inherit; font-size: 18px;
    color: var(--ink); background: var(--bg-raised); border: 1px solid var(--teal-soft);
    border-radius: 10px; outline: none; }
  .search input:focus { border-color: var(--teal); }

  .grid { display: grid; gap: 28px; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); }

  .card { background: var(--bg-raised); border-radius: var(--radius); overflow: hidden;
    display: flex; flex-direction: column; outline: 3px solid transparent; outline-offset: 3px;
    transition: outline-color .12s; }
  .card.selected { outline-color: var(--pink); }
  .card .cover { aspect-ratio: 63 / 50; background: #0a1513 center/cover no-repeat;
    display: grid; place-items: center; font-size: 56px; }
  .card .body { padding: 18px 20px 20px; display: flex; flex-direction: column; gap: 6px; flex: 1; }
  .card h2 { margin: 0; font-size: 24px; line-height: 1.15; letter-spacing: -0.01em; }
  .card .team { color: var(--ink-soft); font-size: 16px; }
  .card .desc { color: var(--ink-soft); font-size: 15px; line-height: 1.45; margin-top: 4px;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .card .actions { margin-top: auto; padding-top: 16px; display: flex; gap: 10px; flex-wrap: wrap; }

  button { font: inherit; font-size: 17px; font-weight: 600; padding: 11px 20px; border-radius: 10px;
    border: 0; cursor: pointer; color: #fff; background: var(--pink); }
  button:hover { filter: brightness(1.1); }
  button:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }
  button.alt { background: transparent; color: var(--ink); border: 1px solid var(--teal); }
  button.stop { background: #3a1f24; color: #ffb3c4; }
  button[disabled] { opacity: .45; cursor: default; }

  .pill { display: inline-block; font-size: 13px; font-weight: 600; padding: 3px 9px; border-radius: 999px;
    background: var(--teal); color: #fff; margin-right: 6px; }
  .pill.off { background: #3a4a46; color: var(--ink-soft); }

  .empty { color: var(--ink-soft); font-size: 20px; padding: 60px 0; }
  .toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%);
    background: var(--teal); color: #fff; padding: 12px 20px; border-radius: 10px; font-size: 17px;
    opacity: 0; transition: opacity .2s; pointer-events: none; }
  .toast.show { opacity: 1; }

  .hint { position: fixed; right: 24px; bottom: 20px; color: var(--ink-soft); font-size: 14px; }
  @media (prefers-reduced-motion: reduce) { .card, .toast { transition: none; } }
</style>
</head>
<body>
<header>
  <h1>🌴 <span>{{JAM}}</span> Spiele</h1>
  <p><span class="count" id="count">…</span> Einreichungen</p>
</header>
<div class="search"><input id="q" type="search" placeholder="Spiel oder Team suchen" autocomplete="off"></div>
<div class="grid" id="grid"></div>
<div class="toast" id="toast"></div>
<div class="hint">Pfeiltasten wählen · Enter startet · Esc beendet</div>

<script>
let games = [], running = new Set(), sel = 0, filtered = [];

function esc(s){ return String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function toast(msg){ const t = document.getElementById('toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2200); }

function render(){
  const q = document.getElementById('q').value.trim().toLowerCase();
  filtered = games.filter(g => !q || (g.title + ' ' + g.authors).toLowerCase().includes(q));
  document.getElementById('count').textContent = filtered.length + (q ? ' / ' + games.length : '');
  const grid = document.getElementById('grid');
  if (!filtered.length) { grid.innerHTML = '<p class="empty">Kein Spiel passt zur Suche.</p>'; return; }
  sel = Math.min(sel, filtered.length - 1);
  grid.innerHTML = filtered.map((g, i) => {
    const isRun = running.has(g.slug);
    const cover = g.cover ? `style="background-image:url('${g.cover}')"` : '';
    const primaryBtn = g.primary === 'exe'
      ? `<button data-act="exe" data-slug="${g.slug}">Spielen</button>`
      : g.primary === 'web' ? `<button data-act="web" data-slug="${g.slug}">Spielen</button>`
      : `<button disabled>Kein Build</button>`;
    const secondary = (g.hasExe && g.hasWeb)
      ? (g.primary === 'exe' ? `<button class="alt" data-act="web" data-slug="${g.slug}">Im Browser</button>`
                             : `<button class="alt" data-act="exe" data-slug="${g.slug}">Als .exe</button>`) : '';
    const stop = isRun ? `<button class="stop" data-act="stop" data-slug="${g.slug}">Beenden</button>` : '';
    return `<article class="card ${i===sel?'selected':''}" data-i="${i}">
      <div class="cover" ${cover}>${g.cover ? '' : '🎮'}</div>
      <div class="body">
        <h2>${esc(g.title)}</h2>
        <div class="team">${esc(g.authors)}</div>
        <div>${g.hasExe ? '<span class="pill">Windows</span>' : ''}${g.hasWeb ? '<span class="pill">Web</span>' : ''}${isRun ? '<span class="pill" style="background:var(--pink)">läuft</span>' : ''}</div>
        <div class="desc">${esc(g.description)}</div>
        <div class="actions">${isRun ? stop : primaryBtn}${secondary}</div>
      </div></article>`;
  }).join('');
}

async function act(action, slug){
  if (action === 'web') { location.href = '/play/' + slug; return; }
  const r = await fetch('/' + (action === 'exe' ? 'launch' : 'stop') + '/' + slug, {method:'POST'});
  const j = await r.json();
  toast(j.result === 'ok' ? (action === 'exe' ? 'Gestartet' : 'Beendet') : j.result);
  await refresh();
}

async function refresh(){
  const s = await (await fetch('/status')).json();
  const next = new Set(s.running);
  if ([...next].join() !== [...running].join()) { running = next; render(); }
}

document.getElementById('grid').addEventListener('click', e => {
  const b = e.target.closest('button[data-act]'); if (b) { act(b.dataset.act, b.dataset.slug); return; }
  const c = e.target.closest('.card'); if (c) { sel = +c.dataset.i; render(); }
});
document.getElementById('q').addEventListener('input', () => { sel = 0; render(); });

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' && !['ArrowDown','ArrowUp','Enter','Escape'].includes(e.key)) return;
  const cols = Math.max(1, Math.round(document.getElementById('grid').clientWidth / 318));
  const g = filtered[sel];
  if (e.key === 'ArrowRight') sel++; else if (e.key === 'ArrowLeft') sel--;
  else if (e.key === 'ArrowDown') sel += cols; else if (e.key === 'ArrowUp') sel -= cols;
  else if (e.key === 'Enter' && g) { if (running.has(g.slug)) return; if (g.primary) act(g.primary, g.slug); return; }
  else if (e.key === 'Escape' && g && running.has(g.slug)) { act('stop', g.slug); return; }
  else if (e.key === '/' ) { document.getElementById('q').focus(); e.preventDefault(); return; }
  else return;
  e.preventDefault();
  sel = (sel + filtered.length) % filtered.length;
  render();
  document.querySelector('.card.selected')?.scrollIntoView({block:'nearest'});
});

fetch('/games.json').then(r => r.json()).then(d => { games = d.games; render(); refresh(); setInterval(refresh, 1500); });
</script>
</body>
</html>
"""

PLAY_HTML = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>{{TITLE}}</title>
<style>
  html, body { margin: 0; height: 100%; background: #000; color: #f3efe6;
    font-family: "Segoe UI", system-ui, sans-serif; overflow: hidden; }
  .bar { position: fixed; top: 0; left: 0; right: 0; height: 44px; display: flex; align-items: center;
    gap: 16px; padding: 0 14px; background: #0d1b19; font-size: 16px; z-index: 2; }
  .bar a { color: #fff; background: #d8124a; text-decoration: none; padding: 7px 14px; border-radius: 8px;
    font-weight: 600; }
  .bar span { color: #b5c6c0; }
  iframe { position: fixed; top: 44px; left: 0; width: 100%; height: calc(100% - 44px); border: 0; background: #000; }
</style>
</head>
<body>
<div class="bar"><a href="/">Zurück zur Übersicht</a><strong>{{TITLE}}</strong><span>Esc = zurück</span></div>
<iframe src="{{SRC}}" allow="autoplay; fullscreen; gamepad; cross-origin-isolated" allowfullscreen></iframe>
<script>
  document.addEventListener('keydown', e => { if (e.key === 'Escape') location.href = '/'; });
  // Esc auch abfangen, wenn das Spiel den Fokus hat (nur gleiche Origin möglich)
  const f = document.querySelector('iframe');
  f.addEventListener('load', () => { try { f.contentWindow.addEventListener('keydown', e => { if (e.key === 'Escape') location.href = '/'; }); } catch (_) {} });
  f.focus();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Lokaler Jam-Launcher")
    ap.add_argument("--games", default="games", help="Ordner mit games.json (von prepare.py)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    args = ap.parse_args()

    folder = Path(args.games)
    if not (folder / "games.json").is_file():
        sys.exit(f"{folder / 'games.json'} fehlt – erst prepare.py ausführen.")
    load_games(folder)

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}/"
    print(f"{JAM_TITLE}: {len(GAMES)} Spiele geladen. Launcher läuft auf {url}  (Strg+C beendet)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for slug in list(RUNNING):
            stop_exe(slug)


if __name__ == "__main__":
    main()
