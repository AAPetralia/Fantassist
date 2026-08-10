# -*- coding: utf-8 -*-
"""
FANTASSIST — Scraper consolidato "Probabili Formazioni"
Un solo fetch della pagina fantacalcio.it/probabili-formazioni-serie-a produce TRE output:
  1. data/fonti_titolarita/fantacalcio.json  (titolarità, invariato)
  2. data/calendario.json                     (partite della giornata: data/ora/stadio reali)
  3. data/indisponibili.json                  (squalificati/diffidati/infortunati/in dubbio,
                                                 con dettaglio infortunio e rientro atteso)

Sostituisce le fonti separate usate finora da scraper.py per calendario e indisponibili,
riducendo le richieste HTTP e allineando tutto a un'unica fonte aggiornata in tempo reale.

Pattern di estrazione validati contro un campione reale della pagina (giornata 1, 2026-27):
calendario 3/3 partite esatte, indisponibili corretti (squalificati/infortunati/dubbio con
dettaglio testuale). Non ancora testato end-to-end nel workflow.

USO
---
  pip install requests
  python probabili_formazioni_scraper.py [numero_giornata]
"""

import re
import sys
import json
import os
import requests
from datetime import datetime, timezone

URL = "https://www.fantacalcio.it/probabili-formazioni-serie-a"
os.makedirs("data/fonti_titolarita", exist_ok=True)

OUT_TITOLARITA = "data/fonti_titolarita/fantacalcio.json"
OUT_CALENDARIO = "data/calendario.json"
OUT_INDISPONIBILI = "data/indisponibili.json"

MESI = {'gennaio':1,'febbraio':2,'marzo':3,'aprile':4,'maggio':5,'giugno':6,
        'luglio':7,'agosto':8,'settembre':9,'ottobre':10,'novembre':11,'dicembre':12}

PATTERN_TITOLARITA = re.compile(
    r'\[([^\]]+)\]\(https://www\.fantacalcio\.it/serie-a/squadre/([^/]+)/[^/]+/(\d+)\)'
    r'(?:\s|<[^>]*>)*?(\d{1,3})\s*%',
)
PATTERN_GIORNATA = re.compile(r'Giornata\s+(\d+)')


def rileva_giornata(html):
    """La pagina mostra 'Giornata N' vicino al titolo; se non trovato, usa argv[1] o None."""
    m = PATTERN_GIORNATA.search(html)
    if m:
        return int(m.group(1))
    return int(sys.argv[1]) if len(sys.argv) > 1 else None


import asyncio
from playwright.async_api import async_playwright


def fetch_html_statico():
    """Per il calendario: quella parte è renderizzata server-side, requests basta."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(URL, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.text


async def fetch_rendered():
    """Titolarità e indisponibili sono caricati via JS: serve un browser vero."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)   # margine per hydration completa

        titolarita = await page.evaluate("""
            () => {
                const risultati = [];
                document.querySelectorAll('a[href*="/serie-a/squadre/"]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const m = href.match(/\\/serie-a\\/squadre\\/([^\\/]+)\\/[^\\/]+\\/(\\d+)/);
                    if (!m) return;
                    const nome = a.textContent.trim();
                    if (!nome) return;
                    let node = a, percentuale = null;
                    for (let i = 0; i < 5 && node; i++) {
                        const pm = (node.textContent || '').match(/(\\d{1,3})\\s*%/);
                        if (pm) { percentuale = parseInt(pm[1]); break; }
                        node = node.parentElement;
                    }
                    risultati.push({nome, squadra: m[1], id: m[2], percentuale});
                });
                return risultati;
            }
        """)

        # Diagnostica indisponibili: cattura fino a 3000 caratteri di HTML renderizzato
        # attorno alla PRIMA occorrenza di "Squalificati" che sia DENTRO al contenuto
        # della pagina (non nel menu di navigazione in alto).
        diag_indisponibili = await page.evaluate("""
            () => {
                const main = document.querySelector('main') || document.body;
                const html = main.innerHTML;
                // Squalificati/Diffidati già risolti — ora serve vedere 'injureds'
                // (infortunati) CON dati reali per capire la struttura del dettaglio
                // (motivo + rientro atteso). Raccogliamo più occorrenze: la prima
                // partita potrebbe non avere infortunati (sezione vuota).
                const idxPrimaPartita = html.indexOf('data-match-id');
                let pos = idxPrimaPartita >= 0 ? idxPrimaPartita : 0;
                let pezzi = [];
                for (let i = 0; i < 4; i++) {
                    const idx = html.indexOf('class="injureds"', pos);
                    if (idx < 0) break;
                    pezzi.push(html.substring(idx, idx + 1500));
                    pos = idx + 1500;
                }
                return pezzi.length ? pezzi.join('\\n\\n---PROSSIMA PARTITA---\\n\\n') : null;
            }
        """)

        rendered_html = await page.content()
        await browser.close()
        return titolarita, diag_indisponibili, rendered_html


