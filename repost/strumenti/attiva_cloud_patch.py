#!/usr/bin/env python3
"""
Patch rapida per il PC del concessionario dove la Dashboard è già installata.
1. Rileva automaticamente la cartella esatta della Dashboard attiva su 127.0.0.1:8765
   (e legge le auto che sono appena state impostate "In Arrivo" nella Dashboard!).
2. Recupera il Token GitHub già salvato (o lo chiede se mancante).
3. Riavvia il processo server_foto.py in background (che era rimasto fermo alla vecchia versione in RAM)
   e invia SUBITO a GitHub le auto "In Arrivo".
"""
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def verifica_token(token: str) -> tuple[bool, str]:
    token = (token or "").strip()
    if not token:
        return False, "Token vuoto."
    req = urllib.request.Request(
        "https://api.github.com/repos/Ennesseauto/enneesseauto-vetrina",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "EnneEsseAuto-Patch",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode("utf-8"))
            if (d.get("permissions") or {}).get("push"):
                return True, "Token GitHub valido e autorizzato alla scrittura!"
            return False, "Il token non ha il permesso 'repo' (scrittura)."
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return (
                False,
                "Codice rifiutato da GitHub (Errore 401).\n\n"
                "Attenzione: devi incollare il Token che inizia con 'ghp_' "
                "e NON la password dell'account GitHub!",
            )
        return False, f"Errore HTTP GitHub: {e.code}"
    except Exception as e:
        return False, f"Errore di rete: {e}"


def leggi_stato_server_attivo() -> dict | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/api/stato", timeout=3) as r:
            if r.status == 200:
                return json.loads(r.read().decode("utf-8"))
    except Exception:
        pass
    return None


def ferma_vecchio_server():
    try:
        req = urllib.request.Request("http://127.0.0.1:8765/api/spegnimento", data=b"{}", method="POST")
        urllib.request.urlopen(req, timeout=2).read()
        time.sleep(0.5)
    except Exception:
        pass
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }",
            ],
            capture_output=True,
            timeout=6,
        )
        time.sleep(0.6)
    except Exception:
        pass


def trova_cartella_dashboard(stato_live: dict | None) -> Path | None:
    # 1. Prende la cartella esatta dal server attivo su 127.0.0.1:8765!
    if stato_live and stato_live.get("percorsoDrive"):
        p_drive = Path(stato_live["percorsoDrive"])
        if p_drive.parent.exists() and (p_drive.parent / "repost" / "gestione-foto.html").exists():
            return p_drive.parent

    home = Path.home()
    candidati = [
        home / "Desktop" / "Dashboard Enne Esse Auto",
        home / "OneDrive" / "Desktop" / "Dashboard Enne Esse Auto",
        home / "Documents" / "Dashboard Enne Esse Auto",
        home / "Documenti" / "Dashboard Enne Esse Auto",
        home / "OneDrive" / "Documents" / "Dashboard Enne Esse Auto",
        home / "OneDrive" / "Documenti" / "Dashboard Enne Esse Auto",
        home / "Dashboard Enne Esse Auto",
        Path("C:/Dashboard Enne Esse Auto"),
    ]
    # Cerca anche se c'è una cartella dove .gh_auth.json è già stato scritto
    for c in candidati:
        if (c / "repost" / "strumenti" / ".gh_auth.json").exists():
            return c
    for c in candidati:
        if (c / "repost" / "gestione-foto.html").exists():
            return c

    for desk in [home / "Desktop", home / "OneDrive" / "Desktop"]:
        lnk = desk / "Dashboard Enne Esse Auto.lnk"
        if lnk.exists():
            try:
                ps = f"(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}').WorkingDirectory"
                r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
                wd = (r.stdout or "").strip()
                if wd and (Path(wd) / "repost" / "gestione-foto.html").exists():
                    return Path(wd)
            except Exception:
                pass

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(
            "Seleziona la cartella della Dashboard",
            "Seleziona la cartella 'Dashboard Enne Esse Auto' installata su questo PC.",
            parent=root,
        )
        scelta = filedialog.askdirectory(
            title="Seleziona la cartella 'Dashboard Enne Esse Auto' installata sul PC",
            initialdir=str(home),
            mustexist=True,
            parent=root,
        )
        root.destroy()
        if scelta:
            p = Path(scelta)
            if (p / "repost" / "gestione-foto.html").exists():
                return p
            if (p / "gestione-foto.html").exists():
                return p.parent
            if (p / "Dashboard Enne Esse Auto" / "repost" / "gestione-foto.html").exists():
                return p / "Dashboard Enne Esse Auto"
    except Exception:
        pass
    return None


