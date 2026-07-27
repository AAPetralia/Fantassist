# -*- coding: utf-8 -*-
"""
FANTASSIST — Elaborazione Understat
Legge il CSV da understat_pull.py, aggrega per giocatore (shots_p90, xa_p90),
fa il matching con players.json, e salva understat.json.

USO
---
  1. understat_pull.py genera understat_2025_26_permatch.csv
  2. Questo script lo elabora → data/understat.json
"""

import json
import sys
import csv
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher
import unicodedata
import re

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

CSV_IN = Path(__file__).parent / "understat_2025_26_permatch.csv"


def normalize_name(name: str) -> str:
    """Normalizza nomi per il matching fuzzy."""
    if not name:
        return ""
    
    # Minuscolo e strip
    name = name.lower().strip()
    
    # Rimuove accenti
    name = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    
    # Rimuove abbreviazioni tipo "L.", "K."
    name = re.sub(r'\s+[a-z]\.$', '', name)
    
    # Pulisce spazi multipli
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Similarità tra due stringhe (0-1)."""
    return SequenceMatcher(None, s1, s2).ratio()


def main() -> int:
    print("\n▶ Elaborazione Understat")
    
    # Legge players.json per il mapping
    players_file = DATA_DIR / "players.json"
    if not players_file.exists():
        print(f"  ✘ {players_file} non trovato (run scraper.py prima)")
        return 1
    
    with open(players_file, encoding='utf-8') as f:
        players_data = json.load(f)
    
    giocatori_fanta = {p['id']: normalize_name(p['nome']) 
                       for p in players_data['giocatori'] if p.get('id')}
    print(f"  Caricati {len(giocatori_fanta)} giocatori da players.json")
    
    # Legge il CSV da understat_pull.py
    if not CSV_IN.exists():
        print(f"  ✘ {CSV_IN} non trovato")
        print(f"     Run understat_pull.py prima per generare il CSV")
        return 1
    
    # Aggregazione per giocatore: {player_name → {min, shots, xa, ...}}
    player_stats = defaultdict(lambda: {
        'minutes': 0, 'shots': 0, 'xa': 0, 'matches': 0,
        'goals': 0, 'xg': 0, 'npxg': 0, 'assists': 0,
        'key_passes': 0
    })
    
    with open(CSV_IN, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            player = row.get('player', '').strip()
            if not player:
                continue
            
            try:
                minutes = int(row.get('minutes', 0)) or 0
                shots = float(row.get('shots', 0)) or 0
                xa = float(row.get('xA', 0)) or 0
                goals = float(row.get('goals', 0)) or 0
                xg = float(row.get('xG', 0)) or 0
                npxg = float(row.get('npxG', 0)) or 0
                assists = float(row.get('assists', 0)) or 0
                key_passes = float(row.get('key_passes', 0)) or 0
            except (ValueError, TypeError):
                continue
            
            player_stats[player]['minutes'] += minutes
            player_stats[player]['shots'] += shots
            player_stats[player]['xa'] += xa
            player_stats[player]['goals'] += goals
            player_stats[player]['xg'] += xg
            player_stats[player]['npxg'] += npxg
            player_stats[player]['assists'] += assists
            player_stats[player]['key_passes'] += key_passes
            player_stats[player]['matches'] += 1
    
    print(f"  Aggregati {len(player_stats)} giocatori dal CSV")
    
    # Calcola p90 e fa il matching con players.json
    understat_by_id = {}
    matched = 0
    failed = []
    
    for understat_name, stats in player_stats.items():
        if stats['minutes'] < 90:
            # Scarta chi ha giocato meno di 90 minuti totali
            continue
        
        # Calcola metriche per 90 minuti
        mins = max(stats['minutes'], 1)
        shots_p90 = (stats['shots'] * 90) / mins if mins > 0 else 0
        xa_p90 = (stats['xa'] * 90) / mins if mins > 0 else 0
        
        # Matching con players.json (fuzzy)
        understat_norm = normalize_name(understat_name)
        best_match_id = None
        best_score = 0.65  # soglia minima
        
        for player_id, fanta_name in giocatori_fanta.items():
            score = levenshtein_ratio(understat_norm, fanta_name)
            
            # Bonus se il cognome finale match
            parts_under = understat_norm.split()
            parts_fanta = fanta_name.split()
            if parts_under and parts_fanta:
                if parts_under[-1] == parts_fanta[-1]:
                    score = max(score, 0.85)
            
            if score > best_score:
                best_score = score
                best_match_id = player_id
        
        if best_match_id:
            understat_by_id[best_match_id] = {
                "shots_p90": round(shots_p90, 3),
                "xa_p90": round(xa_p90, 3),
                "understat_name": understat_name,
                "minutes_total": stats['minutes'],
                "matches": stats['matches'],
                "match_score": round(best_score, 3)
            }
            matched += 1
        else:
            failed.append((understat_name, stats['minutes']))
    
    print(f"  ✓ Matched: {matched} giocatori")
    if failed and len(failed) <= 10:
        print(f"    Falliti (campione):")
        for name, mins in failed[:10]:
            print(f"      - {name} ({mins} min)")
    
    # Salva understat.json
    import datetime as dt
    result = {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fonte": "Understat (partita per partita)",
        "note": "Mapping ID fantacalcio → {shots_p90, xa_p90}. Aggregato da understat_2025_26_permatch.csv.",
        "giocatori": understat_by_id
    }
    
    with open(DATA_DIR / "understat.json", "w", encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    
    print(f"  ✔ scritto data/understat.json ({len(understat_by_id)} giocatori)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
