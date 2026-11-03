#!/usr/bin/env python3
"""
Genera il pacchetto ZIP leggero per il concessionario:
Dashboard_EnneEsseAuto_Setup.zip
Contiene SOLO la Dashboard, il Manuale e il programma di installazione guidata.
"""
import json
import sys
import zipfile
from pathlib import Path

CARTELLA_ROOT = Path(__file__).resolve().parent.parent.parent
CARTELLA_REPOST = Path(__file__).resolve().parent.parent
ZIP_DEST = CARTELLA_ROOT / "Dashboard_EnneEsseAuto_Setup.zip"
FILE_AUTH = CARTELLA_REPOST / "strumenti" / ".gh_auth.json"

BAT_INSTALLER = (
    "@echo off\r\n"
    "setlocal EnableDelayedExpansion\r\n"
    "chcp 65001 >nul\r\n"
    "title Installazione Dashboard - Enne Esse Auto\r\n"
    'cd /d "%~dp0"\r\n'
    "\r\n"
    "echo =================================================================\r\n"
    "echo   AVVIO INSTALLAZIONE DASHBOARD PARCO AUTO - ENNE ESSE AUTO\r\n"
    "echo =================================================================\r\n"
    "echo.\r\n"
    "\r\n"
    'if not exist "%~dp0repost\\strumenti\\installa_dashboard.py" (\r\n'
    "    echo [ATTENZIONE] Non hai estratto il file ZIP!\r\n"
    "    echo.\r\n"
    "    echo Hai fatto doppio clic direttamente dentro il file compresso .zip.\r\n"
    "    echo Per installare la Dashboard:\r\n"
    "    echo   1. Fai tasto destro sul file Dashboard_EnneEsseAuto_Setup.zip\r\n"
    '    echo   2. Clicca su "Estrai tutto..."\r\n'
    '    echo   3. Apri la cartella estratta e fai doppio clic su "Installa Dashboard Enne Esse Auto.bat"\r\n'
    "    echo.\r\n"
    "    powershell -NoProfile -Command \"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Hai aperto il file direttamente da dentro lo ZIP senza estrarlo!' + [Environment]::NewLine + [Environment]::NewLine + '1. Fai tasto destro sul file ZIP e clicca su Estrai tutto...' + [Environment]::NewLine + '2. Poi avvia Installa Dashboard Enne Esse Auto dalla cartella estratta.', 'Enne Esse Auto - Estrai prima lo ZIP', 'OK', 'Warning')\" >nul 2>nul\r\n"
    "    pause\r\n"
    "    exit /b 1\r\n"
    ")\r\n"
    "\r\n"
    'set "PY_CMD="\r\n'
    "\r\n"
    "REM 1. Verifica se python reale (non lo stub Microsoft Store) e' installato\r\n"
    'python -c "import sys; assert sys.version_info >= (3, 8)" >nul 2>nul\r\n'
    "if !ERRORLEVEL! EQU 0 (\r\n"
    '    set "PY_CMD=python"\r\n'
    "    goto :esegui\r\n"
    ")\r\n"
    "\r\n"
    'py -3 -c "import sys; assert sys.version_info >= (3, 8)" >nul 2>nul\r\n'
    "if !ERRORLEVEL! EQU 0 (\r\n"
    '    set "PY_CMD=py -3"\r\n'
    "    goto :esegui\r\n"
    ")\r\n"
    "\r\n"
    "for %%P in (\r\n"
    '    "%LOCALAPPDATA%\\Programs\\Python\\Python312\\python.exe"\r\n'
    '    "%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe"\r\n'
    '    "%LOCALAPPDATA%\\Programs\\Python\\Python310\\python.exe"\r\n'
    '    "%ProgramFiles%\\Python312\\python.exe"\r\n'
    '    "%ProgramFiles%\\Python311\\python.exe"\r\n'
    ") do (\r\n"
    "    if exist %%P (\r\n"
    '        set "PY_CMD=%%P"\r\n'
    "        goto :esegui\r\n"
    "    )\r\n"
    ")\r\n"
    "\r\n"
    "echo Preparazione motore grafico Python sul PC (solo la prima volta, attendere 1 minuto)...\r\n"
    "echo Non chiudere questa finestra.\r\n"
    "echo.\r\n"
    "winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements\r\n"
    "\r\n"
    'if exist "%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe" (\r\n'
    '    set "PY_CMD="%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe""\r\n'
    "    goto :esegui\r\n"
    ")\r\n"
    "\r\n"
    "echo Scaricamento diretto di Python 3.11 ufficiale in corso...\r\n"
    'set "PY_SETUP=%TEMP%\\python-3.11.9-amd64.exe"\r\n'
    'curl.exe -L -s -o "%PY_SETUP%" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"\r\n'
    'if exist "%PY_SETUP%" (\r\n'
    "    echo Installazione di Python 3.11 in corso (attendere circa 30-45 secondi)...\r\n"
    '    "%PY_SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_tcltk=1 Include_test=0\r\n'
    ")\r\n"
    "\r\n"
    'if exist "%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe" (\r\n'
    '    set "PY_CMD="%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe""\r\n'
    "    goto :esegui\r\n"
    ")\r\n"
    "\r\n"
    'py -3 -c "import sys" >nul 2>nul\r\n'
    "if !ERRORLEVEL! EQU 0 (\r\n"
    '    set "PY_CMD=py -3"\r\n'
    "    goto :esegui\r\n"
    ")\r\n"
    "\r\n"
    "echo.\r\n"
    "echo [ERRORE] Impossibile installare automaticamente Python su questo PC.\r\n"
    "pause\r\n"
    "exit /b 1\r\n"
    "\r\n"
    ":esegui\r\n"
    'echo Avvio programma di installazione guidata...\r\n'
    '!PY_CMD! "%~dp0repost\\strumenti\\installa_dashboard.py"\r\n'
    "if !ERRORLEVEL! NEQ 0 (\r\n"
    "    echo.\r\n"
    "    echo Si e' verificato un problema durante l'installazione.\r\n"
    "    pause\r\n"
    ")\r\n"
)

