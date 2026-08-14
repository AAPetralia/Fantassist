# -*- coding: utf-8 -*-
"""
FANTASSIST — Consensus Titolarità Reale
Legge TUTTI i file in data/fonti_titolarita/*.json (uno per fonte, stesso
schema: {fonte, giornata, giocatori:{player_id:{percentuale/confidence,...}}})
e li combina in data/titolarita_reale.json, il file che il motore (index.html)
legge in S.titolarita_reale.

Con 1 sola fonte disponibile (oggi: fantacalcio.it) il consensus coincide con
quella fonte. Quando altre fonti verranno aggiunte (stesso schema, tramite
player_name_matcher.py per il matching nome->id), si combinano automaticamente
in media pesata — nessuna modifica a questo script.

USO
---
  python titolarita_consensus.py
"""

import json
import glob
import os
from datetime import datetime, timezone
from collections import defaultdict

FONTI_DIR = "data/fonti_titolarita"
OUT_JSON = "data/titolarita_reale.json"

PESI_FONTE = {
    "fantacalcio.it": 1.0,
    "sosfanta.com": 0.8,      # meno storicamente validata di fantacalcio.it in questo progetto, peso minore
}
PESO_DEFAULT = 0.5  # per fonti non ancora presenti in PESI_FONTE (nuove, non tarate)


def carica_fonti():
    fonti = []
    for path in sorted(glob.glob(os.path.join(FONTI_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        fonti.append(data)
    return fonti


def combina(fonti):
    """Per ogni player_id, media pesata delle 'confidence' tra le fonti che lo citano."""
    accumulo = defaultdict(list)
    anagrafica = {}

    for f in fonti:
        nome_fonte = f.get("fonte", "sconosciuta")
        peso = PESI_FONTE.get(nome_fonte, PESO_DEFAULT)
        for pid, g in f.get("giocatori", {}).items():
            conf = g.get("confidence")
            if conf is None and g.get("percentuale") is not None:
                conf = g["percentuale"] / 100
            if conf is None:
                continue
            match_score = g.get("match_score", 1.0)
            peso_effettivo = peso * match_score
            accumulo[pid].append((conf, peso_effettivo, nome_fonte))
            if pid not in anagrafica:
                anagrafica[pid] = {"nome": g.get("nome"), "squadra": g.get("squadra")}

    risultato = {}
    for pid, letture in accumulo.items():
        peso_tot = sum(p for _, p, _ in letture)
        if peso_tot <= 0:
            continue
        confidence = sum(c * p for c, p, _ in letture) / peso_tot
        risultato[pid] = {
            **anagrafica[pid],
            "confidence": round(confidence, 3),
            "fonti": [fn for _, _, fn in letture],
            "n_fonti": len(letture),
        }
    return risultato


def main():
    fonti = carica_fonti()
    if not fonti:
        print(f"Nessuna fonte trovata in {FONTI_DIR}/ - lancia prima uno scraper")
        return 1

    print(f"{len(fonti)} fonte/i trovate:")
    for f in fonti:
        print(f"   {f.get('fonte','?'):20s} - {len(f.get('giocatori',{}))} giocatori, giornata {f.get('giornata')}")

    consensus = combina(fonti)
    print(f"\nConsensus calcolato per {len(consensus)} giocatori")

    multi_fonte = [pid for pid, g in consensus.items() if g["n_fonti"] > 1]
    print(f"   di cui {len(multi_fonte)} confermati da piu' di una fonte")

    os.makedirs("data", exist_ok=True)
    output = {
        "aggiornato": datetime.now(timezone.utc).isoformat(),
        "fonti_usate": [f.get("fonte") for f in fonti],
        "giocatori": consensus,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Salvato in {OUT_JSON}")

    print("\nAnteprima (10 giocatori):")
    for pid, g in list(consensus.items())[:10]:
        print(f"   id={pid:>6s}  {str(g['nome']):20s}  confidence={g['confidence']}  fonti={g['fonti']}")

    return 0


if __name__ == "__main__":
    exit(main())
