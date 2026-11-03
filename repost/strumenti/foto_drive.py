#!/usr/bin/env python3
"""
REPOST AUTOSCOUT24 — Gestione Cartella Google Drive, Foto Integrative e Stato Auto

Gestisce in modo bidirezionale (sia da Cartella Google Drive sia da Dashboard):
1. Stato di ogni auto:
   - "salone"  -> Cartella "1 - Auto in vendita"
   - "arrivo"  -> Cartella "2 - Vetture in arrivo"
   - "venduta" -> Cartella "3 - Vendute (archivio)/<Anno>/<Mese>"
2. Selezione della foto di copertina (tramite file "copertina.*" nel Drive
   oppure scelta con un clic dalla Dashboard).
3. Integrazione delle 40 foto mancanti con filtro anti-doppioni automatico
   (impronta visiva dHash a 64 bit rispetto alle foto di AutoScout24) e
   conversione nelle 4 misure WebP (250x188, 720x540, 1280x960, 1920x1080)
   con rimozione dei metadati GPS/EXIF.
"""
import hashlib
import io
import json
import os
import re
import shutil
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageOps
    PILLOW_DISPONIBILE = True
except ImportError:
    PILLOW_DISPONIBILE = False

CARTELLA_REPOST = Path(__file__).resolve().parent.parent
FILE_CONFIG = CARTELLA_REPOST / "configurazione.json"
CARTELLA_EXTRA_WEB = CARTELLA_REPOST / "dati" / "foto-extra"
FILE_STATO_MANUALE = CARTELLA_REPOST / "dati" / "stato_manuale.json"

ESTENSIONI_FOTO = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MISURE_WEBP = {
    "250x188": (250, 188, 80),
    "720x540": (720, 540, 82),
    "1280x960": (1280, 960, 84),
    "1920x1080": (1920, 1080, 85),
}
SOGLIA_HAMMING_DOPPIONE = 6

MESI_IT = [
    "", "01 - Gennaio", "02 - Febbraio", "03 - Marzo", "04 - Aprile",
    "05 - Maggio", "06 - Giugno", "07 - Luglio", "08 - Agosto",
    "09 - Settembre", "10 - Ottobre", "11 - Novembre", "12 - Dicembre"
]

RE_RIF = re.compile(r"\[rif\.\s*([a-f0-9]{8})\]", re.I)


