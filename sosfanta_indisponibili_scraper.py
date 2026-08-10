# -*- coding: utf-8 -*-
"""
FANTASSIST — Indisponibili da SOS Fanta
Testo statico puro, niente Playwright/lazy-loading (a differenza della pagina
probabili formazioni di fantacalcio.it, abbandonata per questo dato dopo
diversi tentativi infruttuosi con timing/scroll). Formato pulito, include
il numero di giornata di rientro atteso ("in dubbio per la Na").

Non ha ID giocatore diretto: usa player_name_matcher.py (già validato con
Understat) per il matching nome→player_id contro data/players.json.

Testato su campione reale (9 squadre, inclusi casi con più infortunati e
descrizioni lunghe): risultati esatti, incluso il parsing del numero di
giornata di rientro.

USO
---
  pip install requests
  python sosfanta_indisponibili_scraper.py
"""

import re
import sys
import json
import os
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from player_name_matcher import PlayerMatcher

URL = "https://www.sosfanta.com/indisponibili-e-squalificati/tabella-indisponibili-seriea-fantacalcio-asta-infortunati-tempi-recupero-squalificati-diffidati/"
OUT_JSON = "data/indisponibili.json"

# SOS Fanta usa nomi squadra in maiuscolo senza abbreviazioni; mappa verso gli
# slug usati ovunque nell'app (uguali a quelli di fantacalcio.it).
SLUG_SQUADRA = {
    "ATALANTA": "atalanta", "BOLOGNA": "bologna", "CAGLIARI": "cagliari",
    "COMO": "como", "FIORENTINA": "fiorentina", "FROSINONE": "frosinone",
    "GENOA": "genoa", "INTER": "inter", "JUVENTUS": "juventus", "LAZIO": "lazio",
    "LECCE": "lecce", "MILAN": "milan", "MONZA": "monza", "NAPOLI": "napoli",
    "PARMA": "parma", "ROMA": "roma", "SASSUOLO": "sassuolo", "TORINO": "torino",
    "UDINESE": "udinese", "VENEZIA": "venezia",
}