def main():
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    import webbrowser

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    stato_live = leggi_stato_server_attivo()
    cartella_dash = trova_cartella_dashboard(stato_live)
    if not cartella_dash:
        messagebox.showerror(
            "Cartella non trovata",
            "Non e' stata trovata la cartella 'Dashboard Enne Esse Auto' su questo PC.",
            parent=root,
        )
        root.destroy()
        sys.exit(1)

    print(f"[OK] Trovata Dashboard attiva in: {cartella_dash}")
    strumenti_dest = cartella_dash / "repost" / "strumenti"
    file_auth_dest = strumenti_dest / ".gh_auth.json"

    # Cerca il token già salvato in precedenza (in tutte le possibili cartelle o nello ZIP)
    mio_dir = Path(__file__).resolve().parent
    token_valido = ""
    possibili_auth = [
        file_auth_dest,
        mio_dir / ".gh_auth.json",
        Path.home() / "Desktop" / "Dashboard Enne Esse Auto" / "repost" / "strumenti" / ".gh_auth.json",
        Path.home() / "OneDrive" / "Desktop" / "Dashboard Enne Esse Auto" / "repost" / "strumenti" / ".gh_auth.json",
        Path.home() / "Documents" / "Dashboard Enne Esse Auto" / "repost" / "strumenti" / ".gh_auth.json",
    ]
    for p_auth in possibili_auth:
        if p_auth.exists():
            try:
                cand = json.loads(p_auth.read_text(encoding="utf-8")).get("token", "").strip()
                ok, _ = verifica_token(cand)
                if ok:
                    token_valido = cand
                    break
            except Exception:
                pass

    while not token_valido:
        apri = messagebox.askyesno(
            "Genera Token GitHub (ghp_...)",
            "Per collegare questa Dashboard al sito enneesseauto.it serve il codice Token di GitHub (inizia con 'ghp_...').\n\n"
            "Hai gia' copiato il codice 'ghp_...' negli appunti?\n"
            "- Clicca SI se ce l'hai gia' pronto da incollare.\n"
            "- Clicca NO per aprire la pagina di GitHub dove generarlo.",
            parent=root,
        )
        if not apri:
            webbrowser.open("https://github.com/settings/tokens/new?description=Dashboard+Enne+Esse+Auto&scopes=repo")

        tok = simpledialog.askstring(
            "Incolla il Token GitHub (ghp_...)",
            "Incolla qui il Token generato su GitHub (inizia con ghp_...):\n"
            "(NON inserire la password dell'account GitHub, ma il Token ghp_...)",
            parent=root,
        )
        if not tok or not tok.strip():
            root.destroy()
            sys.exit(0)
        ok, msg = verifica_token(tok.strip())
        if ok:
            token_valido = tok.strip()
        else:
            if not messagebox.askretrycancel("Token non valido", msg, parent=root):
                root.destroy()
                sys.exit(1)

    # 1. Ferma il vecchio server_foto.py in background (che aveva in RAM la vecchia versione senza Cloud)
    print("Riavvio del motore Dashboard in background con supporto Cloud attivo...")
    ferma_vecchio_server()

    # 2. Aggiorna gestione-foto.html, foto_drive.py, cloud_github.py, server_foto.py e motorexpo-embed.js nella cartella installata
    for nome_f in ("cloud_github.py", "server_foto.py", "foto_drive.py"):
        src_f = mio_dir / nome_f
        if src_f.exists():
            shutil.copy2(src_f, strumenti_dest / nome_f)

    repost_patch_dir = mio_dir.parent
    html_src = repost_patch_dir / "gestione-foto.html"
    if html_src.exists():
        shutil.copy2(html_src, cartella_dash / "repost" / "gestione-foto.html")
    embed_src = repost_patch_dir / "embed" / "motorexpo-embed.js"
    if embed_src.exists():
        (cartella_dash / "repost" / "embed").mkdir(parents=True, exist_ok=True)
        shutil.copy2(embed_src, cartella_dash / "repost" / "embed" / "motorexpo-embed.js")

    # 3. Salva il token verificato nella cartella attiva
    file_auth_dest.write_text(json.dumps({"token": token_valido}, indent=2) + "\n", encoding="utf-8")

    # 4. Se il server attivo aveva auto in memoria (es. appena messe "In Arrivo"), assicurati che siano salvate
    file_stato_man = cartella_dash / "repost" / "dati" / "stato_manuale.json"
    file_dati_js = cartella_dash / "repost" / "dati" / "annunci.js"
    file_dati_json = cartella_dash / "repost" / "dati" / "annunci.json"

    auto_in_arrivo_nomi = []
    try:
        stato_man = json.loads(file_stato_man.read_text(encoding="utf-8")) if file_stato_man.exists() else {"stati": {}, "copertine": {}, "foto_originali_as24": {}}
        if stato_live and isinstance(stato_live.get("annunci"), list):
            for a in stato_live["annunci"]:
                if a.get("id") and a.get("stato"):
                    stato_man.setdefault("stati", {})[a["id"]] = a["stato"]
        file_stato_man.write_text(json.dumps(stato_man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        if file_dati_js.exists():
            testo = file_dati_js.read_text(encoding="utf-8")
            inizio = testo.find("{")
            fine = testo.rfind("}")
            if inizio != -1 and fine != -1:
                dati = json.loads(testo[inizio : fine + 1])
                for a in dati.get("annunci", []):
                    st = stato_man.get("stati", {}).get(a["id"], a.get("stato", "salone"))
                    a["stato"] = st
                    if st == "arrivo":
                        auto_in_arrivo_nomi.append(f"• {a.get('marca', '')} {a.get('modello', '')}")
                file_dati_js.write_text(
                    "window.REPOST_DATI = " + json.dumps(dati, ensure_ascii=True, separators=(",", ":")) + ";\n",
                    encoding="utf-8",
                )
                file_dati_json.write_text(
                    json.dumps(dati, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
    except Exception as e:
        print(f"Avviso lettura stato: {e}")

    # 5. Invia SUBITO a GitHub e riavvia il nuovo server_foto.py in background
    print("Invio immediato a GitHub in corso...")
    sys.path.insert(0, str(strumenti_dest))
    try:
        import cloud_github  # type: ignore

        cloud_github.CARTELLA_ROOT = cartella_dash
        cloud_github.CARTELLA_REPOST = cartella_dash / "repost"
        cloud_github.FILE_DATI_JS = file_dati_js
        cloud_github.FILE_DATI_JSON = file_dati_json
        cloud_github.FILE_AUTH = file_auth_dest

        cloud_github._push_via_api_https(token_valido, "Sincronizzazione auto In Arrivo da Dashboard concessionario")
        cloud_github._svuota_cache_cdn()

        # Riavvia il server aggiornato in background direttamente con sys.executable
        py_exe = sys.executable
        vbs = strumenti_dest / "avvia_server_silenzioso.vbs"
        vbs.write_text(
            "' Avvia il server locale della Dashboard (server_foto.py) in background senza finestra nera\r\n"
            'Set fso = CreateObject("Scripting.FileSystemObject")\r\n'
            'Set shell = CreateObject("WScript.Shell")\r\n'
            "cartellaStrumenti = fso.GetParentFolderName(WScript.ScriptFullName)\r\n"
            "cartellaRepost = fso.GetParentFolderName(cartellaStrumenti)\r\n"
            'fileLog = cartellaRepost & "\\dati\\server_foto.log"\r\n'
            f'pyExe = "{py_exe}"\r\n'
            'comando = "cmd /c cd /d """ & cartellaRepost & """ && set PYTHONIOENCODING=utf-8 && (""" & pyExe & """ ""strumenti\\server_foto.py"" --no-browser > """ & fileLog & """ 2>&1 || python ""strumenti\\server_foto.py"" --no-browser >> """ & fileLog & """ 2>&1 || py -3 ""strumenti\\server_foto.py"" --no-browser >> """ & fileLog & """ 2>&1)"\r\n'
            "shell.Run comando, 0, False\r\n",
            encoding="utf-8",
        )
        subprocess.Popen(
            [py_exe, str(strumenti_dest / "server_foto.py"), "--no-browser"],
            cwd=str(cartella_dash / "repost"),
            creationflags=0x08000000 if sys.platform.startswith("win") else 0,
        )
        for _ in range(15):
            if leggi_stato_server_attivo() is not None:
                break
            time.sleep(0.3)

        webbrowser.open("http://127.0.0.1:8765/repost/gestione-foto.html")

        elenco_txt = "\n".join(auto_in_arrivo_nomi) if auto_in_arrivo_nomi else "(Nessuna auto attualmente segnata 'In Arrivo' in questa cartella)"
        messagebox.showinfo(
            "Sincronizzazione Cloud Completata!",
            f"Motore Dashboard riavviato e sincronizzato con GitHub!\n\n"
            f"Cartella attiva:\n{cartella_dash}\n\n"
            f"Auto 'In Arrivo' appena inviate al sito ({len(auto_in_arrivo_nomi)}):\n{elenco_txt}\n\n"
            "Da questo momento ogni clic nella Dashboard aggiorna enneesseauto.it in 3-5 secondi!",
            parent=root,
        )
    except Exception as e:
        messagebox.showerror(
            "Errore durante l'invio a GitHub",
            f"Si e' verificato questo errore durante l'invio a GitHub:\n\n{e}",
            parent=root,
        )
    root.destroy()


if __name__ == "__main__":
    main()
