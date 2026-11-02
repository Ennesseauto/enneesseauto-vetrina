#!/usr/bin/env python3
"""
REPOST AUTOSCOUT24 — Server Locale Dashboard (127.0.0.1)

Espone le API locali per la Dashboard (repost/gestione-foto.html):
- /api/stato              -> Stato completo delle auto (In Salone, In Arrivo, Vendute, Foto)
- /api/cambia-stato       -> Sposta un'auto tra "salone", "arrivo" e "venduta" (anche su Drive)
- /api/imposta-copertina  -> Imposta qualsiasi foto (AutoScout24 o Extra) come 1a foto di copertina
- /api/carica-foto        -> Drag & Drop foto integrative con filtro anti-doppioni dHash e WebP
- /api/elimina-foto       -> Rimuove singola foto extra o tutte le foto extra di un'auto
- /api/aggiorna-autoscout -> Forza l'aggiornamento live immediato da AutoScout24
- /api/sincronizza        -> Rilegge la cartella Google Drive in < 1 secondo
- /api/apri-cartella      -> Apre la cartella dell'auto in Esplora File di Windows
"""
import base64
import ipaddress
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from aggiorna_annunci import FILE_DATI, PREFISSO, leggi_precedente
from cloud_github import (
    esegui_pull_iniziale,
    esporta_annunci_json,
    git_configurato,
    pianifica_push_background,
)
from foto_drive import (
    CARTELLA_EXTRA_WEB,
    ESTENSIONI_FOTO,
    carica_configurazione,
    carica_stato_manuale,
    mappa_tutte_cartelle_drive,
    percorso_drive,
    salva_stato_manuale,
    sincronizza_cartella_drive,
)

CARTELLA_ROOT = Path(__file__).resolve().parent.parent.parent
CARTELLA_REPOST = Path(__file__).resolve().parent.parent
SCRIPT_AGGIORNA = Path(__file__).resolve().parent / "aggiorna_annunci.py"
HOST = "127.0.0.1"
PORTA = 8765


