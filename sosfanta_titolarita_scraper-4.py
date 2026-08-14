# -*- coding: utf-8 -*-
"""
FANTASSIST — Titolarità da SOS Fanta (seconda fonte per il consensus)

TERZO TENTATIVO — approccio cambiato radicalmente dopo 2 fallimenti con
0 elementi estratti nonostante la struttura HTML confermata corretta dalla
diagnostica entrambe le volte. Sospetto: html.parser (il parser base di
Python) naviga male l'albero DOM su una pagina reale grande e complessa,
anche se la STRUTTURA locale è quella giusta — find_parent/find_next_sibling
sono fragili se il parser interpreta l'annidamento in modo leggermente diverso
da un browser vero.

Nuovo approccio, più robusto: PRIMA isolo per stringa pura (nessuna ambiguità
di parsing) il pezzo di HTML tra un "Titolari" e il prossimo header <h3>;
SOLO DENTRO quel pezzo, già piccolo e isolato, uso BeautifulSoup per trovare
i <li> con percentuale+nome. Se anche i 2 <ul> non si trovano puliti dentro
la sezione, ripiego su un flat-parsing di tutti i <li> con posizione (prima
metà=casa, seconda metà=trasferta) invece di fallire del tutto.

USO
---
  pip install requests beautifulsoup4
  python sosfanta_titolarita_scraper.py
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

URL = "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/"
OUT_JSON = "data/fonti_titolarita/sosfanta.json"


def fetch_html():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(URL, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.text


def estrai_li_percentuale_nome(html_snippet):
    """Da un pezzo di HTML (già isolato per stringa), estrae tutte le coppie
    percentuale+nome dai <li>, usando SOLO regex — nessun albero DOM in gioco,
    quindi nessun rischio di parsing errato dell'annidamento."""
    risultati = []
    for li_match in re.finditer(r'<li\b.*?</li>', html_snippet, re.DOTALL):
        li_html = li_match.group(0)
        spans = re.findall(r'<span\b[^>]*>([^<]*)</span>', li_html)
        perc, nome = None, None
        for s in spans:
            s = s.strip()
            m = re.match(r'^(\d{1,3})%$', s)
            if m:
                perc = int(m.group(1))
            elif s:
                nome = s
        if perc is not None and nome:
            risultati.append((perc, nome))
    return risultati


def estrai_titolarita(html):
    risultati = []
    posizioni_titolari = [m.start() for m in re.finditer(r'>Titolari<', html)]
    tutti_h3 = [m.start() for m in re.finditer(r'<h3\b', html)]

    for match_idx, pos_tit in enumerate(posizioni_titolari):
        successivi = [p for p in tutti_h3 if p > pos_tit]
        fine = successivi[0] if successivi else len(html)
        sezione = html[pos_tit:fine]

        # Primo tentativo: 2 <ul> puliti dentro la sezione (casa, trasferta)
        soup_sezione = BeautifulSoup(sezione, "html.parser")
        uls = soup_sezione.find_all("ul")
        if len(uls) >= 2:
            for team_idx, ul in enumerate(uls[:2]):
                for li in ul.find_all("li"):
                    coppie = estrai_li_percentuale_nome(str(li))
                    for perc, nome in coppie:
                        risultati.append({"matchIdx": match_idx, "teamIdx": team_idx,
                                           "percentuale": perc, "nome": nome})
        else:
            # Ripiego: lista piatta di tutti i <li> nella sezione, prima metà
            # assegnata a casa, seconda metà a trasferta (11+11 per Titolari).
            coppie = estrai_li_percentuale_nome(sezione)
            meta = len(coppie) // 2
            for i, (perc, nome) in enumerate(coppie):
                team_idx = 0 if i < meta else 1
                risultati.append({"matchIdx": match_idx, "teamIdx": team_idx,
                                   "percentuale": perc, "nome": nome})

    return risultati


def main():
    print(f"Scaricando {URL}...")
    try:
        html = fetch_html()
    except Exception as e:
        print(f"Errore download: {e}")
        return 1
    print(f"Scaricato ({len(html)} caratteri)")

    risultati = estrai_titolarita(html)
    print(f"Elementi estratti: {len(risultati)}")

    if not risultati:
        print("\n⚠️  ATTENZIONE: 0 elementi estratti. Diagnostica:")
        idx = html.find("Titolari")
        if idx >= 0:
            print(html[max(0, idx-300): idx+2000])
        else:
            print("Nemmeno 'Titolari' trovato nell'HTML — pagina cambiata del tutto.")
        return 1

    if not os.path.exists("data/players.json") or not os.path.exists("data/calendario.json"):
        print("⚠️  Servono data/players.json e data/calendario.json (lanciati prima nello stesso workflow).")
        return 1
    with open("data/calendario.json", encoding="utf-8") as f:
        partite = json.load(f).get("partite", [])
    print(f"Calendario: {len(partite)} partite")

    matcher = PlayerMatcher.from_players_json("data/players.json")
    giocatori = {}
    non_trovati = []
    for r in risultati:
        if r["matchIdx"] >= len(partite):
            continue
        squadra = partite[r["matchIdx"]]["casa"] if r["teamIdx"] == 0 else partite[r["matchIdx"]]["trasferta"]
        pid, score = matcher.match(r["nome"], squadra_hint=squadra)
        if pid is None:
            non_trovati.append((squadra, r["nome"]))
            continue
        prec = giocatori.get(pid)
        if prec is None or r["percentuale"] > prec["percentuale"]:
            giocatori[pid] = {"nome": r["nome"], "squadra": squadra,
                               "percentuale": r["percentuale"],
                               "confidence": round(r["percentuale"]/100, 2), "match_score": score}

    print(f"Giocatori riconosciuti: {len(giocatori)}")
    if non_trovati:
        print(f"⚠️  {len(non_trovati)} non riconosciuti (primi 10): {non_trovati[:10]}")

    os.makedirs("data/fonti_titolarita", exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"fonte": "sosfanta.com", "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "giocatori": giocatori}, f, ensure_ascii=False, indent=2)
    print(f"Salvato {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
