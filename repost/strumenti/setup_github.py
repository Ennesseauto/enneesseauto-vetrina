#!/usr/bin/env python3
"""
REPOST AUTOSCOUT24 — Configurazione Guidata GitHub Pages (H24)
Collega la cartella locale al repository GitHub Pages per mantenere il sito
sempre visibile 24/7 anche a PC spento e ricevere aggiornamenti ogni ora.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from aggiorna_annunci import leggi_precedente
from cloud_github import esporta_annunci_json
from foto_drive import carica_configurazione, FILE_CONFIG

CARTELLA_ROOT = Path(__file__).resolve().parent.parent.parent
CARTELLA_REPOST = Path(__file__).resolve().parent.parent


def esegui(cmd: list[str], check: bool = False):
    return subprocess.run(cmd, cwd=str(CARTELLA_ROOT), text=True, capture_output=True, check=check)


def estrai_github_pages_url(repo_url: str) -> str | None:
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", repo_url.strip(), re.I)
    if not m:
        return None
    utente, repo = m.group(1), m.group(2)
    return f"https://{utente}.github.io/{repo}"


def genera_file_codici_duda(cloud_url: str):
    codice_1 = f"""<!-- BLOCCO 1: HOMEPAGE — DIVISIONE AUTO (IN SALONE) -->
<div id="ees-home-salone" data-ees-blocco="salone"></div>
<script>
(function() {{
  window.EES_CONFIG = {{ cloudOrigin: '{cloud_url}' }};
  if (window.__EES_LOADER__) return;
  window.__EES_LOADER__ = true;
  var s = document.createElement('script');
  s.src = '{cloud_url}/repost/embed/motorexpo-embed.js?t=' + Math.floor(Date.now() / 60000);
  document.head.appendChild(s);
}})();
</script>"""

    codice_2 = """<!-- BLOCCO 2: HOMEPAGE — VETTURE IN ARRIVO -->
<div id="ees-home-arrivo" data-ees-blocco="arrivo" data-nascondi-riga="true"></div>"""

    codice_3 = f"""<!-- BLOCCO 3: PAGINA AUTOVETTURE — CATALOGO COMPLETO + FILTRI + SCHEDA AUTO -->
<div id="ees-catalogo-completo" data-ees-blocco="catalogo"></div>
<script>
(function() {{
  window.EES_CONFIG = {{ cloudOrigin: '{cloud_url}' }};
  if (window.__EES_LOADER__) return;
  window.__EES_LOADER__ = true;
  var s = document.createElement('script');
  s.src = '{cloud_url}/repost/embed/motorexpo-embed.js?t=' + Math.floor(Date.now() / 60000);
  document.head.appendChild(s);
}})();
</script>"""

    testo = f"""===========================================================================
  CODICI EMBED H24 PRONTI PER IL SITO ENNE ESSE AUTO (CON GITHUB PAGES)
  URL Cloud H24: {cloud_url}
===========================================================================

--- 1. HOMEPAGE: Sotto il titolo "DIVISIONE AUTO" ---
{codice_1}

---------------------------------------------------------------------------

--- 2. HOMEPAGE: Sotto il titolo "VETTURE IN ARRIVO" ---
{codice_2}

---------------------------------------------------------------------------

--- 3. PAGINA AUTOVETTURE (/nuova-pagina): Catalogo Completo ---
{codice_3}
"""
    dest = CARTELLA_REPOST / "CODICI_SITO_PRONTI.txt"
    dest.write_text(testo, encoding="utf-8")
    return dest


def main():
    print("=================================================================")
    print("  CONFIGURAZIONE CLOUD H24 (GITHUB PAGES) — ENNE ESSE AUTO")
    print("=================================================================\n")

    dati = leggi_precedente()
    if dati:
        esporta_annunci_json(dati)

    if len(sys.argv) > 1 and sys.argv[1].strip():
        repo_url = sys.argv[1].strip()
    else:
        print("Incolla qui l'indirizzo del repository GitHub che hai creato")
        print("(es. https://github.com/tuo-utente/enneesseauto-vetrina.git):")
        repo_url = input("> ").strip()

    if not repo_url:
        print("\nOperazione annullata: nessun URL inserito.")
        sys.exit(1)

    cloud_url = estrai_github_pages_url(repo_url)
    if not cloud_url:
        print("\n[!] L'indirizzo inserito non sembra un URL GitHub valido.")
        sys.exit(1)

    config = carica_configurazione()
    config["cloud_url"] = cloud_url
    FILE_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Blocca l'origine dati in motorexpo-embed.js esclusivamente a questo progetto GitHub
    file_embed = CARTELLA_REPOST / "embed" / "motorexpo-embed.js"
    if file_embed.exists():
        codice_embed = file_embed.read_text(encoding="utf-8")
        codice_embed = re.sub(
            r"const LOCKED_GITHUB_ORIGIN = '[^']*';",
            f"const LOCKED_GITHUB_ORIGIN = '{cloud_url}';",
            codice_embed,
            count=1,
        )
        file_embed.write_text(codice_embed, encoding="utf-8")

    # 1. Inizializza Git se non presente
    if not (CARTELLA_ROOT / ".git").exists():
        esegui(["git", "init", "-b", "main"])
    else:
        esegui(["git", "branch", "-M", "main"])

    # 2. Assicura user.name e user.email locali
    chk_name = esegui(["git", "config", "user.name"])
    if not chk_name.stdout.strip():
        esegui(["git", "config", "user.name", "Dashboard Enne Esse Auto"])
        esegui(["git", "config", "user.email", "dashboard@enneesseauto.local"])

    # 3. Configura remote origin
    esegui(["git", "remote", "remove", "origin"])
    esegui(["git", "remote", "add", "origin", repo_url])

    # 4. Aggiunge i file necessari per GitHub Pages e GitHub Actions
    percorsi = [
        ".gitignore",
        ".github",
        "repost/configurazione.json",
        "repost/dati/annunci.json",
        "repost/dati/annunci.js",
        "repost/dati/stato_manuale.json",
        "repost/dati/foto-extra",
        "repost/embed/motorexpo-embed.js",
        "repost/strumenti",
    ]
    for p in percorsi:
        if (CARTELLA_ROOT / p).exists():
            esegui(["git", "add", "-A", p])

    esegui(["git", "commit", "-m", "Attivazione vetrina H24 Enne Esse Auto"])

    print("\nInvio dei dati a GitHub in corso (potrebbe aprirsi la finestra di accesso a GitHub)...")
    push = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=str(CARTELLA_ROOT))

    file_codici = genera_file_codici_duda(cloud_url)
    print("\n=================================================================")
    if push.returncode == 0:
        print("  [OK] SINCRONIZZAZIONE GITHUB COMPLETATA CON SUCCESSO!")
    else:
        print("  [!] Push non ancora completato (verifica l'accesso a GitHub e riprova).")
    print(f"  • Indirizzo GitHub Pages: {cloud_url}")
    print(f"  • Codici HTML pronti salvati in: {file_codici}")
    print("=================================================================\n")


if __name__ == "__main__":
    main()
