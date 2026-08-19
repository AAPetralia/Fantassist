# -*- coding: utf-8 -*-
"""
FANTASSIST — Prezzi reali d'asta da Fantacalcio-Online
Sostituisce la stima FVM/ripartizione-budget per il campo "Max %" in Asta con
il prezzo MEDIO REALMENTE PAGATO, misurato su migliaia di aste vere (non una
formula nostra). Fonte: fantacalcio-online.com/it/i-piu-comprati — tabella con
Ruolo, Squadra, Nome, Quotazione ufficiale, % squadre che l'hanno comprato,
prezzo medio in lega da 350 e da 500 crediti.

Nessun ID giocatore compatibile con fantacalcio.it: matching per nome via
player_name_matcher.py, stesso approccio già usato per SOS Fanta.

Output: data/prezzi_reali_asta.json — {player_id: {percMax, comprato_pct,
prezzo_350, prezzo_500, quotazione, match_score}}

USO
---
  pip install requests beautifulsoup4
  python fantacalcio_online_scraper.py
"""

import re
import sys
import json
import os
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from player_name_matcher import PlayerMatcher, normalize_name

URL = "https://www.fantacalcio-online.com/it/i-piu-comprati"
OUT_JSON = "data/prezzi_reali_asta.json"
BUDGET_RIFERIMENTO = 500   # il prezzo "Prezzo 500" è calibrato su una lega da 500 crediti