def rileva_ip_lan() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def ip_autorizzato(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_loopback or ip.is_private
    except ValueError:
        return False


def trova_cartella_auto(id_auto: str, dir_drive: Path) -> Path | None:
    rif = id_auto[:8].lower()
    mappa = mappa_tutte_cartelle_drive(dir_drive)
    voce = mappa.get(rif)
    return voce[0] if voce else None


def salva_annunci_js(dati: dict):
    FILE_DATI.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = FILE_DATI.with_suffix(".tmp")
    temporaneo.write_text(
        PREFISSO + json.dumps(dati, ensure_ascii=True, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    temporaneo.replace(FILE_DATI)
    esporta_annunci_json(dati)


def stato_completo():
    config = carica_configurazione()
    dir_drive = percorso_drive(config)
    dati = leggi_precedente() or {"annunci": []}
    annunci = dati.get("annunci", [])
    esito = sincronizza_cartella_drive(annunci, dir_drive)
    stato_man = carica_stato_manuale()
    ordine_sito = stato_man.get("ordine_sito") or "autoscout"
    dati["ordineSito"] = ordine_sito
    salva_annunci_js(dati)

    mappa_drive = mappa_tutte_cartelle_drive(dir_drive)
    dettagli_auto = []
    for a in annunci:
        rif = a["id"][:8].lower()
        voce_c = mappa_drive.get(rif)
        cartella = voce_c[0] if voce_c else None
        file_extra = []
        manifest = {}
        manifest_path = CARTELLA_EXTRA_WEB / a["id"] / ".manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8")).get("file_processati", {})
            except Exception:
                pass

        if cartella and cartella.exists():
            for f in sorted(cartella.iterdir(), key=lambda p: p.name.lower()):
                if f.is_file() and f.suffix.lower() in ESTENSIONI_FOTO and not f.name.startswith("."):
                    info_m = manifest.get(f.name) or {}
                    slug = info_m.get("slug")
                    file_extra.append({
                        "nome": f.name,
                        "copertina": f.stem.lower().strip().startswith("copertina"),
                        "doppione": bool(info_m.get("doppione")),
                        "slug": slug,
                        "urlExtra": f"foto-extra/{a['id']}/{slug}" if slug else None,
                    })

        copia = dict(a)
        copia["_cartella"] = str(cartella) if cartella else ""
        copia["_fileDrive"] = file_extra
        dettagli_auto.append(copia)

    porta = int(config.get("porta_dashboard") or PORTA)
    ip_lan = rileva_ip_lan()
    return {
        "ok": True,
        "aggiornato": dati.get("aggiornato"),
        "ordineSito": ordine_sito,
        "cloudAttivo": git_configurato(),
        "percorsoDrive": str(dir_drive),
        "urlReteLocale": f"http://{ip_lan}:{porta}/gestione-foto.html",
        "riepilogo": esito,
        "annunci": dettagli_auto,
    }


class GestoreLocale(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def invia_json(self, codice: int, payload: dict):
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Cache-Control, Pragma")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Cache-Control, Pragma")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.end_headers()

    def leggi_json(self) -> dict:
        lunghezza = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(lunghezza) if lunghezza > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if not ip_autorizzato(self.client_address[0]):
            self.send_error(403, "Accesso consentito solo dalla rete locale del concessionario")
            return
        parsed = urllib.parse.urlparse(self.path)
        percorso = urllib.parse.unquote(parsed.path)

        if percorso == "/api/stato":
            self.invia_json(200, stato_completo())
            return

        if percorso in ("/", "/gestione-foto.html"):
            percorso = "/repost/gestione-foto.html"

        file_locale = (CARTELLA_ROOT / percorso.lstrip("/")).resolve()
        if not file_locale.is_file():
            alt = (CARTELLA_REPOST / percorso.lstrip("/")).resolve()
            if str(alt).startswith(str(CARTELLA_REPOST)) and alt.is_file():
                file_locale = alt
        if not str(file_locale).startswith(str(CARTELLA_ROOT)) or not file_locale.is_file():
            self.send_error(404, "File non trovato")
            return

        tipo, _ = mimetypes.guess_type(str(file_locale))
        dati = file_locale.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo or "application/octet-stream")
        self.send_header("Content-Length", str(len(dati)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.end_headers()
        self.wfile.write(dati)

    def do_POST(self):
        if not ip_autorizzato(self.client_address[0]):
            self.invia_json(403, {"ok": False, "errore": "Accesso consentito solo dalla rete locale"})
            return
        parsed = urllib.parse.urlparse(self.path)
        percorso = parsed.path

        try:
            body = self.leggi_json()
        except Exception as e:
            self.invia_json(400, {"ok": False, "errore": f"Richiesta non valida: {e}"})
            return

        config = carica_configurazione()
        dir_drive = percorso_drive(config)

        # 1. Sincronizza veloce (< 1 secondo)
        if percorso == "/api/sincronizza":
            stato = stato_completo()
            pianifica_push_background("Sincronizzazione cartella foto")
            self.invia_json(200, stato)
            return

        # 2. Aggiornamento forzato immediato da AutoScout24
        if percorso == "/api/aggiorna-autoscout":
            try:
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT_AGGIORNA), "--pausa", "0.6"],
                    cwd=str(CARTELLA_REPOST),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=180,
                )
                stato = stato_completo()
                stato["log"] = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
                stato["exitCode"] = proc.returncode
                pianifica_push_background("Aggiornamento da AutoScout24")
                self.invia_json(200, stato)
            except Exception as e:
                self.invia_json(500, {"ok": False, "errore": f"Errore aggiornamento AutoScout24: {e}"})
            return

        # 3. Cambia stato dell'auto ("salone" | "arrivo" | "venduta")
        if percorso == "/api/cambia-stato":
            id_auto = body.get("id")
            nuovo_stato = body.get("stato")
            if not id_auto or nuovo_stato not in ("salone", "arrivo", "venduta"):
                self.invia_json(400, {"ok": False, "errore": "Parametri stato non validi"})
                return
            stato_man = carica_stato_manuale()
            stato_man["stati"][id_auto] = nuovo_stato
            salva_stato_manuale(stato_man)
            stato = stato_completo()
            pianifica_push_background(f"Cambio stato auto {id_auto[:8]} -> {nuovo_stato}")
            self.invia_json(200, stato)
            return

        # 3b. Imposta l'ordine predefinito del sito deciso dalla Dashboard
        if percorso == "/api/imposta-ordine":
            nuovo_ordine = body.get("ordine") or "autoscout"
            stato_man = carica_stato_manuale()
            stato_man["ordine_sito"] = nuovo_ordine
            salva_stato_manuale(stato_man)
            stato = stato_completo()
            pianifica_push_background(f"Ordine vetrina -> {nuovo_ordine}")
            self.invia_json(200, stato)
            return

        # 4. Imposta qualsiasi foto (AutoScout24 o Extra) come immagine di copertina (#1)
        if percorso == "/api/imposta-copertina":
            id_auto = body.get("id")
            url_foto = body.get("foto")
            if not id_auto or not url_foto:
                self.invia_json(400, {"ok": False, "errore": "ID auto o foto mancante"})
                return
            stato_man = carica_stato_manuale()
            stato_man["copertine"][id_auto] = url_foto
            salva_stato_manuale(stato_man)
            stato = stato_completo()
            pianifica_push_background(f"Imposta copertina auto {id_auto[:8]}")
            self.invia_json(200, stato)
            return

        # 5. Apri la cartella in Esplora File di Windows
        if percorso == "/api/apri-cartella":
            id_auto = body.get("id")
            bersaglio = trova_cartella_auto(id_auto, dir_drive) if id_auto else dir_drive
            if bersaglio and bersaglio.exists():
                if sys.platform.startswith("win"):
                    os.startfile(str(bersaglio))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(bersaglio)])
                else:
                    subprocess.Popen(["xdg-open", str(bersaglio)])
                self.invia_json(200, {"ok": True})
            else:
                self.invia_json(404, {"ok": False, "errore": "Cartella non trovata"})
            return

        # 6. Caricamento Drag & Drop di foto
        if percorso == "/api/carica-foto":
            id_auto = body.get("id")
            files = body.get("files") or []
            cartella = trova_cartella_auto(id_auto, dir_drive) if id_auto else None
            if not cartella or not cartella.exists():
                self.invia_json(404, {"ok": False, "errore": "Cartella dell'auto non trovata"})
                return

            salvati = 0
            for item in files:
                nome_orig = Path(item.get("name") or "foto.jpg").name
                nome_pulito = re.sub(r'[<>:"/\\|?*]+', "_", nome_orig)
                est = Path(nome_pulito).suffix.lower()
                if est not in ESTENSIONI_FOTO:
                    nome_pulito += ".jpg"
                b64 = item.get("data") or ""
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                try:
                    raw_bytes = base64.b64decode(b64)
                    dest = cartella / nome_pulito
                    dest.write_bytes(raw_bytes)
                    salvati += 1
                except Exception:
                    continue

            stato = stato_completo()
            stato["salvati"] = salvati
            pianifica_push_background(f"Caricate {salvati} foto extra per {id_auto[:8]}")
            self.invia_json(200, stato)
            return

        # 7. Elimina una foto extra (o tutte le foto extra di quell'auto)
        if percorso == "/api/elimina-foto":
            id_auto = body.get("id")
            nome_file = body.get("nome")
            url_extra = body.get("urlExtra")
            tutte = bool(body.get("tutte"))
            cartella = trova_cartella_auto(id_auto, dir_drive) if id_auto else None
            if not cartella or not cartella.exists():
                self.invia_json(404, {"ok": False, "errore": "Cartella dell'auto non trovata"})
                return

            if tutte:
                for p in cartella.iterdir():
                    if p.is_file() and p.suffix.lower() in ESTENSIONI_FOTO and not p.name.startswith("."):
                        p.unlink(missing_ok=True)
            else:
                # Se è stato passato urlExtra (es. "foto-extra/<id>/<slug>"), risale al file sorgente dal manifest
                if not nome_file and url_extra:
                    slug_cercato = url_extra.rsplit("/", 1)[-1]
                    manifest_path = CARTELLA_EXTRA_WEB / id_auto / ".manifest.json"
                    if manifest_path.exists():
                        try:
                            proc_map = json.loads(manifest_path.read_text(encoding="utf-8")).get("file_processati", {})
                            for nf, meta in proc_map.items():
                                if meta.get("slug") == slug_cercato:
                                    nome_file = nf
                                    break
                        except Exception:
                            pass
                if nome_file:
                    bersaglio = (cartella / Path(nome_file).name).resolve()
                    if bersaglio.parent == cartella.resolve() and bersaglio.is_file():
                        bersaglio.unlink(missing_ok=True)

            stato = stato_completo()
            pianifica_push_background(f"Eliminata foto extra per {id_auto[:8]}")
            self.invia_json(200, stato)
            return

        self.invia_json(404, {"ok": False, "errore": "Endpoint sconosciuto"})


def main():
    config = carica_configurazione()
    porta = int(config.get("porta_dashboard") or PORTA)
    rete_locale = bool(config.get("accesso_rete_locale", True)) or ("--rete-locale" in sys.argv)
    bind_host = "0.0.0.0" if rete_locale else HOST
    ip_lan = rileva_ip_lan()
    print("=================================================================")
    print("  REPOST AUTOSCOUT24 — Dashboard Locale & Cloud H24")
    print("=================================================================")
    esegui_pull_iniziale()
    stato_completo()
    url_pc = f"http://127.0.0.1:{porta}/repost/gestione-foto.html"
    url_lan = f"http://{ip_lan}:{porta}/gestione-foto.html"
    server = ThreadingHTTPServer((bind_host, porta), GestoreLocale)
    print(f"\n  • Su questo PC:                      {url_pc}")
    if rete_locale and ip_lan != "127.0.0.1":
        print(f"  • Altri PC / Telefoni Wi-Fi ufficio: {url_lan}")
    print("\nLascia aperta questa finestra mentre lavori. Premi Ctrl+C per chiudere.\n")
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(url_pc)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChiusura dashboard locale.")
        server.server_close()


if __name__ == "__main__":
    main()