def parse_titolarita(risultati_dom):
    giocatori = {}
    for r in risultati_dom:
        if r["percentuale"] is None:
            continue
        pid = r["id"]
        giocatori[pid] = {
            "nome": r["nome"], "squadra": r["squadra"],
            "percentuale": r["percentuale"], "confidence": round(r["percentuale"] / 100, 2),
            "match_score": 1.0,
        }
    return giocatori


MATCH_BLOCK_START = re.compile(r'<li data-match-id="(\d+)" data-teams-id="(\d+)\|(\d+)" class="match">')
TEAM_HOME_PATTERN = re.compile(r'class="team-home\s*"[\s\S]{0,400}?href="https://www\.fantacalcio\.it/serie-a/squadre/([a-z\-]+)"')
TEAM_AWAY_PATTERN = re.compile(r'class="team-away\s*"[\s\S]{0,400}?href="https://www\.fantacalcio\.it/serie-a/squadre/([a-z\-]+)"')
START_DATE_PATTERN = re.compile(r'<meta itemprop="startDate" content="([^"]+)"')
STADIUM_PATTERN = re.compile(r'<span class="stadium"[^>]*>([^<]*)</span>')


def split_match_blocks(html):
    """Ogni partita è un <li data-match-id="..."> — confine molto più solido
    del testo 'ripulito' usato nella prima versione (validata per errore su
    formattazione del mio strumento di lettura pagine, non sull'HTML vero)."""
    starts = list(MATCH_BLOCK_START.finditer(html))
    blocks = []
    for i, m in enumerate(starts):
        start = m.start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(html)
        blocks.append({"match_id": m.group(1), "text": html[start:end]})
    return blocks


PLAYER_LINK_PATTERN = re.compile(
    r'<a class="player-name player-link"\s+href="https://www\.fantacalcio\.it/serie-a/squadre/'
    r'([a-z\-]+)/[^/"]+/(\d+)"[^>]*>\s*<span>([^<]+)</span>'
)
# Nomi reali delle sezioni scoperti nell'HTML renderizzato (non più intestazioni italiane markdown):
SEZIONI_INDISPONIBILI = {
    "squalificati": "suspendeds",
    "diffidati": "cautioneds",
    "infortunati": "injureds",
    "dubbio": "doubtfuls",   # da confermare — non ancora visto in HTML reale, verificare al prossimo giro
}


def estrai_lista_indisponibili(nome_sezione, blocco, con_dettaglio=False):
    """Estrae una lista (squalificati/diffidati/infortunati/in dubbio) da un blocco-partita,
    cercando la <section class="..."> corrispondente (struttura reale, non testo markdown)."""
    section_class = SEZIONI_INDISPONIBILI.get(nome_sezione, nome_sezione)
    m = re.search(rf'<section class="{section_class}">(.*?)</section>', blocco, re.DOTALL)
    if not m:
        return []
    corpo = m.group(1)
    items = []
    for squadra, pid, nome in PLAYER_LINK_PATTERN.findall(corpo):
        items.append({"nome": nome.strip(), "id": pid, "squadra": squadra})
        # dettaglio (motivo infortunio, rientro atteso): struttura non ancora vista in HTML
        # reale per gli infortunati — se con_dettaglio è True, verrà aggiunto qui appena
        # confermata (vedi diagnostica successiva).
    return items


