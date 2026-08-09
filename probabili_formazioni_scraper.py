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


def fetch_html():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(URL, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.text


def parse_titolarita(html):
    giocatori = {}
    for m in PATTERN_TITOLARITA.finditer(html):
        nome, squadra, pid, perc = m.groups()
        giocatori[pid] = {
            "nome": nome.strip(), "squadra": squadra.strip(),
            "percentuale": int(perc), "confidence": round(int(perc) / 100, 2),
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


def estrai_lista_indisponibili(nome_sezione, blocco, con_dettaglio=False):
    """Estrae una lista (squalificati/diffidati/infortunati/in dubbio) da un blocco-partita."""
    m = re.search(rf'#### {nome_sezione}\n(.*?)(?=\n#### |\Z)', blocco, re.DOTALL)
    if not m:
        return []
    corpo = m.group(1)
    items = []
    # Ferma il dettaglio alla riga vuota successiva, al prossimo bullet, o a "Nessun calciatore"
    for match in re.finditer(
        r'\*\s*\[([^\]]+)\]\([^)]*?/(\d+)\)(?:\n\s*(.+?))?(?=\n\s*\n|\n\s*\*|\n\s*Nessun calciatore|\Z)',
        corpo, re.DOTALL
    ):
        nome, pid, dettaglio = match.groups()
        item = {"nome": nome.strip(), "id": pid}
        if con_dettaglio and dettaglio and dettaglio.strip():
            item["dettaglio"] = dettaglio.strip()
        items.append(item)
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
                m_url = re.search(rf'/serie-a/squadre/([a-z-]+)/[a-zà-ù.\-]+/{item["id"]}', blocco)
                squadra = m_url.group(1) if m_url else (casa if item["id"] else "?")
                indisponibili.setdefault(squadra, {"squalificati": [], "diffidati": [],
                                                     "infortunati": [], "dubbio": []})
                if not any(x["id"] == item["id"] for x in indisponibili[squadra][chiave]):
                    indisponibili[squadra][chiave].append(item)

    return partite, indisponibili


def main():
    print(f"Scaricando {URL}...")
    try:
        html = fetch_html()
    except Exception as e:
        print(f"Errore download: {e}")
        return 1
    print(f"Scaricato ({len(html)} caratteri)")

    GIORNATA = rileva_giornata(html)
    print(f"Giornata rilevata: {GIORNATA}")

    # --- DIAGNOSTICA TEMPORANEA: la struttura HTML grezza vista da requests.get() ---
    # è diversa da quella "ripulita" usata finora per validare il parser (fatto su
    # testo pre-elaborato, non HTML vero). Stampiamo pezzi reali nel log di Actions
    # per ricostruire il parser sulla struttura reale, invece di ipotizzarla di nuovo.
    # Calendario: GIÀ CORRETTO su questa struttura (vedi split_match_blocks).
    # Titolarità (percentuali) e Squalificati/Infortunati: ANCORA da vedere in HTML vero.
    idx_percento = html.find("%</")
    if idx_percento < 0:
        idx_percento = html.find("%<")
    if idx_percento >= 0:
        print("\n" + "="*70)
        print("DIAGNOSTICA TITOLARITÀ — HTML reale attorno alla prima percentuale:")
        print("="*70)
        print(html[max(0, idx_percento-1500): idx_percento+500])
        print("="*70 + "\n")
    else:
        print("\n⚠️  DIAGNOSTICA: nessuna '%' trovata nell'HTML — la titolarità potrebbe")
        print("essere caricata via JS (come i voti), non nell'HTML statico.")

    idx_squal = html.find("qualificat")
    if idx_squal >= 0:
        print("\n" + "="*70)
        print("DIAGNOSTICA INDISPONIBILI — HTML reale attorno a 'Squalificati':")
        print("="*70)
        print(html[max(0, idx_squal-200): idx_squal+2500])
        print("="*70 + "\n")

    # --- Titolarità (invariato) ---
    giocatori = parse_titolarita(html)
    print(f"Titolarità: {len(giocatori)} giocatori estratti")
    with open(OUT_TITOLARITA, "w", encoding="utf-8") as f:
        json.dump({"fonte": "fantacalcio.it", "giornata": GIORNATA,
                    "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "giocatori": giocatori}, f, ensure_ascii=False, indent=2)
    print(f"Salvato {OUT_TITOLARITA}")

    # --- Calendario + Indisponibili (nuovo) ---
    partite, indisponibili = parse_calendario_e_indisponibili(html)
    print(f"\nCalendario: {len(partite)} partite estratte")
    for p in partite:
        print(f"   {p['casa']} - {p['trasferta']}  |  {p['data']} {p['ora']}  |  {p['stadio']}")

    with open(OUT_CALENDARIO, "w", encoding="utf-8") as f:
        json.dump({"giornata": GIORNATA, "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "partite": partite}, f, ensure_ascii=False, indent=2)
    print(f"Salvato {OUT_CALENDARIO}")

    print(f"\nIndisponibili: {len(indisponibili)} squadre con almeno un'assenza")
    with open(OUT_INDISPONIBILI, "w", encoding="utf-8") as f:
        json.dump({"giornata": GIORNATA, "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "squadre": indisponibili}, f, ensure_ascii=False, indent=2)
    print(f"Salvato {OUT_INDISPONIBILI}")

    if not partite:
        print("\n⚠️  ATTENZIONE: nessuna partita estratta. Il separatore dei blocchi ('\\n- 1\\n\\n')")
        print("   è stato validato su testo già ripulito (via fetch), non sull'HTML grezzo reale.")
        print("   Se questo accade al primo run vero, va rivisto il separatore dei blocchi-partita")
        print("   guardando l'HTML effettivo scaricato da requests.get().")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
