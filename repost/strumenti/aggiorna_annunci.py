#!/usr/bin/env python3
"""
REPOST AUTOSCOUT24 — Aggiornamento annunci (prototipo locale)

Legge gli annunci attivi di un concessionario dalla sua pagina pubblica su
AutoScout24 e li salva in repost/dati/annunci.js, il file che le due vetrine
(versione-1.html e versione-2.html) leggono all'apertura.

Uso (oppure doppio clic su "Aggiorna annunci.bat"):
    python aggiorna_annunci.py
    python aggiorna_annunci.py --concessionario altro-slug-autoscout24

Solo libreria standard di Python: niente da installare.
"""
import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from cloud_github import esporta_annunci_json, pianifica_push_background
from foto_drive import carica_configurazione, carica_stato_manuale, percorso_drive, sincronizza_cartella_drive

# ---------------------------------------------------------------------------
# Impostazioni
# ---------------------------------------------------------------------------
SITO = "https://www.autoscout24.it"
CONCESSIONARIO = "enne-esse-auto-motorexpo-brescia"   # la parte finale dell'indirizzo /concessionari/...
USER_AGENT = "PaddockPrototipo/0.1 (prova locale, aggiornamento manuale)"
PAUSA = 1.5        # secondi di attesa tra una richiesta e l'altra
MAX_PAGINE = 20    # 20 annunci per pagina: basta fino a 400 annunci

# Contatti da mostrare in vetrina al posto di quelli presenti su AutoScout24
# (lì un numero può essere di tracciamento chiamate). Presi dal sito del
# concessionario; metti None per usare quelli di AutoScout24.
CONTATTI_PROPRI = {
    "telefono": "+39 030 0985415",
    "whatsapp": "+39 348 9379494",
}

CDN_FOTO = "https://prod.pictures.autoscout24.net/"
CARTELLA = Path(__file__).resolve().parent.parent
FILE_DATI = CARTELLA / "dati" / "annunci.js"
PREFISSO = "window.REPOST_DATI = "

RE_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
RE_MISURA_FOTO = re.compile(r"/\d+x\d+\.webp$")


class Errore(Exception):
    """Errore da mostrare all'utente così com'è."""


class NonTrovato(Errore):
    pass


# ---------------------------------------------------------------------------
# Scaricamento (con compressione GZIP e supporto opzionale Proxy)
# ---------------------------------------------------------------------------
def _crea_opener():
    proxy_url = os.environ.get("AUTOSCOUT_PROXY_URL", "").strip()
    if not proxy_url:
        try:
            proxy_url = (carica_configurazione().get("proxy_url") or "").strip()
        except Exception:
            proxy_url = ""
    if proxy_url:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener()


_OPENER = None


def scarica(url, tentativi=3):
    global _OPENER
    if _OPENER is None:
        _OPENER = _crea_opener()
    richiesta = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip",
        "Cache-Control": "no-cache",
    })
    ultimo = None
    for n in range(1, tentativi + 1):
        try:
            with _OPENER.open(richiesta, timeout=30) as risposta:
                raw = risposta.read()
                if risposta.headers.get("Content-Encoding", "").lower() == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise NonTrovato(f"pagina non trovata ({e.code}): {url}")
            if e.code in (401, 403, 429):
                raise Errore(f"AutoScout24 ha rifiutato la richiesta (HTTP {e.code}). Riprova più tardi.")
            ultimo = e
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo = e
        time.sleep(3 * n)
    raise Errore(f"impossibile scaricare {url}: {ultimo}")


def dati_pagina(html, url):
    """I dati della pagina sono in un blocco JSON di Next.js (__NEXT_DATA__)."""
    m = RE_NEXT_DATA.search(html)
    if not m:
        raise Errore(f"formato della pagina cambiato, dati non trovati: {url}")
    return json.loads(m.group(1))["props"]["pageProps"]


