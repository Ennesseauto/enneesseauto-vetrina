#!/usr/bin/env python3
"""
REPOST AUTOSCOUT24 — Sincronizzazione Automatica Cloud H24 (GitHub)

Questo modulo permette alla Dashboard locale (server_foto.py) su QUALSIASI PC di:
1. Generare il file di puri dati JSON `repost/dati/annunci.json` (sicuro al 100%, zero codice eseguibile).
2. Inviare automaticamente in background ogni modifica fatta dalla Dashboard
   (Stato In Salone / In Arrivo / Venduta, Copertina #1, Ordine, Foto Extra WebP)
   verso il repository GitHub `Ennesseauto/enneesseauto-vetrina` (sia tramite API HTTPS
   diretta senza bisogno di Git installato, sia tramite Git locale), svuotando
   immediatamente la cache CDN in modo che il sito si aggiorni in 5-8 secondi.
"""
import base64
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
FILE_AUTH = Path(__file__).resolve().parent / ".gh_auth.json"

REPO_OWNER = "Ennesseauto"
REPO_NAME = "enneesseauto-vetrina"
BRANCH = "main"

_lock_git = threading.Lock()
_timer_push = None


def esporta_annunci_json(dati: dict):
    """Salva una copia in puro JSON (senza codice JS) per la lettura sicura da GitHub."""
    FILE_DATI_JSON.parent.mkdir(parents=True, exist_ok=True)
    temp = FILE_DATI_JSON.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(dati, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temp.replace(FILE_DATI_JSON)


def _leggi_token_locale() -> str:
    if FILE_AUTH.exists():
        try:
            d = json.loads(FILE_AUTH.read_text(encoding="utf-8"))
            t = (d.get("token") or "").strip()
            if t:
                return t
        except Exception:
            pass
    return ""


def git_configurato() -> bool:
    """Verifica se la Dashboard è collegata al Cloud (tramite token API HTTPS o Git locale)."""
    if _leggi_token_locale():
        return True
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


def _svuota_cache_cdn():
    for path in ("repost/dati/annunci.json", "repost/dati/annunci.js", "repost/dati/stato_manuale.json"):
        try:
            urllib.request.urlopen(
                f"https://purge.jsdelivr.net/gh/{REPO_OWNER}/{REPO_NAME}@{BRANCH}/{path}",
                timeout=6,
            ).read()
        except Exception:
            pass


def esegui_pull_iniziale():
    """All'avvio della Dashboard, recupera eventuali aggiornamenti orari fatti da GitHub Actions a PC spento."""
    token = _leggi_token_locale()
    if token:
        try:
            _svuota_cache_cdn()
            for rel in ("dati/annunci.js", "dati/annunci.json"):
                url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/repost/{rel}?ref={BRANCH}"
                req = urllib.request.Request(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github.v3.raw",
                        "User-Agent": "EnneEsseAuto-Dashboard",
                    },
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read()
                    if raw:
                        dest = CARTELLA_REPOST / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(raw)
            return
        except Exception:
            pass

    if not (CARTELLA_ROOT / ".git").exists():
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


def _api_github(metodo: str, endpoint: str, token: str, payload: dict | None = None) -> dict:
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}{endpoint}"
    dati = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=dati,
        method=metodo,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "EnneEsseAuto-Dashboard",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _push_via_api_https(token: str, motivo: str) -> bool:
    """Invia i file aggiornati direttamente a GitHub via HTTPS (funziona su qualsiasi PC anche senza Git)."""
    ref_info = _api_github("GET", f"/git/ref/heads/{BRANCH}", token)
    ultimo_commit_sha = ref_info["object"]["sha"]
    commit_info = _api_github("GET", f"/git/commits/{ultimo_commit_sha}", token)
    base_tree_sha = commit_info["tree"]["sha"]

    elementi_tree = []
    file_testo = [
        ("repost/dati/annunci.json", CARTELLA_REPOST / "dati" / "annunci.json"),
        ("repost/dati/annunci.js", CARTELLA_REPOST / "dati" / "annunci.js"),
        ("repost/dati/stato_manuale.json", CARTELLA_REPOST / "dati" / "stato_manuale.json"),
    ]
    for path_repo, path_locale in file_testo:
        if path_locale.exists():
            elementi_tree.append({
                "path": path_repo,
                "mode": "100644",
                "type": "blob",
                "content": path_locale.read_text(encoding="utf-8"),
            })

    # Includi eventuali miniature WebP in foto-extra
    dir_extra = CARTELLA_REPOST / "dati" / "foto-extra"
    if dir_extra.exists():
        for f in dir_extra.rglob("*"):
            if f.is_file():
                rel_repo = "repost/" + f.relative_to(CARTELLA_REPOST).as_posix()
                b64 = base64.b64encode(f.read_bytes()).decode("ascii")
                blob = _api_github("POST", "/git/blobs", token, {"content": b64, "encoding": "base64"})
                elementi_tree.append({
                    "path": rel_repo,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob["sha"],
                })

    if not elementi_tree:
        return True

    nuovo_tree = _api_github("POST", "/git/trees", token, {
        "base_tree": base_tree_sha,
        "tree": elementi_tree,
    })
    if nuovo_tree["sha"] == base_tree_sha:
        _svuota_cache_cdn()
        return True

    nuovo_commit = _api_github("POST", "/git/commits", token, {
        "message": motivo,
        "tree": nuovo_tree["sha"],
        "parents": [ultimo_commit_sha],
    })
    _api_github("PATCH", f"/git/refs/heads/{BRANCH}", token, {
        "sha": nuovo_commit["sha"],
        "force": True,
    })
    _svuota_cache_cdn()
    return True


def sincronizza_cloud_ora(motivo: str = "Aggiornamento da Dashboard"):
    """Invia le modifiche a GitHub (via API HTTPS diretta o via Git) e azzera subito la cache CDN."""
    with _lock_git:
        token = _leggi_token_locale()
        if token:
            try:
                if _push_via_api_https(token, motivo):
                    return True
            except Exception:
                pass

        if not (CARTELLA_ROOT / ".git").exists():
            return False
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
                _svuota_cache_cdn()
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
                _svuota_cache_cdn()
                return True
            return False
        except Exception:
            return False


def pianifica_push_background(motivo: str = "Aggiornamento da Dashboard", ritardo_sec: float = 0.8):
    """Raggruppa clic ravvicinati nella Dashboard e invia l'aggiornamento a GitHub in background."""
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
