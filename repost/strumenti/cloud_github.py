#!/usr/bin/env python3
"""
REPOST AUTOSCOUT24 — Sincronizzazione Automatica Cloud H24 (GitHub Pages)

Questo modulo permette alla Dashboard locale (server_foto.py) di:
1. Generare il file di puri dati JSON `repost/dati/annunci.json` (sicuro al 100%, zero codice eseguibile).
2. Inviare automaticamente in background (`git commit` + `git push`) ogni modifica fatta dalla
   Dashboard (Stato In Salone / In Arrivo / Venduta, Copertina #1, Ordine, Foto Extra WebP)
   verso il repository GitHub Pages, così il sito rimane visibile H24 anche a PC spento.
3. Scaricare all'avvio della Dashboard eventuali aggiornamenti orari fatti da GitHub Actions
   mentre il PC era spento (`git pull`).
"""
import json
import subprocess
import threading
import urllib.request
from pathlib import Path

CARTELLA_ROOT = Path(__file__).resolve().parent.parent.parent
CARTELLA_REPOST = Path(__file__).resolve().parent.parent
FILE_DATI_JS = CARTELLA_REPOST / "dati" / "annunci.js"
FILE_DATI_JSON = CARTELLA_REPOST / "dati" / "annunci.json"
FILE_CONFIG = CARTELLA_REPOST / "configurazione.json"

_lock_git = threading.Lock()
_timer_push = None


def esporta_annunci_json(dati: dict):
    """Salva una copia in puro JSON (senza codice JS) per la lettura sicura da GitHub Pages."""
    FILE_DATI_JSON.parent.mkdir(parents=True, exist_ok=True)
    temp = FILE_DATI_JSON.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(dati, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temp.replace(FILE_DATI_JSON)


def git_configurato() -> bool:
    """Verifica se la cartella è collegata a un repository Git con remote 'origin'."""
    if not (CARTELLA_ROOT / ".git").exists():
        return False
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(CARTELLA_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def esegui_pull_iniziale():
    """All'avvio della Dashboard, recupera eventuali aggiornamenti orari fatti da GitHub Actions a PC spento."""
    if not git_configurato():
        return
    with _lock_git:
        try:
            subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", "main"],
                cwd=str(CARTELLA_ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            pass


def sincronizza_cloud_ora(motivo: str = "Aggiornamento da Dashboard"):
    """Esegue commit + pull --rebase + push verso GitHub Pages."""
    if not git_configurato():
        return False
    with _lock_git:
        try:
            percorsi = [
                "repost/dati/annunci.json",
                "repost/dati/annunci.js",
                "repost/dati/stato_manuale.json",
                "repost/dati/foto-extra",
                "repost/embed/motorexpo-embed.js",
            ]
            for p in percorsi:
                if (CARTELLA_ROOT / p).exists():
                    subprocess.run(["git", "add", "-A", p], cwd=str(CARTELLA_ROOT), capture_output=True, timeout=15)

            stato_git = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(CARTELLA_ROOT),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if not stato_git.stdout.strip():
                return True

            subprocess.run(
                ["git", "commit", "-m", motivo],
                cwd=str(CARTELLA_ROOT),
                capture_output=True,
                text=True,
                timeout=15,
            )
            subprocess.run(
                ["git", "pull", "--rebase", "--autostash", "origin", "main"],
                cwd=str(CARTELLA_ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )
            push = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=str(CARTELLA_ROOT),
                capture_output=True,
                text=True,
                timeout=45,
            )
            if push.returncode == 0:
                try:
                    urllib.request.urlopen(
                        "https://purge.jsdelivr.net/gh/Ennesseauto/enneesseauto-vetrina@main/repost/dati/annunci.json",
                        timeout=6,
                    ).read()
                except Exception:
                    pass
                return True
            return False
        except Exception:
            return False


def pianifica_push_background(motivo: str = "Aggiornamento da Dashboard", ritardo_sec: float = 1.5):
    """Raggruppa clic ravvicinati nella Dashboard e invia l'aggiornamento a GitHub Pages in background."""
    global _timer_push
    if not git_configurato():
        return
    if _timer_push is not None:
        try:
            _timer_push.cancel()
        except Exception:
            pass
    _timer_push = threading.Timer(ritardo_sec, sincronizza_cloud_ora, args=(motivo,))
    _timer_push.daemon = True
    _timer_push.start()