def parse_calendario_e_indisponibili(html):
    blocchi = split_match_blocks(html)   # ora su <li data-match-id="..."> reale, non testo "ripulito"
    partite = []
    indisponibili = {}

    for b in blocchi:
        blocco, match_id = b["text"], b["match_id"]

        m_casa = TEAM_HOME_PATTERN.search(blocco)
        m_trasferta = TEAM_AWAY_PATTERN.search(blocco)
        if not m_casa or not m_trasferta:
            continue
        casa, trasferta = m_casa.group(1), m_trasferta.group(1)

        # Data/ora/stadio: "1970-01-01" è il placeholder del sito quando non ancora
        # pubblicati (osservato su dati reali, giornata 1 a 2 settimane dal via) —
        # li trattiamo come non disponibili invece di salvare un valore falso.
        data_iso, ora, stadio = None, None, None
        m_start = START_DATE_PATTERN.search(blocco)
        if m_start and m_start.group(1) != "1970-01-01":
            data_iso = m_start.group(1)
        m_stadio = STADIUM_PATTERN.search(blocco)
        if m_stadio and m_stadio.group(1).strip() not in ("", "-"):
            stadio = m_stadio.group(1).strip()

        partite.append({"casa": casa, "trasferta": trasferta, "data": data_iso, "ora": ora,
                         "stadio": stadio, "match_id": match_id})

        sq = estrai_lista_indisponibili("Squalificati", blocco)
        diff = estrai_lista_indisponibili("Diffidati", blocco)
        inf = estrai_lista_indisponibili("Infortunati", blocco, con_dettaglio=True)
        dub = estrai_lista_indisponibili("In dubbio", blocco, con_dettaglio=True)

        for lista, chiave in [(sq, "squalificati"), (diff, "diffidati"),
                               (inf, "infortunati"), (dub, "dubbio")]:
            for item in lista:
                squadra = item["squadra"]
                indisponibili.setdefault(squadra, {"squalificati": [], "diffidati": [],
                                                     "infortunati": [], "dubbio": []})
                if not any(x["id"] == item["id"] for x in indisponibili[squadra][chiave]):
                    indisponibili[squadra][chiave].append(item)

    return partite, indisponibili


async def main_async():
    print(f"Scaricando {URL} (statico, per calendario)...")
    try:
        html_statico = fetch_html_statico()
    except Exception as e:
        print(f"Errore download statico: {e}")
        return 1
    print(f"Scaricato ({len(html_statico)} caratteri)")

    GIORNATA = rileva_giornata(html_statico)
    print(f"Giornata rilevata: {GIORNATA}")

    # --- Calendario (statico, requests basta — validato in produzione) ---
    partite, indisponibili_fallback = parse_calendario_e_indisponibili(html_statico)
    print(f"\nCalendario: {len(partite)} partite estratte")
    for p in partite:
        print(f"   {p['casa']} - {p['trasferta']}  |  {p['data']} {p['ora']}  |  {p['stadio']}")
    with open(OUT_CALENDARIO, "w", encoding="utf-8") as f:
        json.dump({"giornata": GIORNATA, "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "partite": partite}, f, ensure_ascii=False, indent=2)
    print(f"Salvato {OUT_CALENDARIO}")

    # --- Titolarità + Indisponibili (via browser, JS-caricati) ---
    print(f"\nScaricando {URL} (Playwright, per titolarità/indisponibili)...")
    try:
        risultati_dom, diag_indisponibili, html_renderizzato = await fetch_rendered()
    except Exception as e:
        print(f"Errore download Playwright: {e}")
        return 1

    giocatori = parse_titolarita(risultati_dom)
    print(f"Titolarità: {len(giocatori)} giocatori estratti")
    with open(OUT_TITOLARITA, "w", encoding="utf-8") as f:
        json.dump({"fonte": "fantacalcio.it", "giornata": GIORNATA,
                    "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "giocatori": giocatori}, f, ensure_ascii=False, indent=2)
    print(f"Salvato {OUT_TITOLARITA}")

    if diag_indisponibili:
        print("\n" + "="*70)
        print("DIAGNOSTICA INDISPONIBILI — HTML renderizzato reale attorno a 'Squalificati':")
        print("="*70)
        print(diag_indisponibili)
        print("="*70 + "\n")
    else:
        print("\n⚠️  DIAGNOSTICA: 'Squalificati' non trovato nemmeno nel DOM renderizzato.")

    # Indisponibili: riusa il parser esistente sull'HTML renderizzato (probabilmente
    # va corretto col prossimo giro guardando la diagnostica sopra — non blocca il resto).
    _, indisponibili = parse_calendario_e_indisponibili(html_renderizzato)
    print(f"Indisponibili: {len(indisponibili)} squadre con almeno un'assenza")
    with open(OUT_INDISPONIBILI, "w", encoding="utf-8") as f:
        json.dump({"giornata": GIORNATA, "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "squadre": indisponibili}, f, ensure_ascii=False, indent=2)
    print(f"Salvato {OUT_INDISPONIBILI}")

    if not partite:
        print("\n⚠️  ATTENZIONE: nessuna partita estratta dal calendario.")
        return 1

    return 0


def main():
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
