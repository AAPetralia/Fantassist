# -*- coding: utf-8 -*-
"""
FANTASSIST — Titolarità da SOS Fanta (seconda fonte per il consensus)
Pagina: lista-formazioni/probabili-formazioni-serie-a — percentuali titolari/
ballottaggi/panchina per ogni partita della giornata. Nessun ID giocatore
diretto (solo nome): matching via player_name_matcher.py.

CAMBIO DI APPROCCIO: la prima versione usava Playwright, ma ha fallito due
volte di fila con 0 elementi estratti nonostante la struttura HTML confermata
corretta dalla diagnostica in entrambi i casi — sintomo di un problema di
timing/hydration di Playwright, non della struttura. Lo scraper indisponibili
su questo STESSO sito funziona con semplice `requests` (nessun JS necessario):
SOS Fanta è renderizzato lato server. Questa versione fa lo stesso.

Struttura reale confermata due volte su dati veri (log di produzione):
  <h3>Titolari</h3>                          (dentro un div fratello di...)
  <div class="grid grid-cols-2 gap-8">        (...contenente 2 <ul>, indice
    <ul>...</ul>                               0=squadra di casa, 1=trasferta)
    <ul>...</ul>
  </div>
  ogni <li> contiene 2 <span>: percentuale ("95%") e nome giocatore.

Output nello stesso schema "per-fonte" di fantacalcio.it, così
titolarita_consensus.py li combina automaticamente:
  data/fonti_titolarita/sosfanta.json

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


def estrai_titolarita(html):
    """Naviga la struttura reale (confermata due volte su dati di produzione):
    ogni <h3>Titolari</h3> è seguito da un div fratello con 2 <ul> (casa, trasferta)."""
    soup = BeautifulSoup(html, "html.parser")
    risultati = []

    headers_titolari = [h for h in soup.find_all("h3") if h.get_text(strip=True) == "Titolari"]
    for match_idx, h3 in enumerate(headers_titolari):
        header_div = h3.find_parent("div")
        if not header_div:
            continue
        grid_div = header_div.find_next_sibling("div")
        if not grid_div:
            continue
        uls = grid_div.find_all("ul", recursive=False)
        for team_idx, ul in enumerate(uls):
            for li in ul.find_all("li"):
                spans = li.find_all("span")
                perc, nome = None, None
                for s in spans:
                    t = s.get_text(strip=True)
                    m = re.match(r"^(\d{1,3})%$", t)
                    if m:
                        perc = int(m.group(1))
                    elif t:
                        nome = t
                if perc is not None and nome:
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
    print(f"Elementi estratti (grezzi, con probabili duplicati titolari/panchina): {len(risultati)}")

    if not risultati:
        print("\n⚠️  ATTENZIONE: 0 elementi estratti. Struttura pagina diversa dal previsto.")
        idx = html.find("Titolari")
        if idx >= 0:
            print("\n" + "="*70)
            print("DIAGNOSTICA — HTML grezzo reale attorno a 'Titolari':")
            print("="*70)
            print(html[max(0, idx-500): idx+3000])
            print("="*70)
        else:
            print("Nemmeno la parola 'Titolari' trovata nell'HTML — pagina cambiata del tutto.")
        return 1

    if not os.path.exists("data/players.json"):
        print("⚠️  data/players.json non trovato — lancia prima scraper.py per il matching nomi.")
        return 1
    if not os.path.exists("data/calendario.json"):
        print("⚠️  data/calendario.json non trovato — serve per abbinare matchIdx→squadre.")
        return 1
    with open("data/calendario.json", encoding="utf-8") as f:
        partite = json.load(f).get("partite", [])
    print(f"Calendario: {len(partite)} partite disponibili per l'abbinamento")

    matcher = PlayerMatcher.from_players_json("data/players.json")

    giocatori = {}
    non_trovati = []
    non_abbinati_partita = 0
    for r in risultati:
        if r["matchIdx"] >= len(partite):
            non_abbinati_partita += 1
            continue
        squadra = partite[r["matchIdx"]]["casa"] if r["teamIdx"] == 0 else partite[r["matchIdx"]]["trasferta"]
        pid, score = matcher.match(r["nome"], squadra_hint=squadra)
        if pid is None:
            non_trovati.append((squadra, r["nome"]))
            continue
        prec = giocatori.get(pid)
        if prec is None or r["percentuale"] > prec["percentuale"]:
            giocatori[pid] = {
                "nome": r["nome"], "squadra": squadra,
                "percentuale": r["percentuale"], "confidence": round(r["percentuale"]/100, 2),
                "match_score": score,
            }

    print(f"Giocatori riconosciuti (per ID): {len(giocatori)}")
    if non_abbinati_partita:
        print(f"⚠️  {non_abbinati_partita} elementi con matchIdx oltre il numero di partite in calendario.json")
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
