# -*- coding: utf-8 -*-
"""
INTEGRAZIONE VOTI GIORNATA → voti_storico.json
Prende l'output di voti_giornata_scraper_v2.py (formato per-squadra) e:
  1. Appiattisce per player_id (stesso ID di players.json → matching diretto)
  2. Calcola il CONSENSUS tra le 3 redazioni (media semplice, scartando i null)
  3. Accumula nello storico voti_storico.json (una riga per player_id x giornata)

USO
---
  python integra_voti_storico.py voti_giornata_16.json 16
"""

import json
import sys
import os
from pathlib import Path
from statistics import mean

STORICO_PATH = "data/voti_storico.json"


def clamp_voto(v):
    """'55' è un valore SENTINELLA usato dal sito per 'non votato da questa fonte'
    (verificato sui dati reali: 182/188 valori >11 erano esattamente 55; i rimanenti
    erano fantavoti alti ma legittimi, es. doppietta+Player of the match=13,5 —
    quelli NON vanno toccati). Qualsiasi altro valore fuori range viene lasciato
    invariato ma segnalato per revisione manuale."""
    if v is None:
        return None, False
    if v == 55:
        return None, True  # sentinel → dato mancante
    return v, False


def flatten(teams_data, giornata):
    """Appiattisce il formato per-squadra in una lista per player_id."""
    rows = []
    sentinel_rimossi = []
    da_rivedere = []
    for team in teams_data:
        for p in team["players"]:
            if not p.get("player_id"):
                continue  # giocatori senza id (raro, es. nome non linkato) scartati

            voti_puliti = []
            for v in p["voti"]:
                voto_c, sent_v = clamp_voto(v["voto"])
                fanta_c, sent_f = clamp_voto(v["fantavoto"])
                if sent_v or sent_f:
                    sentinel_rimossi.append((p["name"], p["player_id"], v["fonte"]))
                elif (voto_c is not None and abs(voto_c) > 11) or (fanta_c is not None and abs(fanta_c) > 11):
                    da_rivedere.append((p["name"], p["player_id"], voto_c, fanta_c))
                voti_puliti.append({**v, "voto": voto_c, "fantavoto": fanta_c})
            p["voti"] = voti_puliti

            fantavoti = [v["fantavoto"] for v in p["voti"] if v["fantavoto"] is not None]
            voti = [v["voto"] for v in p["voti"] if v["voto"] is not None]

            rows.append({
                "player_id": p["player_id"],
                "nome": p["name"],
                "squadra": team["team_slug"],
                "ruolo": p["role"],
                "giornata": giornata,
                "sostituito": p["sostituito"],
                "voto_consensus": round(mean(voti), 2) if voti else None,
                "fantavoto_consensus": round(mean(fantavoti), 2) if fantavoti else None,
                "voti_per_fonte": p["voti"],          # dettaglio 3 redazioni, per audit
                "bonus_malus": p["bonus_malus"],
            })

    if sentinel_rimossi:
        print(f"ℹ️  {len(sentinel_rimossi)} voti sentinella (55 = non votato da quella fonte) esclusi dal consensus")
    if da_rivedere:
        print(f"⚠️  {len(da_rivedere)} valori fuori range MA NON toccati (probabile fantavoto alto legittimo) — controlla a vista:")
        for nome, pid, v, fv in da_rivedere[:10]:
            print(f"   {nome} (id={pid}): V={v} FV={fv}")

    return rows


def load_storico():
    if Path(STORICO_PATH).exists():
        with open(STORICO_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_storico(storico):
    os.makedirs("data", exist_ok=True)
    with open(STORICO_PATH, "w", encoding="utf-8") as f:
        json.dump(storico, f, ensure_ascii=False, indent=2)


def main():
    if len(sys.argv) < 3:
        print("Uso: python integra_voti_storico.py <file_voti_giornata.json> <numero_giornata>")
        return 1

    voti_path, giornata = sys.argv[1], int(sys.argv[2])

    with open(voti_path, encoding="utf-8") as f:
        teams_data = json.load(f)

    rows = flatten(teams_data, giornata)
    print(f"✅ {len(rows)} giocatori appiattiti dalla giornata {giornata}")

    anomalie = [r for r in rows if r["fantavoto_consensus"] is None]
    if anomalie:
        print(f"⚠️  {len(anomalie)} giocatori senza fantavoto valido (probabile non giocato):")
        for a in anomalie[:5]:
            print(f"   {a['nome']} (id={a['player_id']})")

    # Carica storico esistente e integra (keyed by player_id → lista giornate)
    storico = load_storico()
    aggiornati, nuovi = 0, 0

    for r in rows:
        pid = r["player_id"]
        if pid not in storico:
            storico[pid] = {"nome": r["nome"], "squadra": r["squadra"], "ruolo": r["ruolo"], "giornate": {}}
            nuovi += 1
        else:
            aggiornati += 1

        storico[pid]["giornate"][str(giornata)] = {
            "voto_consensus": r["voto_consensus"],
            "fantavoto_consensus": r["fantavoto_consensus"],
            "sostituito": r["sostituito"],
            "voti_per_fonte": r["voti_per_fonte"],
            "bonus_malus": r["bonus_malus"],
        }

    save_storico(storico)
    print(f"\n📝 voti_storico.json aggiornato: {nuovi} giocatori nuovi, {aggiornati} aggiornati")
    print(f"   Totale giocatori nello storico: {len(storico)}")

    # Anteprima consensus
    print("\n📊 Anteprima consensus (primi 5):")
    for r in rows[:5]:
        print(f"   {r['nome']:20s} id={r['player_id']:>6s} → "
              f"V={r['voto_consensus']} FV={r['fantavoto_consensus']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