LEGGIMI_INSTALLER = """===========================================================================
  ENNE ESSE AUTO · MOTOREXPO BRESCIA — INSTALLAZIONE DASHBOARD PARCO AUTO
===========================================================================

ISTRUZIONI RAPIDE (3 PASSAGGI):
1. Estrai tutto il contenuto di questo file ZIP in una cartella qualsiasi.
2. Fai doppio clic su "Installa Dashboard Enne Esse Auto.bat".
3. Nella finestra che si apre, scegli la cartella del tuo PC (ad es. Desktop
   o Documenti) dove vuoi posizionare la cartella "Dashboard Enne Esse Auto".

Al termine dell'installazione (circa 3 secondi):
- Verrà creata l'icona "Dashboard Enne Esse Auto" sul tuo Desktop.
- La Dashboard si aprirà automaticamente nel tuo browser, pronta all'uso!
===========================================================================
"""

FILE_INCLUSI_REPOST = [
    "gestione-foto.html",
    "configurazione.json",
    "Manuale Operativo Concessionario.md",
    "assets/repost.css",
    "assets/style.css",
    "dati/annunci.js",
    "dati/annunci.json",
    "dati/stato_manuale.json",
    "embed/motorexpo-embed.js",
    "strumenti/installa_dashboard.py",
    "strumenti/server_foto.py",
    "strumenti/aggiorna_annunci.py",
    "strumenti/foto_drive.py",
    "strumenti/cloud_github.py",
    "strumenti/avvia_silenzioso.vbs",
    "strumenti/avvia_server_silenzioso.vbs",
    "strumenti/.gh_auth.json",
]


def verifica_token_github(token: str) -> tuple[bool, str]:
    token = (token or "").strip()
    if not token:
        return False, "Token vuoto."
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        "https://api.github.com/repos/Ennesseauto/enneesseauto-vetrina",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "EnneEsseAuto-Setup",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode("utf-8"))
            perms = d.get("permissions") or {}
            if not perms.get("push"):
                return False, "Il token e' valido ma NON ha il permesso di scrittura ('repo' / 'Contents: Read and write')."
            return True, "Token GitHub verificato con successo (lettura e scrittura attive)!"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return (
                False,
                "GitHub ha rifiutato il codice (Errore 401: Non autorizzato).\n"
                "Assicurati di aver incollato il Token generato da GitHub (inizia con 'ghp_' o 'github_pat_')\n"
                "e NON la password del tuo account GitHub!",
            )
        return False, f"Errore HTTP GitHub: {e.code}"
    except Exception as e:
        return False, f"Errore di connessione a GitHub: {e}"


def chiedi_token_grafico():
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog
        import webbrowser

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        apri = messagebox.askyesno(
            "Collegamento Cloud GitHub — Enne Esse Auto",
            "Per permettere al PC del concessionario di inviare le modifiche ('In Arrivo', foto, ecc.) a GitHub,\n"
            "serve un Token di accesso GitHub (inizia con 'ghp_...').\n\n"
            "Vuoi aprire ora la pagina di GitHub per generarlo in 10 secondi?\n"
            "(Ti bastera' spuntare la casella 'repo' e cliccare il pulsante verde 'Generate token' in fondo).",
            parent=root,
        )
        if apri:
            webbrowser.open("https://github.com/settings/tokens/new?description=Dashboard+Enne+Esse+Auto&scopes=repo")

        while True:
            tok = simpledialog.askstring(
                "Incolla il Token GitHub (ghp_...)",
                "Incolla qui il Token generato su GitHub (inizia con ghp_... o github_pat_...):\n"
                "ATTENZIONE: non inserire la password dell'account GitHub, ma il codice ghp_...",
                parent=root,
            )
            if not tok or not tok.strip():
                root.destroy()
                return
            ok, msg = verifica_token_github(tok.strip())
            if ok:
                FILE_AUTH.write_text(json.dumps({"token": tok.strip()}, indent=2) + "\n", encoding="utf-8")
                messagebox.showinfo("Token Verificato!", msg, parent=root)
                root.destroy()
                return
            else:
                riprova = messagebox.askretrycancel("Token non valido", msg, parent=root)
                if not riprova:
                    root.destroy()
                    return
    except Exception as e:
        print(f"Errore finestra grafica: {e}")