def fetch_html():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(URL, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.text


def match_nome_fco(matcher, nome_completo, squadra_hint):
    """I nomi di fantacalcio-online sono 'COGNOME Nome' (es. 'MARTINEZ Lautaro').
    Il nostro database usa il solo cognome, con l'iniziale del nome aggiunta SOLO
    quando serve a distinguere due giocatori con lo stesso cognome (es. 'Martinez L.'
    per Lautaro vs 'Martinez Jo.' per Josep) — il matching generico per similarità
    di stringa può sbagliare proprio in questi casi (verificato: 'Martinez Lautaro'
    veniva abbinato a Josep Martinez, il portiere, invece che a Lautaro). Qui si
    cerca prima il solo cognome fra i candidati; se ce n'è più di uno con lo stesso
    cognome, si usa l'iniziale del nome proprio per scegliere quello giusto."""
    parti = nome_completo.strip().split(None, 1)
    if not parti:
        return None, 0.0
    cognome = parti[0]
    iniziale = parti[1][0].upper() if len(parti) > 1 and parti[1] else None
    cognome_norm = normalize_name(cognome)

    candidati = []
    for pid, p in matcher.by_id.items():
        nome_raw = p.get("nome", "")
        primo_token = nome_raw.split()[0] if nome_raw.split() else nome_raw
        if normalize_name(primo_token) == cognome_norm:
            candidati.append((pid, nome_raw, normalize_name(p.get("squadra", ""))))

    if not candidati:
        return matcher.match(nome_completo, squadra_hint=squadra_hint)

    if len(candidati) == 1:
        return candidati[0][0], 0.95

    if iniziale:
        per_iniziale = [c for c in candidati if c[1].split()[-1].upper().rstrip(".").startswith(iniziale)]
        if len(per_iniziale) == 1:
            return per_iniziale[0][0], 0.9
    if squadra_hint:
        sq_norm = normalize_name(squadra_hint)
        per_squadra = [c for c in candidati if c[2] == sq_norm]
        if len(per_squadra) == 1:
            return per_squadra[0][0], 0.85

    return None, 0.0


def parse_numero(testo):
    """'36,1%' -> 36.1 ; '30.35' -> 30.35 ; '' o None -> None"""
    if not testo:
        return None
    testo = testo.strip().replace("%", "").replace(",", ".")
    if not testo:
        return None
    try:
        return float(testo)
    except ValueError:
        return None


def estrai_tabella(html):
    """Cerca la tabella principale (Ruolo/Squadra/Nome/Kap./Comprato da/Prezzo 350/Prezzo 500)
    e ne estrae le righe. Se non trova un <table> riconoscibile, ritorna lista vuota
    (la diagnostica in main() mostrerà l'HTML vero per correggere)."""
    soup = BeautifulSoup(html, "html.parser")
    righe = []

    for table in soup.find_all("table"):
        header_txt = table.get_text(" ", strip=True)[:200].lower()
        if "kap" not in header_txt and "comprato" not in header_txt:
            continue   # non è la tabella giusta (il sito potrebbe averne altre)
        for tr in table.find_all("tr"):
            celle = tr.find_all(["td"])
            if len(celle) < 5:
                continue
            testi = [c.get_text(" ", strip=True) for c in celle]
            # Il nome è dentro un <a> nella cella 3 (indice 2)
            link = celle[2].find("a")
            if not link:
                continue
            nome_completo = link.get_text(" ", strip=True)
            righe.append({
                "ruolo": testi[0],
                "squadra": testi[1],
                "nome": nome_completo,
                "quotazione": parse_numero(testi[3]) if len(testi) > 3 else None,
                "comprato_pct": parse_numero(testi[4]) if len(testi) > 4 else None,
                "prezzo_350": parse_numero(testi[5]) if len(testi) > 5 else None,
                "prezzo_500": parse_numero(testi[6]) if len(testi) > 6 else None,
            })
        break  # trovata la tabella giusta, non serve continuare

    return righe


def main():
    print(f"Scaricando {URL}...")
    try:
        html = fetch_html()
    except Exception as e:
        print(f"Errore download: {e}")
        return 1
    print(f"Scaricato ({len(html)} caratteri)")

    righe = estrai_tabella(html)
    print(f"Righe estratte: {len(righe)}")

    if not righe:
        print("\n⚠️  ATTENZIONE: 0 righe estratte. Diagnostica:")
        idx = html.lower().find("comprato")
        if idx >= 0:
            print(html[max(0, idx-500): idx+2000])
        else:
            print("Nemmeno 'comprato' trovato nell'HTML — pagina cambiata del tutto.")
        return 1

    if not os.path.exists("data/players.json"):
        print("⚠️  data/players.json non trovato — lancia prima scraper.py per il matching nomi.")
        return 1
    matcher = PlayerMatcher.from_players_json("data/players.json")

    giocatori = {}
    non_trovati = []
    for r in righe:
        pid, score = match_nome_fco(matcher, r["nome"], r["squadra"])
        if pid is None:
            non_trovati.append((r["squadra"], r["nome"]))
            continue

        # % del budget calcolata dal prezzo medio reale, riscalato sul budget di
        # riferimento della colonna disponibile (preferisce "Prezzo 500", il più
        # standard; ripiega su "Prezzo 350" se manca).
        percMax = None
        if r["prezzo_500"] is not None:
            percMax = round(r["prezzo_500"] / 500 * 100, 2)
        elif r["prezzo_350"] is not None:
            percMax = round(r["prezzo_350"] / 350 * 100, 2)

        giocatori[pid] = {
            "nome": r["nome"], "squadra": r["squadra"],
            "percMax": percMax,
            "comprato_pct": r["comprato_pct"],
            "prezzo_350": r["prezzo_350"], "prezzo_500": r["prezzo_500"],
            "quotazione": r["quotazione"], "match_score": score,
        }

    print(f"Giocatori riconosciuti: {len(giocatori)}")
    if non_trovati:
        print(f"⚠️  {len(non_trovati)} non riconosciuti (primi 10): {non_trovati[:10]}")

    os.makedirs("data", exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"fonte": "fantacalcio-online.com", "aggiornato": datetime.now(timezone.utc).isoformat(),
                    "giocatori": giocatori}, f, ensure_ascii=False, indent=2)
    print(f"Salvato {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