def carica_configurazione():
    predefinita = {
        "concessionario_slug": "enne-esse-auto-motorexpo-brescia",
        "cartella_drive": "foto-drive",
        "contatti_propri": {
            "telefono": "+39 030 0985415",
            "whatsapp": "+39 348 9379494"
        },
        "controlli_prima_di_rimuovere": 2,
        "soglia_allarme_sparizione": 0.4,
        "qualita_webp": 84
    }
    if FILE_CONFIG.exists():
        try:
            letto = json.loads(FILE_CONFIG.read_text(encoding="utf-8"))
            predefinita.update(letto)
        except (OSError, ValueError):
            pass
    else:
        try:
            FILE_CONFIG.write_text(json.dumps(predefinita, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError:
            pass
    return predefinita


def percorso_drive(config=None):
    config = config or carica_configurazione()
    p = Path(config.get("cartella_drive") or "foto-drive")
    if not p.is_absolute():
        p = CARTELLA_REPOST / p
    return p


def carica_stato_manuale() -> dict:
    """Legge repost/dati/stato_manuale.json che conserva:
    - stati: {id_auto: "salone" | "arrivo" | "venduta"}
    - copertine: {id_auto: url_o_percorso_foto_copertina}
    - foto_originali_as24: {id_auto: [lista_url_as24]}
    """
    base = {"stati": {}, "copertine": {}, "foto_originali_as24": {}, "homepage": {}, "ordine_sito": "autoscout"}
    if FILE_STATO_MANUALE.exists():
        try:
            letto = json.loads(FILE_STATO_MANUALE.read_text(encoding="utf-8"))
            for k in ("stati", "copertine", "foto_originali_as24", "homepage"):
                if isinstance(letto.get(k), dict):
                    base[k].update(letto[k])
            if isinstance(letto.get("ordine_sito"), str) and letto["ordine_sito"]:
                base["ordine_sito"] = letto["ordine_sito"]
        except (OSError, ValueError):
            pass
    return base


def salva_stato_manuale(stato: dict):
    FILE_STATO_MANUALE.parent.mkdir(parents=True, exist_ok=True)
    try:
        FILE_STATO_MANUALE.write_text(
            json.dumps(stato, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Utilità per nomi file e ordinamento naturale
# ---------------------------------------------------------------------------
def pulisci_nome_cartella(testo):
    pulito = re.sub(r'[<>:"/\\|?*]+', " ", str(testo or ""))
    return re.sub(r"\s+", " ", pulito).strip().rstrip(".")


def chiave_naturale(percorso: Path):
    nome = percorso.stem.lower().strip()
    is_copertina = 0 if nome.startswith("copertina") else 1
    parti = [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", percorso.name)]
    return (is_copertina, parti)


def nome_cartella_auto(annuncio, num_as24, num_extra, stato="salone"):
    marca = annuncio.get("marca") or "Auto"
    modello = annuncio.get("modello") or ""
    colore = annuncio.get("colore") or ""
    imm = (annuncio.get("immatricolazione") or "")[:4]
    km = annuncio.get("km")
    km_str = f"{km:,} km".replace(",", ".") if isinstance(km, int) else ""

    totale = num_as24 + num_extra
    if num_extra > 0:
        stato_foto = f"({totale} foto, +{num_extra} extra)"
    elif num_as24 < 20:
        stato_foto = f"({num_as24} foto su AS24 - DA COMPLETARE)"
    else:
        stato_foto = f"({num_as24} foto)"

    prefisso = "[IN ARRIVO] " if stato == "arrivo" else ""
    rif = annuncio["id"][:8]
    pezzi = [f"{marca} {modello}".strip(), colore, imm, km_str]
    base = " - ".join(p for p in pezzi if p)
    return pulisci_nome_cartella(f"{prefisso}{base} {stato_foto} [rif. {rif}]")


# ---------------------------------------------------------------------------
# Impronta visiva (dHash 64-bit) e conversione WebP
# ---------------------------------------------------------------------------
def calcola_dhash(img: "Image.Image") -> int:
    grigia = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(grigia.getdata())
    bits = 0
    for riga in range(8):
        offset = riga * 9
        for col in range(8):
            bits = (bits << 1) | (1 if px[offset + col] > px[offset + col + 1] else 0)
    return bits


def distanza_hamming(h1: int, h2: int) -> int:
    return (h1 ^ h2).bit_count()


def scarica_dhash_as24(url_base: str, cache_as24: dict) -> int | None:
    if not PILLOW_DISPONIBILE or not url_base:
        return None
    if url_base in cache_as24:
        return cache_as24[url_base]
    url_mini = f"{url_base}/250x188.webp"
    try:
        req = urllib.request.Request(url_mini, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            dati = resp.read()
        with Image.open(io.BytesIO(dati)) as img:
            h = calcola_dhash(img)
            cache_as24[url_base] = h
            return h
    except Exception:
        return None


def ridimensiona_e_salva_webp(img: "Image.Image", cartella_dest: Path):
    cartella_dest.mkdir(parents=True, exist_ok=True)
    img_dritta = ImageOps.exif_transpose(img)
    if img_dritta.mode not in ("RGB", "L"):
        sfondo = Image.new("RGB", img_dritta.size, (255, 255, 255))
        if "A" in img_dritta.getbands():
            sfondo.paste(img_dritta, mask=img_dritta.split()[-1])
        else:
            sfondo.paste(img_dritta)
        img_rgb = sfondo
    else:
        img_rgb = img_dritta.convert("RGB")

    orig_w, orig_h = img_rgb.size
    for nome_misura, (max_w, max_h, qualita) in MISURE_WEBP.items():
        dest = cartella_dest / f"{nome_misura}.webp"
        scala = min(max_w / max(orig_w, 1), max_h / max(orig_h, 1), 1.0)
        nuova_w = max(1, round(orig_w * scala))
        nuova_h = max(1, round(orig_h * scala))
        if (nuova_w, nuova_h) != (orig_w, orig_h):
            copia = img_rgb.resize((nuova_w, nuova_h), Image.Resampling.LANCZOS)
        else:
            copia = img_rgb
        copia.save(dest, format="WEBP", quality=qualita, method=4)


TESTO_LEGGIMI = """===========================================================================
  ENNE ESSE AUTO — GUIDA RAPIDA ALLA CARTELLA FOTO (GOOGLE DRIVE)
===========================================================================

STRUTTURA DELLE CARTELLE:
  1 - Auto in vendita     -> Auto presenti in salone e visibili sul sito
  2 - Vetture in arrivo   -> Auto mostrate nella sezione "In Arrivo" del sito
  3 - Vendute (archivio)  -> Auto vendute (tolte dal sito e archiviate per mese)

COME AGGIUNGERE LE FOTO MANCANTI (ANCHE TUTTE LE 50 INSIEME!)
---------------------------------------------------------------------------
1. Apri la cartella dell'auto (quelle bloccate da AutoScout24 a 10-15 foto
   hanno la scritta "DA COMPLETARE" nel nome e sono elencate nel file
   "_RIEPILOGO FOTO MANCANTI.txt").
2. Trascina dentro tutte le 50 foto dell'auto: il sistema riconosce da solo
   le 10-15 già presenti su AutoScout24, scarta i doppioni, rimuove i dati
   GPS del telefono e pubblica solo le foto mancanti in formato WebP veloce.
3. Per scegliere la prima foto (copertina): chiama il file "copertina.jpg"
   oppure clicca su "Imposta Copertina" dalla Dashboard locale.
4. Per spostare un'auto in "In Arrivo" o "Venduta": puoi farlo con un clic
   dalla Dashboard locale oppure spostando la sua cartella tra le 3 cartelle.
===========================================================================
"""


def scrivi_riepilogo_mancanti(cartella_vendita: Path, annunci: list, conteggi_extra: dict):
    da_completare = []
    complete = []
    for a in annunci:
        if a.get("stato") == "venduta":
            continue
        n_extra = conteggi_extra.get(a["id"], 0)
        n_tot = len(a["foto"])
        n_as24 = a.get("fotoAs24", max(0, n_tot - n_extra))
        tag_stato = "[IN ARRIVO] " if a.get("stato") == "arrivo" else ""
        riga = f"  - {tag_stato}{a.get('marca')} {a.get('modello')} ({(a.get('immatricolazione') or '')[:4]}) [rif. {a['id'][:8]}] -> {n_tot} foto sul sito ({n_as24} da AS24 + {n_extra} extra)"
        if n_tot < 30:
            da_completare.append(riga)
        else:
            complete.append(riga)

    righe = [
        "===========================================================================",
        f"  STATO FOTO VETRINA — Aggiornato il {datetime.now().strftime('%d/%m/%Y alle %H:%M')}",
        "===========================================================================",
        "",
        f"AUTO CON POCHE FOTO SU AUTOSCOUT24 DA COMPLETARE ({len(da_completare)}):",
        "(Apri la cartella corrispondente e trascina dentro tutte le foto dell'auto)",
        ""
    ]
    righe.extend(da_completare if da_completare else ["  Nessuna! Tutte le auto hanno già un servizio fotografico completo."])
    righe.extend([
        "",
        "---------------------------------------------------------------------------",
        f"AUTO GIÀ COMPLETE ({len(complete)}):",
        ""
    ])
    righe.extend(complete)
    righe.append("")

    try:
        (cartella_vendita / "_RIEPILOGO FOTO MANCANTI.txt").write_text("\n".join(righe), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Elaborazione foto di una singola auto
# ---------------------------------------------------------------------------
def processa_foto_auto(annuncio: dict, cartella_auto: Path, foto_as24_orig: list[str], copertina_scelta: str | None) -> tuple[list[str], int, int]:
    id_auto = annuncio["id"]
    foto_as24 = [f for f in foto_as24_orig if isinstance(f, str) and not f.startswith("foto-extra/")]
    num_as24 = len(foto_as24)

    file_cliente = []
    if cartella_auto and cartella_auto.exists():
        file_cliente = sorted(
            [p for p in cartella_auto.iterdir()
             if p.is_file() and p.suffix.lower() in ESTENSIONI_FOTO and not p.name.startswith(".")],
            key=chiave_naturale
        )

    cartella_web_auto = CARTELLA_EXTRA_WEB / id_auto
    file_manifest = cartella_web_auto / ".manifest.json"

    if not file_cliente:
        # In modalità Cloud (GitHub Actions), i file raw non sono nel repo ma le miniature WebP
        # già ottimizzate sono presenti in repost/dati/foto-extra/<id_auto>/.manifest.json: le preserviamo!
        if os.environ.get("GITHUB_ACTIONS") == "true" and file_manifest.exists():
            try:
                manifest_cloud = json.loads(file_manifest.read_text(encoding="utf-8"))
                proc_cloud = manifest_cloud.get("file_processati") or {}
                foto_cop_cloud = []
                foto_ext_cloud = []
                for nome_f, meta in proc_cloud.items():
                    slug_c = meta.get("slug")
                    if not meta.get("doppione") and slug_c and (cartella_web_auto / slug_c / "1280x960.webp").exists():
                        rel = f"foto-extra/{id_auto}/{slug_c}"
                        if Path(nome_f).stem.lower().strip().startswith("copertina"):
                            foto_cop_cloud.append(rel)
                        else:
                            foto_ext_cloud.append(rel)
                lista_finale = foto_cop_cloud + list(foto_as24) + foto_ext_cloud
                if copertina_scelta and copertina_scelta in lista_finale:
                    lista_finale.remove(copertina_scelta)
                    lista_finale.insert(0, copertina_scelta)
                return lista_finale, num_as24, len(foto_cop_cloud) + len(foto_ext_cloud)
            except Exception:
                pass

        if cartella_web_auto.exists():
            shutil.rmtree(cartella_web_auto, ignore_errors=True)
        lista_finale = list(foto_as24)
        if copertina_scelta and copertina_scelta in lista_finale:
            lista_finale.remove(copertina_scelta)
            lista_finale.insert(0, copertina_scelta)
        return lista_finale, num_as24, 0

    if not PILLOW_DISPONIBILE:
        return foto_as24, num_as24, 0

    cartella_web_auto.mkdir(parents=True, exist_ok=True)
    manifest = {"as24_hashes": {}, "file_processati": {}}
    if file_manifest.exists():
        try:
            manifest.update(json.loads(file_manifest.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    cache_as24 = manifest.get("as24_hashes") or {}
    hash_as24 = []
    for url_base in foto_as24:
        h = scarica_dhash_as24(url_base, cache_as24)
        if h is not None:
            hash_as24.append((url_base, h))

    vecchi_proc = manifest.get("file_processati") or {}
    nuovi_proc = {}
    foto_copertina = []
    foto_extra = []
    slug_attivi = set()

    for idx, file_img in enumerate(file_cliente, 1):
        stat = file_img.stat()
        chiave_file = file_img.name
        firma_file = f"{stat.st_size}_{int(stat.st_mtime)}"
        is_copertina = file_img.stem.lower().strip().startswith("copertina")

        digest = hashlib.sha1(file_img.name.encode("utf-8")).hexdigest()[:8]
        slug = f"{idx:02d}-{digest}"

        info_prec = vecchi_proc.get(chiave_file)
        cartella_slot = cartella_web_auto / slug

        if (info_prec
                and info_prec.get("firma") == firma_file
                and info_prec.get("dhash") is not None):
            dhash_img = info_prec["dhash"]
            vecchio_slug = info_prec.get("slug")
            if not is_copertina and any(distanza_hamming(dhash_img, h) <= SOGLIA_HAMMING_DOPPIONE for _, h in hash_as24):
                nuovi_proc[chiave_file] = {"firma": firma_file, "dhash": dhash_img, "doppione": True}
                continue
            if vecchio_slug and (cartella_web_auto / vecchio_slug / "1280x960.webp").exists():
                slug = vecchio_slug
                cartella_slot = cartella_web_auto / slug
            else:
                try:
                    with Image.open(file_img) as img:
                        ridimensiona_e_salva_webp(img, cartella_slot)
                except Exception:
                    continue
        else:
            try:
                with Image.open(file_img) as img:
                    img_dritta = ImageOps.exif_transpose(img)
                    dhash_img = calcola_dhash(img_dritta)
                    if not is_copertina and any(distanza_hamming(dhash_img, h) <= SOGLIA_HAMMING_DOPPIONE for _, h in hash_as24):
                        nuovi_proc[chiave_file] = {"firma": firma_file, "dhash": dhash_img, "doppione": True}
                        continue
                    ridimensiona_e_salva_webp(img_dritta, cartella_slot)
            except Exception as e:
                print(f"    [!] Foto ignorata ({file_img.name}): {e}")
                continue

        slug_attivi.add(slug)
        nuovi_proc[chiave_file] = {"firma": firma_file, "dhash": dhash_img, "slug": slug, "doppione": False}
        percorso_rel = f"foto-extra/{id_auto}/{slug}"

        if is_copertina:
            foto_copertina.append((percorso_rel, dhash_img))
        else:
            foto_extra.append(percorso_rel)

    for sub in cartella_web_auto.iterdir():
        if sub.is_dir() and sub.name not in slug_attivi:
            shutil.rmtree(sub, ignore_errors=True)

    foto_as24_filtrate = list(foto_as24)
    for _, h_cop in foto_copertina:
        for url_b, h_as in hash_as24:
            if distanza_hamming(h_cop, h_as) <= SOGLIA_HAMMING_DOPPIONE and url_b in foto_as24_filtrate:
                foto_as24_filtrate.remove(url_b)

    manifest["as24_hashes"] = cache_as24
    manifest["file_processati"] = nuovi_proc
    try:
        file_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass

    lista_finale = [p for p, _ in foto_copertina] + foto_as24_filtrate + foto_extra
    if copertina_scelta and copertina_scelta in lista_finale:
        lista_finale.remove(copertina_scelta)
        lista_finale.insert(0, copertina_scelta)

    num_extra_effettive = len(foto_copertina) + len(foto_extra)
    return lista_finale, num_as24, num_extra_effettive


# ---------------------------------------------------------------------------
# Ricerca cartella fisica di un'auto nelle 3 sezioni del Drive
# ---------------------------------------------------------------------------
def mappa_tutte_cartelle_drive(dir_drive: Path) -> dict[str, tuple[Path, str]]:
    """Cerca tutte le cartelle con [rif. xxxxxxxx] in:
    - 1 - Auto in vendita        -> stato 'salone'
    - 2 - Vetture in arrivo      -> stato 'arrivo'
    - 3 - Vendute (archivio)     -> stato 'venduta' (o vecchio '2 - Vendute (archivio)')
    Restituisce {rif: (percorso_cartella, stato_rilevato)}
    """
    mappa = {}
    dir_vendita = dir_drive / "1 - Auto in vendita"
    dir_arrivo = dir_drive / "2 - Vetture in arrivo"
    dir_vendute = dir_drive / "3 - Vendute (archivio)"
    dir_vendute_legacy = dir_drive / "2 - Vendute (archivio)"

    # Migrazione indolore se esisteva "2 - Vendute (archivio)"
    if dir_vendute_legacy.exists() and not dir_vendute.exists():
        try:
            dir_vendute_legacy.rename(dir_vendute)
        except OSError:
            pass

    for cartella_base, stato_c in ((dir_vendita, "salone"), (dir_arrivo, "arrivo")):
        if cartella_base.exists():
            for sub in cartella_base.iterdir():
                if sub.is_dir():
                    m = RE_RIF.search(sub.name)
                    if m:
                        mappa[m.group(1).lower()] = (sub, stato_c)

    if dir_vendute.exists():
        for sub in dir_vendute.rglob("*"):
            if sub.is_dir():
                m = RE_RIF.search(sub.name)
                if m and m.group(1).lower() not in mappa:
                    mappa[m.group(1).lower()] = (sub, "venduta")

    return mappa


def sposta_cartella_stato(cartella_corrente: Path, nuovo_stato: str, annuncio: dict, n_as24: int, n_extra: int, dir_drive: Path) -> Path:
    """Sposta la cartella dell'auto nella directory corrispondente a nuovo_stato."""
    rif = annuncio["id"][:8].lower()
    adesso = datetime.now()
    if nuovo_stato == "arrivo":
        dest_dir = dir_drive / "2 - Vetture in arrivo"
        dest_dir.mkdir(parents=True, exist_ok=True)
        nuovo_nome = nome_cartella_auto(annuncio, n_as24, n_extra, "arrivo")
    elif nuovo_stato == "venduta":
        dest_dir = dir_drive / "3 - Vendute (archivio)" / str(adesso.year) / MESI_IT[adesso.month]
        dest_dir.mkdir(parents=True, exist_ok=True)
        marca = annuncio.get("marca") or "Auto"
        modello = annuncio.get("modello") or ""
        colore = annuncio.get("colore") or ""
        imm = (annuncio.get("immatricolazione") or "")[:4]
        base = " - ".join(p for p in [f"{marca} {modello}".strip(), colore, imm] if p)
        nuovo_nome = pulisci_nome_cartella(f"{base} - venduta il {adesso.strftime('%d-%m-%Y')} [rif. {rif}]")
    else:
        dest_dir = dir_drive / "1 - Auto in vendita"
        dest_dir.mkdir(parents=True, exist_ok=True)
        nuovo_nome = nome_cartella_auto(annuncio, n_as24, n_extra, "salone")

    dest_path = dest_dir / nuovo_nome
    if cartella_corrente.resolve() == dest_path.resolve():
        return cartella_corrente
    if dest_path.exists():
        shutil.rmtree(dest_path, ignore_errors=True)
    try:
        shutil.move(str(cartella_corrente), str(dest_path))
        return dest_path
    except OSError:
        return cartella_corrente


# ---------------------------------------------------------------------------
# Sincronizzazione dell'intera cartella Google Drive (Salone + In Arrivo + Vendute)
# ---------------------------------------------------------------------------
def sincronizza_cartella_drive(annunci: list, dir_drive: Path = None) -> dict:
    dir_drive = dir_drive or percorso_drive()
    cartella_vendita = dir_drive / "1 - Auto in vendita"
    cartella_arrivo = dir_drive / "2 - Vetture in arrivo"
    cartella_vendute = dir_drive / "3 - Vendute (archivio)"

    mappa_cartelle = mappa_tutte_cartelle_drive(dir_drive)
    cartella_vendita.mkdir(parents=True, exist_ok=True)
    cartella_arrivo.mkdir(parents=True, exist_ok=True)
    cartella_vendute.mkdir(parents=True, exist_ok=True)
    CARTELLA_EXTRA_WEB.mkdir(parents=True, exist_ok=True)

    file_leggimi = dir_drive / "Come caricare le foto (leggimi).txt"
    try:
        file_leggimi.write_text(TESTO_LEGGIMI, encoding="utf-8")
    except OSError:
        pass

    stato_man = carica_stato_manuale()
    stati_salvati = stato_man["stati"]
    copertine_salvate = stato_man["copertine"]
    foto_orig_salvate = stato_man["foto_originali_as24"]
    homepage_salvate = stato_man["homepage"]

    rif_attivi = set()
    conteggi_extra = {}
    totale_extra_aggiunte = 0
    auto_arricchite = 0
    conta_salone = 0
    conta_arrivo = 0
    conta_vendute = 0

    for a in annunci:
        id_auto = a["id"]
        rif = id_auto[:8].lower()
        rif_attivi.add(rif)

        # Conserva l'elenco originale delle foto di AutoScout24
        foto_correnti_as24 = [f for f in a.get("foto", []) if isinstance(f, str) and not f.startswith("foto-extra/")]
        if foto_correnti_as24:
            foto_orig_salvate[id_auto] = foto_correnti_as24
        else:
            foto_correnti_as24 = foto_orig_salvate.get(id_auto, [])

        info_cartella = mappa_cartelle.get(rif)
        stato_auto = stati_salvati.get(id_auto)

        if info_cartella is not None:
            cartella_auto, stato_fisico = info_cartella
            stato_prec_disco = None
            file_info_prec = cartella_auto / ".info_auto.json"
            if file_info_prec.exists():
                try:
                    stato_prec_disco = json.loads(file_info_prec.read_text(encoding="utf-8")).get("stato")
                except Exception:
                    pass
            # Se il cliente ha spostato manualmente la cartella su PC/Drive rispetto all'ultimo stato su disco
            if stato_auto is None or (stato_prec_disco and stato_fisico != stato_prec_disco and stato_auto == stato_prec_disco):
                stato_auto = stato_fisico
                stati_salvati[id_auto] = stato_auto
        else:
            stato_auto = stato_auto or "salone"
            stati_salvati[id_auto] = stato_auto
            dir_base = cartella_arrivo if stato_auto == "arrivo" else cartella_vendita
            nome_iniziale = nome_cartella_auto(a, len(foto_correnti_as24), 0, stato_auto)
            cartella_auto = dir_base / nome_iniziale
            cartella_auto.mkdir(parents=True, exist_ok=True)

        copertina_scelta = copertine_salvate.get(id_auto)
        lista_foto, n_as24, n_extra = processa_foto_auto(a, cartella_auto, foto_correnti_as24, copertina_scelta)

        # Assicura che la cartella fisica si trovi nella sezione giusta per il suo stato
        cartella_auto = sposta_cartella_stato(cartella_auto, stato_auto, a, n_as24, n_extra, dir_drive)

        a["stato"] = stato_auto
        a["homepage"] = bool(homepage_salvate.get(id_auto, False))
        a["foto"] = lista_foto
        a["fotoAs24"] = n_as24
        a["fotoExtra"] = n_extra
        a["copertinaScelta"] = lista_foto[0] if lista_foto else None
        conteggi_extra[id_auto] = n_extra

        if stato_auto == "arrivo":
            conta_arrivo += 1
        elif stato_auto == "venduta":
            conta_vendute += 1
        else:
            conta_salone += 1

        if n_extra > 0 and stato_auto != "venduta":
            totale_extra_aggiunte += n_extra
            auto_arricchite += 1

        info_auto = {
            "id": id_auto,
            "rif": rif,
            "stato": stato_auto,
            "marca": a.get("marca"),
            "modello": a.get("modello"),
            "versione": a.get("versione"),
            "anno": (a.get("immatricolazione") or "")[:4],
            "colore": a.get("colore"),
            "km": a.get("km"),
            "prezzo": a.get("prezzo"),
            "url_autoscout24": a.get("url"),
            "foto_autoscout24": n_as24,
            "foto_extra_cliente": n_extra,
            "foto_totali_sito": len(lista_foto),
        }
        try:
            (cartella_auto / ".info_auto.json").write_text(
                json.dumps(info_auto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        except OSError:
            pass

    # Sposta in "3 - Vendute (archivio)" eventuali auto non più presenti in annunci
    adesso = datetime.now()
    cartella_mese = cartella_vendute / str(adesso.year) / MESI_IT[adesso.month]
    spostate_in_archivio = 0

    for rif, (cartella_vecchia, stato_vecchio) in mappa_cartelle.items():
        if rif in rif_attivi or stato_vecchio == "venduta":
            continue
        cartella_mese.mkdir(parents=True, exist_ok=True)
        nome_base = RE_RIF.sub("", cartella_vecchia.name).strip()
        nome_base = re.sub(r"\[IN ARRIVO\]\s*", "", nome_base, flags=re.I)
        nome_base = re.sub(r"\(\d+[^)]*\)", "", nome_base).strip(" ·-")
        nome_venduta = pulisci_nome_cartella(
            f"{nome_base} - venduta il {adesso.strftime('%d-%m-%Y')} [rif. {rif}]"
        )
        dest_archivio = cartella_mese / nome_venduta
        if dest_archivio.exists():
            dest_archivio = cartella_mese / f"{nome_venduta}_{int(adesso.timestamp())}"
        try:
            shutil.move(str(cartella_vecchia), str(dest_archivio))
            spostate_in_archivio += 1
        except OSError:
            pass

    salva_stato_manuale(stato_man)
    scrivi_riepilogo_mancanti(cartella_vendita, annunci, conteggi_extra)

    return {
        "percorso_drive": str(dir_drive),
        "auto_attive": conta_salone + conta_arrivo,
        "in_salone": conta_salone,
        "in_arrivo": conta_arrivo,
        "vendute_manuali": conta_vendute,
        "auto_arricchite": auto_arricchite,
        "foto_extra_totali": totale_extra_aggiunte,
        "spostate_in_archivio": spostate_in_archivio,
    }