def main():
    if "--chiedi-token" in sys.argv:
        chiedi_token_grafico()
    elif len(sys.argv) > 1 and sys.argv[1].strip():
        token_arg = sys.argv[1].strip()
        ok, msg = verifica_token_github(token_arg)
        if ok:
            FILE_AUTH.write_text(json.dumps({"token": token_arg}, indent=2) + "\n", encoding="utf-8")
            print(f"[OK] {msg}")
        else:
            print(f"\n[ERRORE TOKEN] {msg}\n")
            if FILE_AUTH.exists():
                FILE_AUTH.unlink()

    if FILE_AUTH.exists():
        try:
            tok_esistente = json.loads(FILE_AUTH.read_text(encoding="utf-8")).get("token", "")
            ok, _ = verifica_token_github(tok_esistente)
            if not ok:
                print("     [!] Rimossa chiave .gh_auth.json non valida (non era un token ghp_... autorizzato).")
                FILE_AUTH.unlink()
        except Exception:
            FILE_AUTH.unlink()

    prefisso = "Dashboard_EnneEsseAuto_Setup"
    with zipfile.ZipFile(ZIP_DEST, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr(f"{prefisso}/Installa Dashboard Enne Esse Auto.bat", BAT_INSTALLER)
        zf.writestr(f"{prefisso}/Leggimi - Istruzioni Installazione.txt", LEGGIMI_INSTALLER)

        for rel in FILE_INCLUSI_REPOST:
            src = CARTELLA_REPOST / rel
            if src.exists() and src.is_file():
                zf.write(src, f"{prefisso}/repost/{rel}")

        dir_extra = CARTELLA_REPOST / "dati" / "foto-extra"
        if dir_extra.exists():
            for f in dir_extra.rglob("*"):
                if f.is_file():
                    rel_extra = f.relative_to(CARTELLA_REPOST).as_posix()
                    zf.write(f, f"{prefisso}/repost/{rel_extra}")

    # Genera anche il mini-pacchetto di aggiornamento rapido per PC con Dashboard già installata
    zip_patch = CARTELLA_ROOT / "Aggiorna_Collegamento_Cloud.zip"
    bat_patch = BAT_INSTALLER.replace(
        "repost\\strumenti\\installa_dashboard.py",
        "strumenti\\attiva_cloud_patch.py",
    ).replace(
        "AVVIO INSTALLAZIONE DASHBOARD PARCO AUTO",
        "AGGIORNAMENTO COLLEGAMENTO CLOUD GITHUB",
    )
    pref_patch = "Aggiorna_Collegamento_Cloud"
    with zipfile.ZipFile(zip_patch, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zp:
        zp.writestr(f"{pref_patch}/Attiva Collegamento Cloud GitHub.bat", bat_patch)
        for rel_p in (
            "gestione-foto.html",
            "embed/motorexpo-embed.js",
            "strumenti/attiva_cloud_patch.py",
            "strumenti/cloud_github.py",
            "strumenti/server_foto.py",
            "strumenti/foto_drive.py",
            "strumenti/.gh_auth.json",
        ):
            src_p = CARTELLA_REPOST / rel_p
            if src_p.exists() and src_p.is_file():
                zp.write(src_p, f"{pref_patch}/{rel_p}")

    dim_kb = ZIP_DEST.stat().st_size / 1024
    dim_patch_kb = zip_patch.stat().st_size / 1024
    print(f"[OK] Creato pacchetto completo: {ZIP_DEST} ({dim_kb:.1f} KB)")
    print(f"[OK] Creato pacchetto aggiornamento rapido: {zip_patch} ({dim_patch_kb:.1f} KB)")
    if FILE_AUTH.exists():
        print("     [OK] Chiave Cloud GitHub (.gh_auth.json) inclusa in entrambi i pacchetti ZIP!")
    else:
        print("     [i] Chiave Cloud GitHub verrà chiesta automaticamente all'avvio.")


if __name__ == "__main__":
    main()