def leggi_lista(slug, pausa):
    annunci, visti, info, totale = [], set(), None, 0
    for pagina in range(1, MAX_PAGINE + 1):
        url = f"{SITO}/concessionari/{slug}?sort=standard&desc=0" + (f"&page={pagina}" if pagina > 1 else "")
        pp = dati_pagina(scarica(url), url)
        if info is None:
            if not pp.get("dealerInfoPage"):
                raise Errore(f"concessionario non trovato: {slug}")
            info, totale = pp, pp.get("numberOfResults") or 0
        nuovi = [a for a in pp.get("listings") or [] if a.get("id") and a["id"] not in visti]
        for a in nuovi:
            visti.add(a["id"])
            annunci.append(a)
        if not nuovi or len(annunci) >= totale:
            break
        time.sleep(pausa)
    return info, annunci, totale


# ---------------------------------------------------------------------------
# Descrizione: da HTML a blocchi di solo testo
# ---------------------------------------------------------------------------
class LettoreDescrizione(HTMLParser):
    """Trasforma l'HTML della descrizione in sezioni (separate da <hr>) fatte di
    blocchi semplici: titoli, paragrafi ed elenchi. La vetrina li mostra come
    testo, quindi nessun HTML esterno arriva mai nella pagina."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sezioni = [[]]
        self.parti = []         # paragrafo in corso: [testo, grassetto]
        self.grassetto = 0
        self.elenco = None      # voci dell'elenco in corso
        self.voce = None        # testo della voce in corso
        self.a_capo = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("strong", "b"):
            self.grassetto += 1
        elif tag == "br":
            self.a_capo += 1
            if self.voce is not None:
                self.voce.append(" ")
            elif self.a_capo >= 2:
                self.chiudi_paragrafo()
            else:
                self.parti.append(["\n", self.grassetto > 0])
        elif tag in ("ul", "ol"):
            self.chiudi_paragrafo()
            self.elenco = []
        elif tag == "li":
            self.voce = []
        elif tag == "hr":
            self.chiudi_paragrafo()
            self.sezioni.append([])
        elif tag in ("p", "div"):
            self.chiudi_paragrafo()

    def handle_endtag(self, tag):
        if tag in ("strong", "b"):
            self.grassetto = max(0, self.grassetto - 1)
        elif tag == "li" and self.voce is not None:
            testo = spazi("".join(self.voce))
            if testo and self.elenco is not None:
                self.elenco.append(testo)
            self.voce = None
        elif tag in ("ul", "ol"):
            if self.elenco:
                self.sezioni[-1].append({"tipo": "elenco", "voci": self.elenco})
            self.elenco = None
        elif tag in ("p", "div"):
            self.chiudi_paragrafo()

    def handle_data(self, data):
        if self.voce is not None:
            self.voce.append(data)
            return
        if not data.strip():
            if self.parti:
                self.parti.append([" ", self.grassetto > 0])
            return
        self.a_capo = 0
        self.parti.append([data, self.grassetto > 0])

    def chiudi_paragrafo(self):
        self.a_capo = 0
        unite = []
        for testo, gr in self.parti:
            testo = testo if testo == "\n" else re.sub(r"\s+", " ", testo)
            if unite and unite[-1][1] == gr:
                unite[-1][0] += testo
            else:
                unite.append([testo, gr])
        self.parti = []
        unite = [[re.sub(r" *\n *", "\n", t), g] for t, g in unite]
        while unite and not unite[0][0].strip():
            unite.pop(0)
        while unite and not unite[-1][0].strip():
            unite.pop()
        if not unite:
            return
        unite[0][0] = unite[0][0].lstrip()
        unite[-1][0] = unite[-1][0].rstrip()
        if len(unite) == 1 and unite[0][1] and unite[0][0].rstrip().endswith(":"):
            self.sezioni[-1].append({"tipo": "titolo", "testo": unite[0][0].strip().rstrip(":")})
        else:
            self.sezioni[-1].append({"tipo": "testo", "parti": [[t, 1 if g else 0] for t, g in unite]})

    def risultato(self):
        self.chiudi_paragrafo()
        return [s for s in self.sezioni if s]


def spazi(testo):
    return re.sub(r"\s+", " ", testo).strip()


def leggi_descrizione(html):
    lettore = LettoreDescrizione()
    lettore.feed(html or "")
    lettore.close()
    return lettore.risultato()


def separa_testo_comune(annunci):
    """Il concessionario aggiunge in fondo a ogni annuncio la stessa presentazione:
    la togliamo dalle singole auto e la teniamo una volta sola."""
    conteggio = {}
    for a in annunci:
        for chiave in {json.dumps(s, ensure_ascii=False) for s in a["_sezioni"]}:
            conteggio[chiave] = conteggio.get(chiave, 0) + 1
    soglia = max(2, len(annunci) / 2)
    comuni = {k for k, n in conteggio.items() if n >= soglia}
    presentazione = []
    for a in annunci:
        proprie = []
        for s in a.pop("_sezioni"):
            chiave = json.dumps(s, ensure_ascii=False)
            if chiave in comuni:
                if not presentazione:
                    presentazione = s
            else:
                proprie.extend(s)
        a["descrizione"] = proprie
    return presentazione


# ---------------------------------------------------------------------------
# Normalizzazione dei dati
# ---------------------------------------------------------------------------
def testo(valore):
    """Alcuni campi sono {raw, formatted}, altri stringhe semplici."""
    if isinstance(valore, dict):
        return valore.get("formatted") or None
    return valore or None


def foto_base(url):
    """Toglie la misura finale (/1280x960.webp): la vetrina sceglie quella che le serve."""
    if not isinstance(url, str) or not url.startswith(CDN_FOTO):
        return None
    return RE_MISURA_FOTO.sub("", url)


def solo_cifre(numero):
    return "+" + re.sub(r"\D", "", numero) if numero else None


def componi_annuncio(voce, dettaglio):
    v = dettaglio.get("vehicle") or {}
    vl = voce.get("vehicle") or {}
    prezzi = ((dettaglio.get("prices") or {}).get("public")) or ((voce.get("prices") or {}).get("public")) or {}
    consumo = v.get("fuelConsumptionCombined") or {}
    co2 = v.get("co2emissionInGramPerKmWithFallback") or {}
    proprietari = (vl.get("noOfPreviousOwners") or {}).get("raw")
    interni = " ".join(x for x in (v.get("upholstery"), (v.get("upholsteryColor") or "").lower()) if x)

    accessori = []
    ordine = ["safetyAndSecurity", "comfortAndConvenience", "entertainmentAndMedia", "extras"]
    gruppi = v.get("equipment") or {}
    for chiave in sorted(gruppi, key=lambda k: ordine.index(k) if k in ordine else 99):
        voci = [e.get("id") for e in gruppi[chiave] if e.get("id")]
        if voci:
            accessori.append({"categoria": gruppi[chiave][0].get("categoryName") or chiave, "voci": voci})

    return {
        "id": voce["id"],
        "url": SITO + voce["url"] if voce.get("url", "").startswith("/") else None,
        "marca": v.get("make") or vl.get("make"),
        "modello": v.get("model") or vl.get("model"),
        "versione": spazi(v.get("modelVersionInput") or vl.get("modelVersionInput") or ""),
        "sottotitolo": spazi(vl.get("subtitle") or ""),
        "prezzo": prezzi.get("priceRaw"),
        "ivaDeducibile": bool(prezzi.get("taxDeductible")),
        "trattabile": bool(prezzi.get("negotiable")),
        "km": v.get("mileageInKmRaw"),
        "immatricolazione": (v.get("firstRegistrationDateRaw") or "")[:7] or None,
        "condizione": ", ".join(v.get("legalCategories") or []) or None,
        "cv": v.get("rawPowerInHp"),
        "kw": v.get("rawPowerInKw"),
        "carburante": testo(v.get("fuelCategory")),
        "cambio": testo(v.get("transmissionType")),
        "marce": v.get("gears"),
        "trazione": v.get("driveTrain"),
        "cilindri": v.get("cylinders"),
        "cilindrata": v.get("rawDisplacementInCCM"),
        "carrozzeria": testo(v.get("bodyType")),
        "porte": v.get("numberOfDoors"),
        "posti": v.get("numberOfSeats"),
        "colore": v.get("bodyColor"),
        "vernice": v.get("paintType"),
        "interni": interni or None,
        "consumo": consumo.get("formatted") if consumo.get("raw") else None,
        "co2": co2.get("formatted") if co2.get("raw") else None,
        "classeEmissioni": (v.get("environmentEuDirective") or {}).get("formatted"),
        "proprietari": proprietari,
        "garanzia": dettaglio.get("warranty") if dettaglio.get("warrantyExists") else None,
        "tagliandi": bool(v.get("hasFullServiceHistory")),
        "nonFumatori": bool(v.get("nonSmoking")),
        "neopatentati": bool(v.get("newDriverSuitable")),
        "foto": [f for f in (foto_base(u) for u in dettaglio.get("images") or voce.get("images") or []) if f],
        "accessori": accessori,
        "pubblicato": dettaglio.get("createdTimestampWithOffset"),
        "_sezioni": leggi_descrizione(dettaglio.get("description")),
    }


def componi_concessionario(info, slug, primo_dettaglio):
    d = info["dealerInfoPage"]
    indirizzo = d.get("customerAddress") or {}
    luogo = (primo_dettaglio or {}).get("location") or {}
    telefoni = [{"testo": t, "numero": solo_cifre(t)} for t in d.get("customerPhoneNumbers") or []]
    whatsapp = (primo_dettaglio or {}).get("whatsappNumber")
    if CONTATTI_PROPRI.get("telefono"):
        telefoni = [{"testo": CONTATTI_PROPRI["telefono"], "numero": solo_cifre(CONTATTI_PROPRI["telefono"])}]
    if CONTATTI_PROPRI.get("whatsapp"):
        whatsapp = CONTATTI_PROPRI["whatsapp"]

    reparti = d.get("openingHours") or [{}]
    orari = [[f"{x // 100:02d}:{x % 100:02d}" for x in fasce] for fasce in reparti[0].get("timetable") or []]

    return {
        "nome": d.get("customerName"),
        "indirizzo": {"via": indirizzo.get("street"), "cap": indirizzo.get("zipCode"), "citta": indirizzo.get("city")},
        "coordinate": [luogo["latitude"], luogo["longitude"]] if luogo.get("latitude") else None,
        "telefoni": telefoni,
        "whatsapp": {"testo": whatsapp, "numero": solo_cifre(whatsapp)} if whatsapp else None,
        "referente": d.get("contactName"),
        "sito": d.get("homepageUrl"),
        "orari": orari,           # lunedì ... domenica, fasce "09:00" "13:00" ...
        "servizi": [s.get("name") for s in d.get("additionalServices") or [] if s.get("name")],
        "paginaAutoScout24": f"{SITO}/concessionari/{slug}",
        "presentazione": [],
    }


# ---------------------------------------------------------------------------
# Confronto con l'aggiornamento precedente
# ---------------------------------------------------------------------------
def leggi_precedente():
    try:
        contenuto = FILE_DATI.read_text(encoding="utf-8").strip()
        if contenuto.startswith(PREFISSO):
            return json.loads(contenuto[len(PREFISSO):].rstrip(";"))
    except (OSError, ValueError):
        pass
    return None


def calcola_variazioni(precedente, annunci):
    if not precedente:
        return None
    prima = {a["id"]: a for a in precedente.get("annunci", [])}
    ora = {a["id"]: a for a in annunci}
    titolo = lambda a: f"{a.get('marca')} {a.get('modello')}"
    return {
        "dal": precedente.get("aggiornato"),
        "nuovi": [i for i in ora if i not in prima],
        "rimossi": [{"id": i, "titolo": titolo(a), "prezzo": a.get("prezzo")} for i, a in prima.items() if i not in ora],
        "prezzi": [{"id": i, "da": prima[i].get("prezzo"), "a": a.get("prezzo")}
                   for i, a in ora.items() if i in prima and prima[i].get("prezzo") != a.get("prezzo")],
    }


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------
def applica_protezioni_vendute(precedente, annunci_nuovi, config):
    """Protezione contro errori temporanei di AutoScout24 (come promesso nella proposta):
    1. Se sparisce più del 40% delle auto in un solo controllo, non rimuove nulla.
    2. Un'auto assente viene rimossa solo dopo N (predefinito: 2) controlli consecutivi.
    """
    if not precedente or not precedente.get("annunci"):
        return annunci_nuovi
    prec_lista = precedente["annunci"]
    id_nuovi = {a["id"] for a in annunci_nuovi}
    mancanti = [a for a in prec_lista if a["id"] not in id_nuovi]
    if not mancanti:
        return annunci_nuovi

    soglia_allarme = float(config.get("soglia_allarme_sparizione", 0.4))
    controlli_richiesti = int(config.get("controlli_prima_di_rimuovere", 2))

    if len(prec_lista) >= 5 and (len(mancanti) / len(prec_lista)) >= soglia_allarme:
        print(f"  [!] ATTENZIONE: {len(mancanti)} auto su {len(prec_lista)} risultano assenti tutte insieme.")
        print("      Per sicurezza manteniamo in vetrina le auto precedenti senza rimuovere nulla.")
        for m in mancanti:
            copia = dict(m)
            copia["_assenze"] = copia.get("_assenze", 0) + 1
            annunci_nuovi.append(copia)
        return annunci_nuovi

    for m in mancanti:
        assenze = int(m.get("_assenze", 0)) + 1
        if assenze < controlli_richiesti:
            print(f"  [i] {m.get('marca')} {m.get('modello')} assente ({assenze}/{controlli_richiesti} controlli): mantenuta per sicurezza.")
            copia = dict(m)
            copia["_assenze"] = assenze
            annunci_nuovi.append(copia)
    return annunci_nuovi


def main():
    config = carica_configurazione()
    parser = argparse.ArgumentParser(description="Aggiorna gli annunci della vetrina dal profilo AutoScout24 e sincronizza la cartella foto.")
    parser.add_argument("--concessionario", default=config.get("concessionario_slug") or CONCESSIONARIO, help="slug della pagina /concessionari/... su AutoScout24")
    parser.add_argument("--pausa", type=float, default=PAUSA, help="secondi tra una richiesta e l'altra")
    parser.add_argument("--solo-foto", action="store_true", help="sincronizza solo la cartella foto senza riscaricare da AutoScout24 (immediato)")
    parser.add_argument("--completo", action="store_true", help="forza il riscaricamento di tutte le singole schede auto anche se invariate")
    parser.add_argument("--cartella-drive", default=None, help="percorso personalizzato della cartella Google Drive")
    args = parser.parse_args()

    inizio = time.time()
    precedente = leggi_precedente()
    dir_drive = Path(args.cartella_drive) if args.cartella_drive else percorso_drive(config)

    if args.solo_foto:
        if not precedente or not precedente.get("annunci"):
            raise Errore("nessun dato precedente in annunci.js. Esegui prima un aggiornamento completo.")
        print("Modalità rapida (--solo-foto): lettura annunci già scaricati...")
        dati = dict(precedente)
        annunci = dati["annunci"]
    else:
        print(f"Concessionario: {args.concessionario}")
        info, lista, totale = leggi_lista(args.concessionario, args.pausa)
        print(f"Annunci attivi trovati: {len(lista)} (AutoScout24 ne dichiara {totale})")

        mappa_prec = {x["id"]: x for x in (precedente or {}).get("annunci", []) if x.get("id")}
        annunci, primo_dettaglio, scaricati_dettaglio = [], None, 0

        for n, voce in enumerate(lista, 1):
            id_v = voce["id"]
            prec_a = mappa_prec.get(id_v)
            prezzo_lista = ((voce.get("prices") or {}).get("public") or {}).get("priceRaw")
            sottotitolo_lista = spazi((voce.get("vehicle") or {}).get("subtitle") or "")

            # Delta-Sync intelligente: se l'auto è già in memoria con descrizione e prezzo/titolo invariati,
            # evita di fare una richiesta HTTP aggiuntiva (risparmio ~95% banda e richieste orarie)
            if (not args.completo
                    and prec_a
                    and isinstance(prec_a.get("descrizione"), list)
                    and prec_a.get("prezzo") == prezzo_lista
                    and prec_a.get("sottotitolo") == sottotitolo_lista):
                annuncio = dict(prec_a)
                annuncio["ordineAs24"] = n
                annuncio["ordineDefault"] = prec_a.get("ordineDefault", n)
                annuncio.pop("_assenze", None)
                annunci.append(annuncio)
                print(f"  [{n:>2}/{len(lista)}] {annuncio['marca']} {annuncio['modello']} · invariato (cache delta)")
                continue

            time.sleep(args.pausa)
            url = SITO + voce["url"]
            try:
                dettaglio = dati_pagina(scarica(url), url).get("listingDetails") or {}
                scaricati_dettaglio += 1
            except NonTrovato:
                print(f"  [{n:>2}/{len(lista)}] rimosso nel frattempo, salto")
                continue
            if dettaglio.get("status") not in (None, "Active"):
                print(f"  [{n:>2}/{len(lista)}] non attivo ({dettaglio.get('status')}), salto")
                continue
            primo_dettaglio = primo_dettaglio or dettaglio
            annuncio = componi_annuncio(voce, dettaglio)
            annuncio["ordineAs24"] = n
            annuncio["ordineDefault"] = (prec_a or {}).get("ordineDefault", n)
            annunci.append(annuncio)
            print(f"  [{n:>2}/{len(lista)}] {annuncio['marca']} {annuncio['modello']} · {len(annuncio['foto'])} foto su AS24 (scaricato)")

        concessionario = componi_concessionario(info, args.concessionario, primo_dettaglio)
        nuovi_con_sezioni = [a for a in annunci if "_sezioni" in a]
        if nuovi_con_sezioni:
            pres = separa_testo_comune(nuovi_con_sezioni)
            concessionario["presentazione"] = pres or (precedente or {}).get("concessionario", {}).get("presentazione", [])
        elif precedente and precedente.get("concessionario"):
            concessionario["presentazione"] = precedente["concessionario"].get("presentazione", [])
        if not concessionario.get("coordinate") and precedente and precedente.get("concessionario"):
            concessionario["coordinate"] = precedente["concessionario"].get("coordinate")
        if not concessionario.get("whatsapp") and precedente and precedente.get("concessionario"):
            concessionario["whatsapp"] = precedente["concessionario"].get("whatsapp")

        if precedente and precedente.get("concessionario", {}).get("paginaAutoScout24") != concessionario["paginaAutoScout24"]:
            precedente = None   # concessionario diverso: niente confronto

        annunci = applica_protezioni_vendute(precedente, annunci, config)
        dati = {
            "aggiornato": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "fonte": "AutoScout24 (pagina pubblica del concessionario)",
            "concessionario": concessionario,
            "annunci": annunci,
            "variazioni": calcola_variazioni(precedente, annunci),
        }

    # Sincronizza le cartelle foto (locale / Google Drive) e unisce le foto integrative
    print(f"\nSincronizzazione cartella foto: {dir_drive}")
    esito_foto = sincronizza_cartella_drive(annunci, dir_drive)
    stato_man = carica_stato_manuale()
    dati["ordineSito"] = stato_man.get("ordine_sito") or "autoscout"
    print(f"  Cartelle auto in vendita: {esito_foto['auto_attive']} | "
          f"Auto con foto extra: {esito_foto['auto_arricchite']} (+{esito_foto['foto_extra_totali']} foto) | "
          f"Archiviate in Vendute: {esito_foto['spostate_in_archivio']}")

    FILE_DATI.parent.mkdir(parents=True, exist_ok=True)
    temporaneo = FILE_DATI.with_suffix(".tmp")
    temporaneo.write_text(PREFISSO + json.dumps(dati, ensure_ascii=True, separators=(",", ":")) + ";\n", encoding="utf-8")
    temporaneo.replace(FILE_DATI)
    esporta_annunci_json(dati)
    pianifica_push_background("Aggiornamento automatico AutoScout24", ritardo_sec=0.5)

    var = dati.get("variazioni")
    if var and not args.solo_foto:
        print(f"Rispetto all'aggiornamento precedente: {len(var['nuovi'])} nuovi, "
              f"{len(var['rimossi'])} rimossi, {len(var['prezzi'])} prezzi cambiati")
    print(f"Salvato {FILE_DATI} in {time.time() - inizio:.1f} s. Ricarica la vetrina nel browser.")


if __name__ == "__main__":
    try:
        main()
    except Errore as e:
        print(f"\nErrore: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrotto.")
        sys.exit(1)
