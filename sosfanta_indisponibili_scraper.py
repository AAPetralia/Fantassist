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


def estrai_giocatori(sezione, corpo, con_dettaglio):
    m = re.search(rf'\*{sezione}:\*\s*(.+?)(?=\n\*[A-Z]|\Z)', corpo, re.DOTALL)
    if not m:
        return []
    testo_sez = m.group(1).strip()
    if testo_sez in ("-", ""):
        return []
    if con_dettaglio:
        out = []
        for nome, dettaglio in re.findall(r'\*\*([^*]+)\*\*\s*-\s*([^\n]+?)(?=\n\n|\Z)', testo_sez, re.DOTALL):
            m_g = re.search(r'(?:in dubbio per la|per la)\s*(\d+)[aª]', dettaglio)
            out.append({
                "nome": nome.strip(),
                "dettaglio": dettaglio.strip().rstrip("."),
                "rientro_giornata": int(m_g.group(1)) if m_g else None,
            })
        return out
    return [{"nome": n.strip()} for n in re.findall(r'\*\*([^*]+)\*\*', testo_sez)]


def parse(html):
    blocchi = re.split(r'\n\*\*([A-Z ]+)\*\*\n', "\n" + html)
    squadre_raw = {}
    for i in range(1, len(blocchi), 2):
        nome_squadra = blocchi[i].strip()
        if nome_squadra not in SLUG_SQUADRA:
            continue   # scarta falsi positivi (titoli articolo in maiuscolo, ecc.)
        corpo = blocchi[i + 1]
        inf = estrai_giocatori("Infortunati", corpo, con_dettaglio=True)
        sq = estrai_giocatori("Squalificati", corpo, con_dettaglio=False)
        diff = estrai_giocatori("Diffidati", corpo, con_dettaglio=False)
        if inf or sq or diff:
            squadre_raw[SLUG_SQUADRA[nome_squadra]] = {
                "infortunati": inf, "squalificati": sq, "diffidati": diff}
    return squadre_raw


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