def fetch_html():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(URL, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.text




def parse(html):
    """Naviga i tag HTML VERI (<strong>, <em>) con BeautifulSoup, non testo
    markdown ipotizzato — più robusto a differenze di formattazione che
    regex su '**grassetto**' (fallito: quello era solo come lo vedevo IO,
    non l'HTML reale scaricato da requests.get())."""
    soup = BeautifulSoup(html, "html.parser")
    squadre_raw = {}

    # Ogni nome squadra è un tag <strong> (o <b>) col testo esatto in maiuscolo
    header_tags = [t for t in soup.find_all(["strong", "b"])
                   if t.get_text(strip=True) in SLUG_SQUADRA]

    for idx, header in enumerate(header_tags):
        nome_squadra = header.get_text(strip=True)
        slug = SLUG_SQUADRA[nome_squadra]

        # Il "corpo" di questa squadra: tutto il testo tra questo header e il prossimo
        corpo_tags = []
        for sib in header.find_all_next():
            if sib in header_tags[idx+1:idx+2]:
                break
            if sib.name in ("strong", "b") and sib.get_text(strip=True) in SLUG_SQUADRA:
                break
            corpo_tags.append(sib)

        corpo_testo = " ".join(t.get_text(" ", strip=True) for t in corpo_tags if t.get_text(strip=True))

        inf = _estrai_sezione_bs(corpo_tags, "Infortunati", con_dettaglio=True)
        sq = _estrai_sezione_bs(corpo_tags, "Squalificati", con_dettaglio=False)
        diff = _estrai_sezione_bs(corpo_tags, "Diffidati", con_dettaglio=False)

        if inf or sq or diff:
            squadre_raw[slug] = {"infortunati": inf, "squalificati": sq, "diffidati": diff}

    return squadre_raw


def _estrai_sezione_bs(corpo_tags, etichetta, con_dettaglio):
    """Trova <em>/<i> con testo 'Infortunati:' (ecc.) e i <strong> successivi
    fino alla prossima etichetta di sezione, con eventuale testo descrittivo."""
    etichette = ("Infortunati", "Squalificati", "Diffidati")
    label_tag = None
    for t in corpo_tags:
        if t.name in ("em", "i") and t.get_text(strip=True).rstrip(":") == etichetta:
            label_tag = t
            break
    if label_tag is None:
        return []

    risultati = []
    started = False
    for t in corpo_tags:
        if t is label_tag:
            started = True
            continue
        if not started:
            continue
        if t.name in ("em", "i") and t.get_text(strip=True).rstrip(":") in etichette:
            break   # prossima sezione
        if t.name in ("strong", "b"):
            nome = t.get_text(strip=True)
            if not nome or nome == "-":
                continue
            if con_dettaglio:
                # il testo descrittivo di solito segue nello stesso blocco/paragrafo
                parent = t.find_parent(["p", "li", "div"]) or t
                testo_completo = parent.get_text(" ", strip=True)
                dettaglio = testo_completo.split(nome, 1)[-1].lstrip(" -–—").strip()
                m_g = re.search(r'(?:in dubbio per la|per la)\s*(\d+)[aª]', dettaglio)
                risultati.append({
                    "nome": nome,
                    "dettaglio": dettaglio.rstrip("."),
                    "rientro_giornata": int(m_g.group(1)) if m_g else None,
                })
            else:
                risultati.append({"nome": nome})
    return risultati


def risolvi_id(squadre_raw, matcher):
    """Sostituisce ogni {'nome': X} con il player_id reale via matching fuzzy."""
    squadre = {}
    non_trovati = []
    for slug, dati in squadre_raw.items():
        squadre[slug] = {}
        for categoria, lista in dati.items():
            risolti = []
            for item in lista:
                pid, score = matcher.match(item["nome"], squadra_hint=slug)
                if pid is None:
                    non_trovati.append((slug, item["nome"]))
                    continue
                risolti.append({**item, "id": pid, "match_score": score})
            squadre[slug][categoria] = risolti
    return squadre, non_trovati


def main():
    print(f"Scaricando {URL}...")
    try:
        html = fetch_html()
    except Exception as e:
        print(f"Errore download: {e}")
        return 1
    print(f"Scaricato ({len(html)} caratteri)")

    squadre_raw = parse(html)
    print(f"Squadre con almeno un'assenza: {len(squadre_raw)}")

    if not squadre_raw:
        print("⚠️  Nessuna squadra estratta — la struttura della pagina potrebbe essere cambiata.")
        idx = html.find("ATALANTA")
        if idx >= 0:
            print("\n" + "="*70)
            print("DIAGNOSTICA — HTML grezzo reale attorno a 'ATALANTA':")
            print("="*70)
            print(html[max(0, idx-300): idx+2500])
            print("="*70 + "\n")
        else:
            print("Nemmeno 'ATALANTA' trovato nel testo — controllare se la pagina è cambiata del tutto.")
        return 1

    if not os.path.exists("data/players.json"):
        print("⚠️  data/players.json non trovato — lancia prima scraper.py per il matching nomi.")
        return 1
    matcher = PlayerMatcher.from_players_json("data/players.json")

    squadre, non_trovati = risolvi_id(squadre_raw, matcher)

    if non_trovati:
        print(f"\n⚠️  {len(non_trovati)} giocatori non riconosciuti (nome non matchato):")
        for slug, nome in non_trovati[:15]:
            print(f"   {slug}: {nome}")

    os.makedirs("data", exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"fonte": "sosfanta.com", "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "squadre": squadre}, f, ensure_ascii=False, indent=2)
    print(f"\nSalvato {OUT_JSON}")

    print("\nAnteprima:")
    for slug, dati in list(squadre.items())[:5]:
        print(f"  {slug}: {dati}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
