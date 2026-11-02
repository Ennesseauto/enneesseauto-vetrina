/* =========================================================================
   ENNE ESSE AUTO · MOTOREXPO BRESCIA — Motore Embed Live per Sito Ufficiale
   Alimenta i 3 blocchi del sito (Duda / HTML custom) in tempo reale:
   1) #ees-home-salone       -> Homepage: Carosello "Divisione Auto" (In Salone)
   2) #ees-home-arrivo       -> Homepage: Sezione "Vetture in Arrivo" (auto-hide se 0)
   3) #ees-catalogo-completo -> Pagina Autovetture: Catalogo + Filtri + Scheda Auto
   ========================================================================= */
(function () {
  'use strict';

  if (window.__EES_TIMER__) {
    clearInterval(window.__EES_TIMER__);
  }

  // Origine GitHub Pages bloccata (compilata automaticamente da setup_github.py)
  const LOCKED_GITHUB_ORIGIN = 'https://Ennesseauto.github.io/enneesseauto-vetrina';
  const IS_LOCAL_HOST = (location.hostname === '127.0.0.1' || location.hostname === 'localhost');
  const API_ORIGIN = 'http://127.0.0.1:8765';

  function rilevaCloudOrigin() {
    if (LOCKED_GITHUB_ORIGIN) return LOCKED_GITHUB_ORIGIN;
    if (window.EES_CONFIG && window.EES_CONFIG.cloudOrigin) {
      const cand = String(window.EES_CONFIG.cloudOrigin).replace(/\/+$/, '');
      if (/^https:\/\/[a-z0-9-]+\.github\.io\/[a-z0-9._-]+$/i.test(cand) && !cand.includes('TUO-UTENTE')) {
        return cand;
      }
    }
    return '';
  }
  const CLOUD_ORIGIN = rilevaCloudOrigin();
  // Se il progetto GitHub è collegato e siamo sul sito pubblico (non localhost),
  // blocchiamo la lettura ESCLUSIVAMENTE da quell'unico progetto GitHub Pages!
  const SOLO_DA_GITHUB = Boolean(CLOUD_ORIGIN && !IS_LOCAL_HOST);
  let serverLocaleAttivo = false;
  const CDN_FOTO = 'https://prod.pictures.autoscout24.net/';
  const MISURE = { mini: '250x188', media: '720x540', grande: '1280x960', piena: '1920x1080' };
  const RE_FOTO_EXTRA = /^foto-extra\/[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/;

  const CONTATTI = {
    nome: 'Enne Esse Auto · Motorexpo Brescia Store',
    telefonoTesto: '+39 030 0985415',
    telefonoHref: 'tel:+390300985415',
    whatsappNumero: '393661686090',
    catalogoUrl: (window.EES_CONFIG && window.EES_CONFIG.catalogoUrl) || '/negozio'
  };

  let annunciTutti = (window.REPOST_DATI && Array.isArray(window.REPOST_DATI.annunci)) ? window.REPOST_DATI.annunci : [];
  let annunci = annunciTutti.filter(a => a.stato !== 'venduta');
  let ordineSito = (window.REPOST_DATI && window.REPOST_DATI.ordineSito) || 'autoscout';
  let variazioni = (window.REPOST_DATI && window.REPOST_DATI.variazioni) || null;
  let nuovi = new Set(variazioni && Array.isArray(variazioni.nuovi) ? variazioni.nuovi : []);
  let cambiPrezzo = new Map(((variazioni && Array.isArray(variazioni.prezzi)) ? variazioni.prezzi : []).map(p => [p.id, p]));
  let ultimaImpronta = '';

  function confrontaDaDashboard(a, b) {
    if (ordineSito === 'default') return (a.ordineDefault ?? a.ordineAs24 ?? 999) - (b.ordineDefault ?? b.ordineAs24 ?? 999);
    if (ordineSito === 'recenti') return String(b.pubblicato || '').localeCompare(String(a.pubblicato || ''));
    if (ordineSito === 'prezzoSu') return (a.prezzo ?? Infinity) - (b.prezzo ?? Infinity);
    if (ordineSito === 'prezzoGiu') return (b.prezzo ?? -1) - (a.prezzo ?? -1);
    if (ordineSito === 'menoFoto') return (a.foto || []).length - (b.foto || []).length;
    return (a.ordineAs24 ?? 999) - (b.ordineAs24 ?? 999);
  }

  const filtro = { testo: '', marca: '', stato: '', categoria: '', ordine: 'default' };
  const ORDINI = {
    default: confrontaDaDashboard,
    recenti: (a, b) => String(b.pubblicato || '').localeCompare(String(a.pubblicato || '')),
    prezzoSu: (a, b) => (a.prezzo ?? Infinity) - (b.prezzo ?? Infinity),
    prezzoGiu: (a, b) => (b.prezzo ?? -1) - (a.prezzo ?? -1),
    km: (a, b) => (a.km ?? Infinity) - (b.km ?? Infinity),
    anno: (a, b) => String(b.immatricolazione || '').localeCompare(String(a.immatricolazione || '')),
    potenza: (a, b) => (b.cv ?? 0) - (a.cv ?? 0)
  };

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  function esc(valore) {
    const m = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return String(valore == null ? '' : valore).replace(/[&<>"']/g, c => m[c]);
  }

  function numero(v) {
    const [intera] = Math.abs(Number(v)).toFixed(0).split('.');
    return (v < 0 ? '-' : '') + intera.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  const fmtPrezzo = p => (p == null ? 'Prezzo su richiesta' : '€ ' + numero(p));
  const fmtKm = km => (km == null ? null : numero(km) + ' km');
  const fmtImm = s => (s ? `${s.slice(5, 7)}/${s.slice(0, 4)}` : null);
  const titolo = a => `${a.marca} ${a.modello}`;
  const titoloCompleto = a => `${titolo(a)} ${a.versione || ''}`.trim();
  const normalizza = t => String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

  function foto(base, misura) {
    if (typeof base !== 'string') return '';
    if (base.startsWith(CDN_FOTO)) return `${base}/${MISURE[misura]}.webp`;
    if (RE_FOTO_EXTRA.test(base)) {
      const origineFoto = (!serverLocaleAttivo && CLOUD_ORIGIN) ? CLOUD_ORIGIN : API_ORIGIN;
      return `${origineFoto}/repost/dati/${base}/${MISURE[misura]}.webp`;
    }
    return '';
  }

  function ribassato(a) {
    const c = cambiPrezzo.get(a.id);
    return c && c.da != null && a.prezzo != null && a.prezzo < c.da ? c : null;
  }

  function linkWhatsApp(messaggio) {
    return `https://wa.me/${CONTATTI.whatsappNumero}${messaggio ? '?text=' + encodeURIComponent(messaggio) : ''}`;
  }

  const STILE_ICO = ' style="width:18px !important;height:18px !important;max-width:18px !important;max-height:18px !important;display:inline-block !important;vertical-align:middle !important;flex-shrink:0 !important;"';
  const svg = (d, extra = '') => `<svg class="ees-mx-ico" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"${STILE_ICO}${extra}>${d}</svg>`;
  const pieno = d => `<svg class="ees-mx-ico" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"${STILE_ICO}>${d}</svg>`;
  const ICO = {
    sx: svg('<path d="M15 18l-6-6 6-6"/>'),
    dx: svg('<path d="M9 18l6-6-6-6"/>'),
    chiudi: svg('<path d="M18 6 6 18M6 6l12 12"/>'),
    cerca: svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
    strada: svg('<path d="M8 3 4 21M16 3l4 18M12 4v3M12 10.5v3M12 17v3"/>'),
    cambio: svg('<circle cx="6" cy="5" r="1.8"/><circle cx="12" cy="5" r="1.8"/><circle cx="18" cy="5" r="1.8"/><path d="M6 6.8V19M12 6.8V19M18 6.8V12H6"/>'),
    calendario: svg('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'),
    carburante: svg('<path d="M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h12M4 10h10"/><path d="M14 8h2a2 2 0 0 1 2 2v6a1.5 1.5 0 0 0 3 0V9l-3-3"/>'),
    potenza: svg('<path d="M4.9 19a9 9 0 1 1 14.2 0"/><path d="M12 14l4-4"/><circle cx="12" cy="14" r="1.2"/>'),
    auto: svg('<path d="M3 16.5V13l2.4-5.2A2 2 0 0 1 7.2 6.6h9.6a2 2 0 0 1 1.8 1.2L21 13v3.5"/><path d="M3 13h18M2.5 16.5h19"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>'),
    check: svg('<path d="M20 6L9 17l-5-5"/>'),
    foto: svg('<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>'),
    zoom: svg('<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>'),
    telefono: svg('<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>'),
    whatsapp: pieno('<path d="M12.04 2a9.9 9.9 0 0 0-8.5 14.98L2 22l5.16-1.5A9.9 9.9 0 1 0 12.04 2zm0 18.1a8.2 8.2 0 0 1-4.2-1.15l-.3-.18-3.06.89.9-2.98-.2-.31a8.2 8.2 0 1 1 6.86 3.73zm4.5-6.14c-.25-.12-1.46-.72-1.69-.8-.23-.08-.39-.12-.55.12-.16.25-.63.8-.78.97-.14.16-.29.18-.53.06a6.7 6.7 0 0 1-3.32-2.9c-.25-.43.25-.4.72-1.33.08-.16.04-.3-.02-.43-.06-.12-.55-1.33-.76-1.82-.2-.48-.4-.41-.55-.42h-.47a.9.9 0 0 0-.65.3 2.74 2.74 0 0 0-.86 2.04 4.76 4.76 0 0 0 1 2.53 10.9 10.9 0 0 0 4.17 3.68c1.55.67 2.16.73 2.94.61.47-.07 1.46-.6 1.66-1.17.2-.58.2-1.07.15-1.17-.06-.1-.22-.16-.47-.28z"/>')
  };

  /* ---------- Stili CSS isolati (immuni da override di Duda #dm) ---------- */
  function iniettaStili() {
    let style = $('#ees-mx-styles');
    if (!style) {
      style = document.createElement('style');
      style.id = 'ees-mx-styles';
      document.head.appendChild(style);
    }
    style.textContent = `
      .ees-mx-root, .ees-mx-root *, .ees-mx-modal, .ees-mx-modal * { box-sizing: border-box !important; }
      .ees-mx-root {
        --ees-arancio: #f36e21;
        --ees-arancio-scuro: #d85a10;
        --ees-nero: #0b0b0b;
        --ees-card: #141416;
        --ees-bordo: rgba(255,255,255,0.12);
        --ees-testo: #f5f5f5;
        --ees-tenue: #a8abb2;
        font-family: "Montserrat", "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
        color: var(--ees-testo) !important;
        width: 100%;
        max-width: 1320px;
        margin: 0 auto;
        padding: 10px 14px;
        text-align: left;
      }
      .ees-mx-ico { width: 18px; height: 18px; flex-shrink: 0; display: inline-block; vertical-align: middle; }
      /* Carosello Homepage */
      .ees-mx-carosello { position: relative; width: 100%; }
      .ees-mx-binario {
        display: grid !important;
        grid-auto-flow: column !important;
        grid-auto-columns: calc((100% - 54px) / 4) !important;
        gap: 18px !important;
        overflow-x: auto !important;
        scroll-snap-type: x mandatory;
        scrollbar-width: none;
        padding: 6px 2px 14px !important;
      }
      .ees-mx-binario::-webkit-scrollbar { display: none; }
      @media (max-width: 1100px) { .ees-mx-binario { grid-auto-columns: calc((100% - 36px) / 3) !important; } }
      @media (max-width: 820px) { .ees-mx-binario { grid-auto-columns: calc((100% - 18px) / 2) !important; } }
      @media (max-width: 540px) { .ees-mx-binario { grid-auto-columns: 86% !important; } }
      .ees-mx-freccia {
        position: absolute !important; top: 42% !important; transform: translateY(-50%) !important;
        width: 44px !important; height: 44px !important; border-radius: 50% !important;
        background: rgba(15,15,18,0.92) !important; color: #fff !important;
        border: 1px solid rgba(255,255,255,0.22) !important; cursor: pointer !important;
        display: inline-flex !important; align-items: center !important; justify-content: center !important;
        z-index: 5 !important; transition: all 0.2s ease !important;
        box-shadow: 0 6px 20px rgba(0,0,0,0.45) !important;
      }
      .ees-mx-freccia:hover:not(:disabled) { background: var(--ees-arancio) !important; border-color: var(--ees-arancio) !important; }
      .ees-mx-freccia:disabled { opacity: 0.25 !important; cursor: default !important; }
      .ees-mx-freccia--sx { left: -10px !important; }
      .ees-mx-freccia--dx { right: -10px !important; }
      /* Card Auto */
      .ees-mx-card {
        background: var(--ees-card) !important;
        border: 1px solid var(--ees-bordo) !important;
        border-radius: 12px !important;
        overflow: hidden !important;
        scroll-snap-align: start;
        transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease !important;
        display: flex !important; flex-direction: column !important;
      }
      .ees-mx-card:hover {
        transform: translateY(-4px) !important;
        border-color: rgba(243,110,33,0.65) !important;
        box-shadow: 0 12px 28px rgba(0,0,0,0.5) !important;
      }
      .ees-mx-card__link {
        text-decoration: none !important; color: inherit !important;
        display: flex !important; flex-direction: column !important; height: 100% !important;
        cursor: pointer !important;
      }
      .ees-mx-card__foto {
        position: relative !important; width: 100% !important; height: 220px !important; max-height: 220px !important;
        background: #080809 !important; overflow: hidden !important;
      }
      .ees-mx-card__foto img {
        width: 100% !important; height: 220px !important; max-width: 100% !important; max-height: 220px !important; object-fit: cover !important;
        display: block !important; transition: transform 0.35s ease !important;
      }
      .ees-mx-card:hover .ees-mx-card__foto img { transform: scale(1.04) !important; }
      .ees-mx-card__badge {
        position: absolute !important; top: 10px !important; left: 10px !important;
        display: flex !important; flex-wrap: wrap !important; gap: 6px !important; z-index: 2 !important;
      }
      .ees-mx-badge {
        background: rgba(15,15,18,0.88) !important; color: #fff !important;
        font-size: 11px !important; font-weight: 700 !important; text-transform: uppercase !important;
        letter-spacing: 0.04em !important; padding: 4px 9px !important; border-radius: 999px !important;
        border: 1px solid rgba(255,255,255,0.18) !important; line-height: 1.2 !important;
      }
      .ees-mx-badge--arancio {
        background: var(--ees-arancio) !important; color: #fff !important; border-color: var(--ees-arancio) !important;
      }
      .ees-mx-card__conta {
        position: absolute !important; bottom: 10px !important; right: 10px !important;
        background: rgba(10,10,12,0.82) !important; color: #fff !important;
        font-size: 11.5px !important; font-weight: 600 !important; padding: 4px 9px !important;
        border-radius: 999px !important; display: inline-flex !important; align-items: center !important; gap: 5px !important;
      }
      .ees-mx-card__conta .ees-mx-ico { width: 14px !important; height: 14px !important; }
      .ees-mx-card__testo {
        padding: 14px 16px 16px !important; display: flex !important;
        flex-direction: column !important; gap: 6px !important; flex: 1 !important;
      }
      .ees-mx-card__titolo {
        margin: 0 !important; font-size: 15.5px !important; font-weight: 700 !important;
        color: #fff !important; line-height: 1.32 !important;
        display: -webkit-box !important; -webkit-line-clamp: 2 !important; -webkit-box-orient: vertical !important; overflow: hidden !important;
      }
      .ees-mx-card__dati {
        margin: 0 !important; font-size: 12.5px !important; color: var(--ees-tenue) !important; line-height: 1.4 !important;
      }
      .ees-mx-card__prezzo {
        margin: auto 0 0 !important; padding-top: 8px !important;
        font-size: 18px !important; font-weight: 800 !important; color: var(--ees-arancio) !important;
      }
      .ees-mx-card__prezzo s {
        color: var(--ees-tenue) !important; font-size: 13px !important; font-weight: 500 !important; margin-right: 6px !important;
      }
      .ees-mx-centro { text-align: center !important; margin-top: 26px !important; }
      .ees-mx-btn-pillola {
        display: inline-flex !important; align-items: center !important; justify-content: center !important;
        gap: 8px !important; padding: 12px 28px !important; border-radius: 999px !important;
        background: var(--ees-arancio) !important; color: #fff !important;
        font-size: 14px !important; font-weight: 700 !important; text-transform: uppercase !important;
        letter-spacing: 0.05em !important; text-decoration: none !important; border: none !important;
        cursor: pointer !important; transition: background 0.2s ease !important;
      }
      .ees-mx-btn-pillola:hover { background: var(--ees-arancio-scuro) !important; color: #fff !important; }

      /* Catalogo Completo + Filtri */
      .ees-mx-strumenti {
        display: grid !important; grid-template-columns: 1.5fr repeat(3, minmax(150px, 0.75fr)) !important;
        gap: 12px !important; margin-bottom: 16px !important; align-items: end !important;
      }
      @media (max-width: 960px) { .ees-mx-strumenti { grid-template-columns: 1fr 1fr !important; } }
      @media (max-width: 560px) { .ees-mx-strumenti { grid-template-columns: 1fr !important; } }
      .ees-mx-cerca {
        display: flex !important; align-items: center !important; gap: 10px !important;
        background: #141416 !important; border: 1px solid var(--ees-bordo) !important;
        border-radius: 10px !important; padding: 0 14px !important; height: 46px !important;
      }
      .ees-mx-cerca input {
        background: transparent !important; border: none !important; outline: none !important;
        color: #fff !important; font-size: 14px !important; width: 100% !important; height: 100% !important;
      }
      .ees-mx-select-wrap {
        display: flex !important; flex-direction: column !important; gap: 4px !important;
      }
      .ees-mx-select-wrap span {
        font-size: 11px !important; font-weight: 700 !important; text-transform: uppercase !important;
        letter-spacing: 0.06em !important; color: var(--ees-tenue) !important;
      }
      .ees-mx-select-wrap select {
        height: 46px !important; background: #141416 !important; color: #fff !important;
        border: 1px solid var(--ees-bordo) !important; border-radius: 10px !important;
        padding: 0 12px !important; font-size: 13.5px !important; outline: none !important; cursor: pointer !important;
      }
      .ees-mx-chips {
        display: flex !important; flex-wrap: wrap !important; gap: 8px !important; margin-bottom: 18px !important;
      }
      .ees-mx-chip {
        background: #141416 !important; color: #e2e4e9 !important;
        border: 1px solid var(--ees-bordo) !important; border-radius: 999px !important;
        padding: 7px 14px !important; font-size: 13px !important; font-weight: 600 !important;
        cursor: pointer !important; display: inline-flex !important; align-items: center !important; gap: 6px !important;
      }
      .ees-mx-chip[aria-pressed="true"] {
        background: var(--ees-arancio) !important; color: #fff !important; border-color: var(--ees-arancio) !important;
      }
      .ees-mx-chip__n { opacity: 0.78; font-size: 11.5px; }
      .ees-mx-barra-stato {
        display: flex !important; justify-content: space-between !important; align-items: center !important;
        margin-bottom: 16px !important; font-size: 13.5px !important; color: var(--ees-tenue) !important;
      }
      .ees-mx-link-btn {
        background: none !important; border: none !important; color: var(--ees-arancio) !important;
        font-weight: 700 !important; cursor: pointer !important; text-decoration: underline !important; font-size: 13px !important;
      }
      .ees-mx-griglia {
        display: grid !important; grid-template-columns: repeat(4, minmax(0, 1fr)) !important; gap: 20px !important; width: 100% !important;
      }
      @media (max-width: 1100px) { .ees-mx-griglia { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; } }
      @media (max-width: 820px) { .ees-mx-griglia { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; } }
      @media (max-width: 540px) { .ees-mx-griglia { grid-template-columns: minmax(0, 1fr) !important; } }

      /* Scheda Singola Auto (Inline o Overlay dedicato) */
      .ees-mx-scheda-top {
        display: flex !important; justify-content: space-between !important; align-items: center !important;
        flex-wrap: wrap !important; gap: 12px !important; margin-bottom: 20px !important;
        padding-bottom: 14px !important; border-bottom: 1px solid var(--ees-bordo) !important;
      }
      .ees-mx-torna {
        display: inline-flex !important; align-items: center !important; gap: 8px !important;
        background: #1a1b1e !important; color: #fff !important; border: 1px solid var(--ees-bordo) !important;
        padding: 9px 16px !important; border-radius: 999px !important; font-size: 13.5px !important;
        font-weight: 700 !important; cursor: pointer !important; text-decoration: none !important;
      }
      .ees-mx-torna:hover { border-color: var(--ees-arancio) !important; color: var(--ees-arancio) !important; }
      .ees-mx-dettaglio {
        display: grid !important; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr) !important; gap: 28px !important; align-items: start !important; width: 100% !important; max-width: 100% !important;
      }
      .ees-mx-dettaglio > * { min-width: 0 !important; max-width: 100% !important; overflow: hidden !important; }
      @media (max-width: 920px) { .ees-mx-dettaglio { grid-template-columns: minmax(0, 1fr) !important; } }
      .ees-mx-palco {
        position: relative !important; width: 100% !important; max-width: 100% !important;
        height: 460px !important; max-height: 62vh !important; background: #070708 !important;
        border-radius: 14px !important; overflow: hidden !important; border: 1px solid var(--ees-bordo) !important;
      }
      @media (max-width: 640px) { .ees-mx-palco { height: 270px !important; } }
      .ees-mx-palco img {
        width: 100% !important; height: 100% !important; max-width: 100% !important; max-height: 100% !important;
        object-fit: cover !important; display: block !important; cursor: zoom-in !important; margin: 0 auto !important;
      }
      .ees-mx-palco__pill {
        position: absolute !important; bottom: 12px !important; left: 12px !important;
        background: rgba(10,10,12,0.85) !important; color: #fff !important;
        padding: 5px 12px !important; border-radius: 999px !important; font-size: 12.5px !important; font-weight: 700 !important;
      }
      .ees-mx-palco__zoom {
        position: absolute !important; bottom: 12px !important; right: 12px !important;
        background: rgba(10,10,12,0.85) !important; color: #fff !important; border: 1px solid rgba(255,255,255,0.2) !important;
        padding: 6px 12px !important; border-radius: 999px !important; font-size: 12.5px !important; font-weight: 600 !important;
        display: inline-flex !important; align-items: center !important; gap: 6px !important; cursor: pointer !important;
      }
      .ees-mx-miniature {
        display: flex !important; width: 100% !important; max-width: 100% !important; gap: 8px !important; overflow-x: auto !important;
        padding: 12px 2px 6px !important; scrollbar-width: thin;
      }
      .ees-mx-miniatura {
        width: 82px !important; min-width: 82px !important; max-width: 82px !important;
        height: 62px !important; min-height: 62px !important; max-height: 62px !important;
        flex: 0 0 82px !important;
        border-radius: 8px !important; overflow: hidden !important; border: 2px solid transparent !important;
        padding: 0 !important; cursor: pointer !important; background: #000 !important; opacity: 0.65 !important;
      }
      .ees-mx-miniatura[aria-current="true"] { border-color: var(--ees-arancio) !important; opacity: 1 !important; }
      .ees-mx-miniatura img {
        width: 82px !important; height: 62px !important; max-width: 82px !important; max-height: 62px !important;
        object-fit: cover !important; display: block !important;
      }
      .ees-mx-riepilogo {
        background: #141416 !important; border: 1px solid var(--ees-bordo) !important;
        border-radius: 14px !important; padding: 22px !important;
      }
      .ees-mx-riepilogo__marca { margin: 0 0 4px !important; font-size: 13px !important; font-weight: 700 !important; text-transform: uppercase !important; color: var(--ees-tenue) !important; }
      .ees-mx-riepilogo__titolo { margin: 0 0 6px !important; font-size: 26px !important; font-weight: 800 !important; color: #fff !important; line-height: 1.2 !important; }
      .ees-mx-riepilogo__versione { margin: 0 0 14px !important; font-size: 14.5px !important; color: #d0d3da !important; }
      .ees-mx-riepilogo__prezzo { margin: 0 0 18px !important; font-size: 30px !important; font-weight: 800 !important; color: var(--ees-arancio) !important; }
      .ees-mx-fatti {
        list-style: none !important; margin: 0 0 18px !important; padding: 0 !important;
        display: grid !important; grid-template-columns: 1fr 1fr !important; gap: 10px !important;
      }
      .ees-mx-fatto {
        background: rgba(255,255,255,0.03) !important; border: 1px solid var(--ees-bordo) !important;
        border-radius: 10px !important; padding: 10px 12px !important; display: flex !important; flex-direction: column !important; gap: 2px !important;
      }
      .ees-mx-fatto span { font-size: 11.5px !important; color: var(--ees-tenue) !important; display: inline-flex !important; align-items: center !important; gap: 5px !important; }
      .ees-mx-fatto strong { font-size: 14px !important; color: #fff !important; }
      .ees-mx-azioni { display: grid !important; grid-template-columns: 1fr 1fr !important; gap: 10px !important; margin-top: 16px !important; }
      .ees-mx-btn {
        display: inline-flex !important; align-items: center !important; justify-content: center !important; gap: 8px !important;
        padding: 13px 18px !important; border-radius: 10px !important; font-size: 14.5px !important; font-weight: 700 !important;
        text-decoration: none !important; cursor: pointer !important; border: 1px solid transparent !important;
      }
      .ees-mx-btn--arancio { background: var(--ees-arancio) !important; color: #fff !important; }
      .ees-mx-btn--contorno { background: #1e2024 !important; color: #fff !important; border-color: rgba(255,255,255,0.22) !important; }
      .ees-mx-blocco {
        margin-top: 26px !important; background: #141416 !important; border: 1px solid var(--ees-bordo) !important;
        border-radius: 14px !important; padding: 22px !important;
      }
      .ees-mx-blocco h2 { margin: 0 0 16px !important; font-size: 19px !important; font-weight: 800 !important; color: #fff !important; }
      .ees-mx-tecnici {
        display: grid !important; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)) !important; gap: 10px 22px !important; margin: 0 !important;
      }
      .ees-mx-tecnici div {
        display: flex !important; justify-content: space-between !important; padding: 8px 0 !important;
        border-bottom: 1px solid rgba(255,255,255,0.08) !important; font-size: 13.5px !important;
      }
      .ees-mx-tecnici dt { color: var(--ees-tenue) !important; }
      .ees-mx-tecnici dd { margin: 0 !important; font-weight: 700 !important; color: #fff !important; text-align: right !important; }
      .ees-mx-equip {
        display: grid !important; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)) !important; gap: 18px !important;
      }
      .ees-mx-equip h3 { margin: 0 0 8px !important; font-size: 14px !important; color: var(--ees-arancio) !important; text-transform: uppercase !important; }
      .ees-mx-equip ul { margin: 0 !important; padding-left: 18px !important; color: #d5d7de !important; font-size: 13.5px !important; line-height: 1.6 !important; }
      .ees-mx-descr { color: #d5d7de !important; font-size: 14.5px !important; line-height: 1.65 !important; }
      .ees-mx-descr p { margin: 0 0 10px !important; }
      /* Modal Scheda Auto (quando aperta dalla Homepage) & Lightbox */
      .ees-mx-overlay {
        position: fixed !important; inset: 0 !important; z-index: 999998 !important;
        background: rgba(5,5,7,0.95) !important; overflow-y: auto !important; padding: 24px 14px 60px !important;
      }
      .ees-mx-lightbox {
        position: fixed !important; inset: 0 !important; z-index: 2147483647 !important;
        background: rgba(0,0,0,0.96) !important; display: flex !important; align-items: center !important; justify-content: center !important;
      }
      .ees-mx-lightbox img { max-width: 90vw !important; max-height: 84vh !important; width: auto !important; height: auto !important; object-fit: contain !important; }
    `;
  }

  /* ---------- Generazione Card Auto ---------- */
  function schedaHtml(a) {
    const giu = ribassato(a);
    const badge = [
      a.stato === 'arrivo'
        ? '<span class="ees-mx-badge ees-mx-badge--arancio">In arrivo</span>'
        : (nuovi.has(a.id) ? '<span class="ees-mx-badge ees-mx-badge--arancio">Nuovo arrivo</span>' : ''),
      giu ? '<span class="ees-mx-badge">Prezzo ribassato</span>' : '',
      a.neopatentati ? '<span class="ees-mx-badge">Neopatentati</span>' : ''
    ].join('');
    const dati = [fmtImm(a.immatricolazione), fmtKm(a.km), a.carburante].filter(Boolean);
    const copertina = foto((a.foto || [])[0], 'media');
    return `
      <article class="ees-mx-card" style="background:#141416 !important;border:1px solid rgba(255,255,255,0.12) !important;border-radius:12px !important;overflow:hidden !important;display:flex !important;flex-direction:column !important;">
        <div class="ees-mx-card__link" role="button" tabindex="0" data-ees-apri-auto="${esc(a.id)}" style="cursor:pointer !important;display:flex !important;flex-direction:column !important;height:100% !important;">
          <div class="ees-mx-card__foto" style="position:relative !important;width:100% !important;height:210px !important;max-height:210px !important;overflow:hidden !important;background:#080809 !important;">
            ${copertina ? `<img src="${esc(copertina)}" alt="${esc(titoloCompleto(a))}" loading="lazy" decoding="async" width="720" height="540" style="width:100% !important;height:210px !important;max-width:100% !important;max-height:210px !important;object-fit:cover !important;display:block !important;">` : ''}
            ${badge ? `<div class="ees-mx-card__badge">${badge}</div>` : ''}
            <span class="ees-mx-card__conta">${ICO.foto}${(a.foto || []).length}</span>
          </div>
          <div class="ees-mx-card__testo">
            <h3 class="ees-mx-card__titolo">${esc(titoloCompleto(a))}</h3>
            <p class="ees-mx-card__dati">${dati.map(esc).join(' · ')}</p>
            <p class="ees-mx-card__prezzo">${giu ? `<s>${esc(fmtPrezzo(giu.da))}</s>` : ''}${esc(fmtPrezzo(a.prezzo))}</p>
          </div>
        </div>
      </article>`;
  }

  function collegaCarosello(contenitore) {
    const binario = $('.ees-mx-binario', contenitore);
    if (!binario) return;
    const frecce = $$('[data-ees-verso]', contenitore);
    const aggiorna = () => {
      const fine = binario.scrollWidth - binario.clientWidth - 2;
      frecce.forEach(b => {
        b.disabled = Number(b.dataset.eesVerso) < 0 ? binario.scrollLeft <= 2 : binario.scrollLeft >= fine;
      });
    };
    frecce.forEach(b => b.addEventListener('click', () => {
      binario.scrollBy({ left: Number(b.dataset.eesVerso) * binario.clientWidth * 0.88, behavior: 'smooth' });
    }));
    binario.addEventListener('scroll', aggiorna, { passive: true });
    window.addEventListener('resize', aggiorna);
    setTimeout(aggiorna, 40);
  }

  /* ---------- BLOCCO 1: Homepage - Divisione Auto (In Salone) ---------- */
  function disegnaBloccoSalone(box) {
    box.classList.add('ees-mx-root');
    const inSalone = annunci
      .filter(a => (a.stato || 'salone') === 'salone')
      .sort(confrontaDaDashboard);

    if (!inSalone.length) {
      box.innerHTML = '';
      return;
    }
    box.innerHTML = `
      <div class="ees-mx-vista-lista" data-ees-vista-lista>
        <div class="ees-mx-carosello">
          <div class="ees-mx-binario" aria-label="Auto disponibili in salone">
            ${inSalone.map(schedaHtml).join('')}
          </div>
          <button class="ees-mx-freccia ees-mx-freccia--sx" type="button" data-ees-verso="-1" aria-label="Precedenti">${ICO.sx}</button>
          <button class="ees-mx-freccia ees-mx-freccia--dx" type="button" data-ees-verso="1" aria-label="Successive">${ICO.dx}</button>
        </div>
      </div>
      <div class="ees-mx-scheda-inline" data-ees-scheda-inline style="display:none !important;"></div>`;
    collegaCarosello(box);
  }

  /* ---------- BLOCCO 2: Homepage - Vetture in Arrivo (Auto-Hide se 0) ---------- */
  function disegnaBloccoArrivo(box) {
    box.classList.add('ees-mx-root');
    const inArrivo = annunci
      .filter(a => a.stato === 'arrivo')
      .sort(confrontaDaDashboard);

    // Se siamo dentro una riga dedicata di Duda (.dmRespRow) o una <section>, la nascondiamo/mostriamo per intero
    const rigaDuda = box.closest('.dmRespRow') || box.closest('section');
    const nascondiRiga = box.dataset.nascondiRiga !== 'false';

    if (!inArrivo.length) {
      box.innerHTML = '';
      box.style.display = 'none';
      if (rigaDuda && nascondiRiga && !rigaDuda.querySelector('#ees-home-salone')) {
        rigaDuda.style.display = 'none';
      }
      return;
    }

    box.style.display = '';
    if (rigaDuda) rigaDuda.style.display = '';

    box.innerHTML = `
      <div class="ees-mx-vista-lista" data-ees-vista-lista>
        <div class="ees-mx-carosello">
          <div class="ees-mx-binario" aria-label="Vetture in arrivo">
            ${inArrivo.map(schedaHtml).join('')}
          </div>
          <button class="ees-mx-freccia ees-mx-freccia--sx" type="button" data-ees-verso="-1" aria-label="Precedenti">${ICO.sx}</button>
          <button class="ees-mx-freccia ees-mx-freccia--dx" type="button" data-ees-verso="1" aria-label="Successive">${ICO.dx}</button>
        </div>
      </div>
      <div class="ees-mx-scheda-inline" data-ees-scheda-inline style="display:none !important;"></div>`;
    collegaCarosello(box);
  }

  /* ---------- BLOCCO 3: Pagina Autovetture (Catalogo + Filtri + Scheda) ---------- */
  function marcheDisponibili() {
    const m = new Map();
    annunci.forEach(a => m.set(a.marca, (m.get(a.marca) || 0) + 1));
    return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }

  function filtraRisultati() {
    const parole = normalizza(filtro.testo).split(/\s+/).filter(Boolean);
    return annunci.filter(a => {
      if (filtro.marca && a.marca !== filtro.marca) return false;
      if (filtro.stato && (a.stato || 'salone') !== filtro.stato) return false;
      if (filtro.categoria && a.carrozzeria !== filtro.categoria) return false;
      const t = normalizza([a.marca, a.modello, a.versione, a.sottotitolo, a.carburante, a.cambio, a.carrozzeria, a.colore].join(' '));
      return parole.every(p => t.includes(p));
    }).sort(ORDINI[filtro.ordine] || ORDINI.autoscout);
  }

  function disegnaBloccoCatalogo(box) {
    box.classList.add('ees-mx-root');
    if (!$('.ees-mx-catalogo-wrap', box)) {
      box.innerHTML = `
        <div class="ees-mx-catalogo-wrap ees-mx-vista-lista" data-ees-vista-lista>
          <div class="ees-mx-strumenti">
            <label class="ees-mx-cerca">
              ${ICO.cerca}
              <input type="search" data-ees-cerca placeholder="Cerca marca, modello, versione, cambio…" autocomplete="off">
            </label>
            <label class="ees-mx-select-wrap">
              <span>Mostra</span>
              <select data-ees-stato>
                <option value="">Tutte le auto</option>
                <option value="salone">Disponibili in salone</option>
                <option value="arrivo">Vetture in arrivo</option>
              </select>
            </label>
            <label class="ees-mx-select-wrap">
              <span>Categoria</span>
              <select data-ees-categoria><option value="">Tutte le categorie</option></select>
            </label>
            <label class="ees-mx-select-wrap">
              <span>Ordina per</span>
              <select data-ees-ordine>
                <option value="default">Default</option>
                <option value="recenti">Ultimi arrivi</option>
                <option value="prezzoSu">Prezzo più basso</option>
                <option value="prezzoGiu">Prezzo più alto</option>
                <option value="km">Meno chilometri</option>
                <option value="anno">Più recenti</option>
                <option value="potenza">Più potenti</option>
              </select>
            </label>
          </div>
          <div class="ees-mx-chips" data-ees-chips></div>
          <div class="ees-mx-barra-stato">
            <span data-ees-conta></span>
            <button type="button" class="ees-mx-link-btn" data-ees-azzera hidden>Azzera filtri</button>
          </div>
          <div class="ees-mx-griglia" data-ees-griglia></div>
        </div>
        <div class="ees-mx-scheda-inline" data-ees-scheda-inline style="display:none !important;"></div>`;

      $('[data-ees-cerca]', box).addEventListener('input', e => { filtro.testo = e.target.value; aggiornaRisultatiCatalogo(box); });
      $('[data-ees-stato]', box).addEventListener('change', e => { filtro.stato = e.target.value; aggiornaRisultatiCatalogo(box); });
      $('[data-ees-categoria]', box).addEventListener('change', e => { filtro.categoria = e.target.value; aggiornaRisultatiCatalogo(box); });
      $('[data-ees-ordine]', box).addEventListener('change', e => { filtro.ordine = e.target.value; aggiornaRisultatiCatalogo(box); });
      $('[data-ees-chips]', box).addEventListener('click', e => {
        const b = e.target.closest('button[data-marca]');
        if (!b) return;
        filtro.marca = b.dataset.marca;
        aggiornaChipCatalogo(box);
        aggiornaRisultatiCatalogo(box);
      });
      $('[data-ees-azzera]', box).addEventListener('click', () => {
        filtro.testo = ''; filtro.marca = ''; filtro.stato = ''; filtro.categoria = '';
        $('[data-ees-cerca]', box).value = '';
        $('[data-ees-stato]', box).value = '';
        $('[data-ees-categoria]', box).value = '';
        aggiornaChipCatalogo(box);
        aggiornaRisultatiCatalogo(box);
      });
    }
    aggiornaCategorieCatalogo(box);
    aggiornaChipCatalogo(box);
    aggiornaRisultatiCatalogo(box);
  }

  function aggiornaCategorieCatalogo(box) {
    const sel = $('[data-ees-categoria]', box);
    if (!sel) return;
    const catMap = new Map();
    annunci.forEach(a => { if (a.carrozzeria) catMap.set(a.carrozzeria, (catMap.get(a.carrozzeria) || 0) + 1); });
    sel.innerHTML = '<option value="">Tutte le categorie</option>' +
      Array.from(catMap.entries()).sort((a, b) => b[1] - a[1]).map(([c, n]) => `<option value="${esc(c)}">${esc(c)} (${n})</option>`).join('');
    sel.value = filtro.categoria;
  }

  function aggiornaChipCatalogo(box) {
    const chips = $('[data-ees-chips]', box);
    if (!chips) return;
    const chip = (val, et, n) => `<button type="button" class="ees-mx-chip" data-marca="${esc(val)}" aria-pressed="${filtro.marca === val}">${esc(et)} <span class="ees-mx-chip__n">${n}</span></button>`;
    chips.innerHTML = [chip('', 'Tutte', annunci.length)]
      .concat(marcheDisponibili().map(([m, n]) => chip(m, m, n))).join('');
  }

  function aggiornaRisultatiCatalogo(box) {
    const elenco = filtraRisultati();
    const griglia = $('[data-ees-griglia]', box);
    if (griglia) griglia.innerHTML = elenco.map(schedaHtml).join('');
    const conta = $('[data-ees-conta]', box);
    if (conta) {
      conta.textContent = elenco.length === annunci.length
        ? `${annunci.length} auto disponibili`
        : `${elenco.length} di ${annunci.length} auto`;
    }
    const azzera = $('[data-ees-azzera]', box);
    if (azzera) azzera.hidden = !(filtro.marca || filtro.stato || filtro.categoria || filtro.testo.trim());
  }

  /* ---------- Scheda Completa Singola Auto + Galleria 50 foto ---------- */
  function blocchiTesto(lista) {
    return (lista || []).map(b => {
      if (b.tipo === 'titolo') return `<h3>${esc(b.testo)}</h3>`;
      if (b.tipo === 'elenco') return `<ul>${b.voci.map(v => `<li>${esc(v)}</li>`).join('')}</ul>`;
      const t = (b.parti || []).map(([p, g]) => {
        const h = esc(p).replace(/\n/g, '<br>');
        return g ? `<strong>${h}</strong>` : h;
      }).join('');
      return `<p>${t}</p>`;
    }).join('');
  }

  function htmlSchedaCompleta(a) {
    const n = (a.foto || []).length;
    const nome = titoloCompleto(a);
    const msg = `Buongiorno, vorrei informazioni sulla ${nome} (${fmtPrezzo(a.prezzo)}).`;
    const wa = linkWhatsApp(msg);
    const giu = ribassato(a);
    const riepilogo = [
      ['Chilometraggio', fmtKm(a.km), ICO.strada],
      ['Cambio', a.cambio, ICO.cambio],
      ['Immatricolazione', fmtImm(a.immatricolazione), ICO.calendario],
      ['Carburante', a.carburante, ICO.carburante],
      ['Potenza', a.kw ? `${a.kw} kW (${a.cv} CV)` : null, ICO.potenza],
      ['Carrozzeria', a.carrozzeria, ICO.auto]
    ].filter(([, v]) => v);

    const righeTecniche = [
      ['Condizione', a.condizione],
      ['Immatricolazione', fmtImm(a.immatricolazione)],
      ['Chilometraggio', fmtKm(a.km)],
      ['Carrozzeria', a.carrozzeria],
      ['Colore', [a.colore, a.vernice && a.vernice.toLowerCase()].filter(Boolean).join(' ')],
      ['Interni', a.interni],
      ['Porte / Posti', [a.porte ? `${a.porte} porte` : '', a.posti ? `${a.posti} posti` : ''].filter(Boolean).join(' · ')],
      ['Carburante', a.carburante],
      ['Potenza', a.cv ? `${a.cv} CV (${a.kw} kW)` : null],
      ['Cambio', a.cambio ? a.cambio + (a.marce ? ` · ${a.marce} marce` : '') : null],
      ['Trazione', a.trazione],
      ['Cilindrata', a.cilindrata ? `${numero(a.cilindrata)} cm³` : null],
      ['Classe emissioni', a.classeEmissioni],
      ['Garanzia', a.garanzia]
    ].filter(([, v]) => v);

    const altre = annunci.filter(x => x.id !== a.id).slice(0, 4);

    return `
      <div style="width:100% !important;max-width:1240px !important;margin:0 auto !important;overflow:hidden !important;background:#0e0f12 !important;border:1px solid rgba(255,255,255,0.14) !important;border-radius:16px !important;padding:22px !important;">
      <div class="ees-mx-scheda-top" style="display:flex !important;justify-content:space-between !important;align-items:center !important;flex-wrap:wrap !important;gap:12px !important;margin-bottom:20px !important;padding-bottom:14px !important;border-bottom:1px solid rgba(255,255,255,0.12) !important;">
        <button type="button" class="ees-mx-torna" data-ees-chiudi-scheda style="display:inline-flex !important;align-items:center !important;gap:8px !important;background:#1a1b1e !important;color:#fff !important;border:1px solid rgba(255,255,255,0.2) !important;padding:9px 16px !important;border-radius:999px !important;font-size:13.5px !important;font-weight:700 !important;cursor:pointer !important;">${ICO.sx} Torna a tutte le auto</button>
        <span style="font-size:13px;color:var(--ees-tenue)">${esc(a.marca)} / <strong style="color:#fff">${esc(a.modello)}</strong></span>
      </div>

      <div class="ees-mx-dettaglio" style="display:grid !important;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr) !important;gap:24px !important;align-items:start !important;width:100% !important;max-width:100% !important;">
        <div style="min-width:0 !important;width:100% !important;max-width:100% !important;overflow:hidden !important;">
          <div class="ees-mx-palco" data-ees-palco style="position:relative !important;width:100% !important;max-width:100% !important;height:400px !important;max-height:400px !important;background:#070708 !important;border-radius:12px !important;overflow:hidden !important;border:1px solid rgba(255,255,255,0.12) !important;">
            ${n ? `<img data-ees-foto-grande src="${esc(foto(a.foto[0], 'grande'))}" alt="${esc(nome)}" width="800" height="600" style="width:100% !important;height:400px !important;max-width:100% !important;max-height:400px !important;object-fit:contain !important;background:#070708 !important;display:block !important;cursor:zoom-in !important;margin:0 auto !important;">` : ''}
            ${n > 1 ? `
              <button class="ees-mx-freccia ees-mx-freccia--sx" type="button" data-ees-passo="-1" aria-label="Foto precedente">${ICO.sx}</button>
              <button class="ees-mx-freccia ees-mx-freccia--dx" type="button" data-ees-passo="1" aria-label="Foto successiva">${ICO.dx}</button>` : ''}
            ${n ? `<span class="ees-mx-palco__pill" data-ees-contatore>1 / ${n}</span>
              <button type="button" class="ees-mx-palco__zoom" data-ees-zoom>${ICO.zoom} Schermo intero</button>` : ''}
          </div>
          ${n > 1 ? `<div class="ees-mx-miniature" data-ees-miniature style="display:flex !important;flex-direction:row !important;flex-wrap:nowrap !important;width:100% !important;max-width:100% !important;height:80px !important;max-height:80px !important;gap:8px !important;overflow-x:auto !important;overflow-y:hidden !important;padding:10px 2px !important;align-items:center !important;">
            ${a.foto.map((f, i) => `<button type="button" class="ees-mx-miniatura" data-ees-indice="${i}" aria-current="${i === 0}" style="width:78px !important;min-width:78px !important;max-width:78px !important;height:58px !important;min-height:58px !important;max-height:58px !important;flex:0 0 78px !important;border-radius:6px !important;overflow:hidden !important;padding:0 !important;margin:0 !important;background:#000 !important;cursor:pointer !important;display:inline-block !important;"><img src="${esc(foto(f, 'mini'))}" alt="" loading="lazy" width="78" height="58" style="width:78px !important;height:58px !important;max-width:78px !important;max-height:58px !important;object-fit:cover !important;display:block !important;margin:0 !important;"></button>`).join('')}
          </div>` : ''}
        </div>

        <aside class="ees-mx-riepilogo">
          <p class="ees-mx-riepilogo__marca">${esc(a.marca)} ${a.stato === 'arrivo' ? '· <span class="ees-mx-badge ees-mx-badge--arancio">Vettura in arrivo</span>' : ''}</p>
          <h1 class="ees-mx-riepilogo__titolo">${esc(a.modello)}</h1>
          <p class="ees-mx-riepilogo__versione">${esc(a.versione || '')}</p>
          <p class="ees-mx-riepilogo__prezzo">${giu ? `<s style="font-size:16px;color:#999;margin-right:8px">${esc(fmtPrezzo(giu.da))}</s>` : ''}${esc(fmtPrezzo(a.prezzo))}</p>
          <ul class="ees-mx-fatti">
            ${riepilogo.map(([k, v, ico]) => `<li class="ees-mx-fatto"><span>${ico}${esc(k)}</span><strong>${esc(v)}</strong></li>`).join('')}
          </ul>
          <div class="ees-mx-azioni">
            <a class="ees-mx-btn ees-mx-btn--arancio" href="${esc(CONTATTI.telefonoHref)}">${ICO.telefono} Chiama</a>
            <a class="ees-mx-btn ees-mx-btn--contorno" href="${esc(wa)}" target="_blank" rel="noopener">${ICO.whatsapp} WhatsApp</a>
          </div>
        </aside>
      </div>

      <section class="ees-mx-blocco">
        <h2>Dati tecnici</h2>
        <dl class="ees-mx-tecnici">
          ${righeTecniche.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}
        </dl>
      </section>

      ${(a.accessori || []).length ? `
      <section class="ees-mx-blocco">
        <h2>Equipaggiamento</h2>
        <div class="ees-mx-equip">
          ${a.accessori.map(g => `<div><h3>${esc(g.categoria)}</h3><ul>${g.voci.map(v => `<li>${esc(v)}</li>`).join('')}</ul></div>`).join('')}
        </div>
      </section>` : ''}

      ${(a.descrizione || []).length ? `
      <section class="ees-mx-blocco">
        <h2>Descrizione</h2>
        <div class="ees-mx-descr">${blocchiTesto(a.descrizione)}</div>
      </section>` : ''}

      ${altre.length ? `
      <section class="ees-mx-blocco">
        <h2>Altre auto disponibili</h2>
        <div class="ees-mx-griglia">${altre.map(schedaHtml).join('')}</div>
      </section>` : ''}
      </div>`;
  }

  function attivaInterazioniScheda(contenitore, a, onChiudi) {
    let idx = 0;
    const n = (a.foto || []).length;
    const vaiA = nuovo => {
      if (!n) return;
      idx = (nuovo + n) % n;
      const img = $('[data-ees-foto-grande]', contenitore);
      if (img) img.src = foto(a.foto[idx], 'grande');
      const cont = $('[data-ees-contatore]', contenitore);
      if (cont) cont.textContent = `${idx + 1} / ${n}`;
      $$('[data-ees-indice]', contenitore).forEach((b, k) => b.setAttribute('aria-current', String(k === idx)));
      const minAttiva = $(`[data-ees-indice="${idx}"]`, contenitore);
      if (minAttiva) minAttiva.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    };

    const btnChiudi = $('[data-ees-chiudi-scheda]', contenitore);
    if (btnChiudi) btnChiudi.addEventListener('click', onChiudi);

    $$('[data-ees-passo]', contenitore).forEach(b => b.addEventListener('click', () => vaiA(idx + Number(b.dataset.eesPasso))));
    $$('[data-ees-indice]', contenitore).forEach(b => b.addEventListener('click', () => vaiA(Number(b.dataset.eesIndice))));

    const apriZoom = () => {
      if (!n) return;
      const lb = document.createElement('div');
      lb.className = 'ees-mx-lightbox ees-mx-modal';
      lb.setAttribute('style', 'position:fixed !important;inset:0 !important;width:100vw !important;height:100vh !important;z-index:2147483647 !important;background:rgba(0,0,0,0.96) !important;display:flex !important;align-items:center !important;justify-content:center !important;');
      const disegnaLb = () => {
        lb.innerHTML = `
          <img src="${esc(foto(a.foto[idx], 'piena'))}" alt="" style="max-width:90vw !important;max-height:84vh !important;width:auto !important;height:auto !important;object-fit:contain !important;display:block !important;">
          <button type="button" class="ees-mx-freccia ees-mx-freccia--sx" style="left:18px !important" data-lb="-1">${ICO.sx}</button>
          <button type="button" class="ees-mx-freccia ees-mx-freccia--dx" style="right:18px !important" data-lb="1">${ICO.dx}</button>
          <button type="button" class="ees-mx-freccia" style="top:24px !important;right:18px !important;transform:none !important" data-lb-close>${ICO.chiudi}</button>`;
        $$('[data-lb]', lb).forEach(b => b.addEventListener('click', e => { e.stopPropagation(); vaiA(idx + Number(b.dataset.lb)); disegnaLb(); }));
        $('[data-lb-close]', lb).addEventListener('click', () => lb.remove());
      };
      lb.addEventListener('click', e => { if (e.target === lb) lb.remove(); });
      document.body.appendChild(lb);
      disegnaLb();
    };

    const btnZoom = $('[data-ees-zoom]', contenitore);
    const imgGrande = $('[data-ees-foto-grande]', contenitore);
    if (btnZoom) btnZoom.addEventListener('click', apriZoom);
    if (imgGrande) imgGrande.addEventListener('click', apriZoom);
  }

  let autoApertaId = null;
  let boxAperto = null;

  function chiudiSchedaInline() {
    autoApertaId = null;
    $$('.ees-mx-root').forEach(b => {
      const w = $('[data-ees-vista-lista]', b);
      const s = $('[data-ees-scheda-inline]', b);
      if (w) w.setAttribute('style', 'display:block !important;');
      if (s) { s.setAttribute('style', 'display:none !important;'); s.innerHTML = ''; }
    });
    const vecchioOverlay = $('#ees-mx-overlay-scheda');
    if (vecchioOverlay) vecchioOverlay.remove();
    document.body.style.overflow = '';
  }

  function trovaLinkPaginaAutovetture() {
    return document.getElementById('1793519757') ||
           $$('a').find(el => /^vedi tutte le auto$/i.test((el.textContent || '').trim())) ||
           $$('a').find(el => /^autovetture$/i.test((el.textContent || '').trim()));
  }

  function leggiAutoDaAprire() {
    try {
      const s = sessionStorage.getItem('ees_apri_auto_id');
      if (s) {
        sessionStorage.removeItem('ees_apri_auto_id');
        localStorage.removeItem('ees_apri_auto_id');
        return s;
      }
    } catch (e) {}
    try {
      const raw = localStorage.getItem('ees_apri_auto_id');
      if (raw) {
        localStorage.removeItem('ees_apri_auto_id');
        const obj = JSON.parse(raw);
        if (obj && obj.id && (Date.now() - (obj.ts || 0) < 30000)) return obj.id;
      }
    } catch (e) {}
    const m = location.hash.match(/^#auto\/([A-Za-z0-9-]+)$/) ||
              (new URLSearchParams(location.search).get('auto') ? [null, new URLSearchParams(location.search).get('auto')] : null);
    return m && m[1] ? m[1] : null;
  }

  function apriSchedaAuto(idAuto, origineEl) {
    const boxCatalogo = $('#ees-catalogo-completo, [data-ees-blocco="catalogo"]');

    // Se siamo sulla Homepage (dove non c'è #ees-catalogo-completo), salva l'ID dell'auto e porta alla pagina Autovetture!
    if (!boxCatalogo && idAuto) {
      try { sessionStorage.setItem('ees_apri_auto_id', idAuto); } catch (e) {}
      try { localStorage.setItem('ees_apri_auto_id', JSON.stringify({ id: idAuto, ts: Date.now() })); } catch (e) {}
      const linkDest = trovaLinkPaginaAutovetture();
      if (linkDest) {
        linkDest.click();
      } else {
        window.location.href = '/nuova-pagina';
      }
      return;
    }

    const a = annunci.find(x => x.id === idAuto);
    if (!a) {
      chiudiSchedaInline();
      return;
    }

    autoApertaId = idAuto;
    const targetBox = boxCatalogo ||
                      (origineEl && origineEl.closest('.ees-mx-root')) ||
                      boxAperto;

    if (targetBox) {
      boxAperto = targetBox;
      const wrap = $('[data-ees-vista-lista]', targetBox);
      const inline = $('[data-ees-scheda-inline]', targetBox);
      if (wrap && inline) {
        wrap.setAttribute('style', 'display:none !important;');
        inline.setAttribute('style', 'display:block !important;width:100% !important;max-width:100% !important;overflow:hidden !important;');
        inline.innerHTML = htmlSchedaCompleta(a);
        attivaInterazioniScheda(inline, a, () => {
          chiudiSchedaInline();
          targetBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        targetBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }
    }
  }

  window.__EES_APRI_AUTO__ = apriSchedaAuto;

  if (!window.__EES_CLICK_BOUND__) {
    window.__EES_CLICK_BOUND__ = true;
    document.addEventListener('click', e => {
      const link = e.target.closest('[data-ees-apri-auto]');
      if (!link) return;
      e.preventDefault();
      e.stopPropagation();
      if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
      const id = link.dataset.eesApriAuto;
      if (typeof window.__EES_APRI_AUTO__ === 'function') window.__EES_APRI_AUTO__(id, link);
    }, true);

    document.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const link = e.target.closest('[data-ees-apri-auto]');
      if (!link) return;
      e.preventDefault();
      e.stopPropagation();
      if (typeof window.__EES_APRI_AUTO__ === 'function') window.__EES_APRI_AUTO__(link.dataset.eesApriAuto, link);
    }, true);
  }

  /* ---------- Rendering Globale e Sincronizzazione Live ---------- */
  function calcolaImpronta(lista, ord) {
    return `${ord || 'autoscout'}||` + lista.map(a => `${a.id}:${a.stato || 'salone'}:${(a.foto || [])[0] || ''}:${(a.foto || []).length}:${a.prezzo}`).join('|');
  }

  function disegnaTutto() {
    iniettaStili();
    $$('#ees-home-salone, [data-ees-blocco="salone"]').forEach(disegnaBloccoSalone);
    $$('#ees-home-arrivo, [data-ees-blocco="arrivo"]').forEach(disegnaBloccoArrivo);
    $$('#ees-catalogo-completo, [data-ees-blocco="catalogo"]').forEach(disegnaBloccoCatalogo);

    const boxCatalogo = $('#ees-catalogo-completo, [data-ees-blocco="catalogo"]');
    if (boxCatalogo) {
      if (autoApertaId) {
        apriSchedaAuto(autoApertaId);
      } else {
        const idDaAprire = leggiAutoDaAprire();
        if (idDaAprire) apriSchedaAuto(idDaAprire);
      }
    }
  }

  function applicaNuoviDati(d) {
    if (!d || !Array.isArray(d.annunci)) return;
    const ord = d.ordineSito || 'autoscout';
    const nuovaImpronta = calcolaImpronta(d.annunci, ord);
    if (nuovaImpronta !== ultimaImpronta) {
      ultimaImpronta = nuovaImpronta;
      ordineSito = ord;
      annunciTutti = d.annunci;
      annunci = annunciTutti.filter(a => a.stato !== 'venduta');
      if (d.variazioni) {
        variazioni = d.variazioni;
        nuovi = new Set(Array.isArray(variazioni.nuovi) ? variazioni.nuovi : []);
        cambiPrezzo = new Map((Array.isArray(variazioni.prezzi) ? variazioni.prezzi : []).map(p => [p.id, p]));
      }
      disegnaTutto();
    }
  }

  let ultimoCheckCloud = 0;
  async function sincronizzaConCloud(forza = false) {
    if (!CLOUD_ORIGIN || serverLocaleAttivo) return;
    const ora = Date.now();
    if (!forza && ora - ultimoCheckCloud < 30000) return;
    ultimoCheckCloud = ora;
    try {
      const resp = await fetch(`${CLOUD_ORIGIN}/repost/dati/annunci.json?t=${Math.floor(ora / 30000)}`, { cache: 'no-store' });
      if (!resp.ok) return;
      const d = await resp.json();
      if (!serverLocaleAttivo) {
        applicaNuoviDati(d);
      }
    } catch (e) {
      // Silenzioso se offline
    }
  }

  async function sincronizzaConDashboardLocale() {
    if (SOLO_DA_GITHUB) return;
    try {
      const resp = await fetch(`${API_ORIGIN}/api/stato`, { cache: 'no-store' });
      if (!resp.ok) return;
      const d = await resp.json();
      if (d && d.ok && Array.isArray(d.annunci)) {
        serverLocaleAttivo = true;
        applicaNuoviDati(d);
      }
    } catch (e) {
      serverLocaleAttivo = false;
    }
  }

  window.__EES_MOTOREXPO_REFRESH__ = disegnaTutto;

  if (annunciTutti.length) {
    ultimaImpronta = calcolaImpronta(annunciTutti, ordineSito);
    disegnaTutto();
  }
  sincronizzaConCloud(true);
  sincronizzaConDashboardLocale();

  // Se la Dashboard locale è attiva sul PC, aggiorna ogni 2 secondi; altrimenti controlla il Cloud H24 ogni 30 secondi
  window.__EES_TIMER__ = setInterval(() => {
    if (serverLocaleAttivo) {
      sincronizzaConDashboardLocale();
    } else {
      sincronizzaConCloud(false);
    }
  }, 2000);
  window.addEventListener('focus', () => {
    sincronizzaConDashboardLocale();
    sincronizzaConCloud(true);
  });
  if (typeof BroadcastChannel !== 'undefined') {
    const bc = new BroadcastChannel('repost_live');
    bc.onmessage = sincronizzaConDashboardLocale;
  }
})();
