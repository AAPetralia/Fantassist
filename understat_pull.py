# -*- coding: utf-8 -*-
"""
Understat — statistiche offensive Serie A 2025-26 partita per partita.
Tiri, xG, npxG, assist, xA, key passes e minuti per ogni giocatore in ogni gara.
Nessun browser: solo richieste HTTP, quindi gira ovunque senza blocchi.

USO
---
  pip install requests            (se non già presente)
  python understat_pull.py

Produce:  understat_2025_26_permatch.csv  → poi caricalo nella chat.
Understat è tollerante ma restiamo gentili: una breve pausa tra le richieste.
Durata stimata: 5-10 minuti per ~380 partite.
"""

import re
import csv
import json
import sys
import time
import requests

SEASON = "2025"                       # Understat: 2025 = stagione 2025-26
BASE = "https://understat.com"
LEAGUE_URL = f"{BASE}/league/Serie_A/{SEASON}"
OUT = "understat_2025_26_permatch.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Fantassist/1.0"}
PAUSE = 0.6


def extract_json(html, var):
    """Estrae il payload di  var X = JSON.parse('...')  e lo decodifica."""
    m = re.search(var + r"\s*=\s*JSON\.parse\('(.*?)'\)", html, re.S)
    if not m:
        return None
    raw = m.group(1).encode("utf-8").decode("unicode_escape")
    return json.loads(raw)


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def main():
    print(f"Scarico l'indice della stagione: {LEAGUE_URL}")
    html = get(LEAGUE_URL)
    dates = extract_json(html, "datesData")
    if not dates:
        print("ERRORE: non trovo datesData (Understat può aver cambiato struttura). Fermati e avvisa.")
        return 1
    matches = [d for d in dates if d.get("isResult")]
    print(f"  partite giocate trovate: {len(matches)}")

    rows = []
    for i, d in enumerate(matches, 1):
        mid = d["id"]
        date = d.get("datetime")
        ht = d["h"]["title"]
        at = d["a"]["title"]
        try:
            rosters = extract_json(get(f"{BASE}/match/{mid}"), "rostersData")
        except Exception as e:
            print(f"  ! partita {mid} saltata: {e}")
            continue
        if not rosters:
            continue
        for side, team, opp, home in (("h", ht, at, 1), ("a", at, ht, 0)):
            for pid, p in rosters.get(side, {}).items():
                rows.append({
                    "match_id": mid, "date": date, "team": team,
                    "opponent": opp, "home": home,
                    "understat_pid": p.get("player_id", pid),
                    "player": p.get("player"), "position": p.get("position"),
                    "minutes": p.get("time"), "shots": p.get("shots"),
                    "goals": p.get("goals"), "xG": p.get("xG"),
                    "npxG": p.get("npxG"), "assists": p.get("assists"),
                    "xA": p.get("xA"), "key_passes": p.get("key_passes"),
                    "yellow": p.get("yellow_card"), "red": p.get("red_card"),
                })
        if i % 20 == 0:
            print(f"  …{i}/{len(matches)} partite")
        time.sleep(PAUSE)

    if not rows:
        print("ERRORE: nessun dato raccolto.")
        return 1

    cols = ["match_id", "date", "team", "opponent", "home", "understat_pid",
            "player", "position", "minutes", "shots", "goals", "xG", "npxG",
            "assists", "xA", "key_passes", "yellow", "red"]
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\n✔ Salvato {OUT} — {len(rows)} righe (giocatore × partita)")
    print("  Caricalo nella chat per l'incrocio con i voti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
