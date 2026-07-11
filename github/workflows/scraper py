# -*- coding: utf-8 -*-
"""
FANTASSIST — pipeline dati
Scarica statistiche giocatori (Excel ufficiale fantacalcio.it),
classifica, calendario, rigoristi e indisponibili di Serie A,
e salva tutto come JSON nella cartella /data, pronta per la PWA.

Ogni fonte è indipendente: se una fallisce, le altre vengono
comunque aggiornate e il JSON precedente resta al suo posto.
"""

import io
import json
import re
import sys
import datetime as dt
from pathlib import Path

import requests
import pandas as pd

BASE = "https://www.fantacalcio.it"

# ── CONFIG ────────────────────────────────────────────────────────
# ID stagione nell'endpoint Excel: 20 = 2025-26.
# A inizio stagione 2026-27 verificare il nuovo ID dal pulsante
# "Scarica" della pagina /statistiche-serie-a (link api/v1/Excel/stats/<ID>/1).
SEASON_ID = 20

STATS_XLSX_URL = f"{BASE}/api/v1/Excel/stats/{SEASON_ID}/1"
CLASSIFICA_URL = f"{BASE}/serie-a/classifica"
CALENDARIO_URL = f"{BASE}/serie-a/calendario"
RIGORISTI_URL = f"{BASE}/rigoristi-serie-a"
INDISPONIBILI_URL = f"{BASE}/indisponibili-serie-a"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
}

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


# ── UTILITÀ ───────────────────────────────────────────────────────
def fetch(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=40)
    r.raise_for_status()
    return r


def save_json(name: str, payload) -> None:
    path = DATA_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"  ✔ scritto {path.name}")


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


# ── 1. STATISTICHE GIOCATORI (Excel ufficiale) ────────────────────
def job_statistiche() -> None:
    """
    L'Excel ufficiale ha tipicamente una riga di intestazione non in cima
    (titolo/logo nelle prime righe). Individuiamo la riga header cercando
    la cella 'Nome' e rileggiamo il file da lì.
    Le colonne vengono mappate per nome, così piccole variazioni
    non rompono nulla.
    """
    raw = fetch(STATS_XLSX_URL).content
    probe = pd.read_excel(io.BytesIO(raw), header=None, nrows=8)

    header_row = None
    for i, row in probe.iterrows():
        cells = [norm(c).lower() for c in row.tolist()]
        if "nome" in cells:
            header_row = i
            break
    if header_row is None:
        raise ValueError("Riga di intestazione non trovata nell'Excel statistiche")

    df = pd.read_excel(io.BytesIO(raw), header=header_row)
    df.columns = [norm(c) for c in df.columns]

    # mappa nome-colonna → chiave JSON (tollerante a maiuscole/varianti)
    aliases = {
        "id": "id", "r": "ruolo", "rm": "ruoloMantra", "nome": "nome",
        "squadra": "squadra", "pv": "pv", "mv": "mv", "fm": "fm",
        "gf": "gol", "gs": "golSubiti", "rp": "rigoriParati",
        "rc": "rigoriCalciati", "r+": "rigoriSegnati", "r-": "rigoriSbagliati",
        "ass": "assist", "amm": "ammonizioni", "esp": "espulsioni", "au": "autogol",
    }
    colmap = {}
    for c in df.columns:
        key = aliases.get(c.lower())
        if key:
            colmap[c] = key
    df = df[list(colmap)].rename(columns=colmap)
    df = df.dropna(subset=["nome"])

    players = []
    for _, r in df.iterrows():
        p = {}
        for k, v in r.items():
            if pd.isna(v):
                p[k] = None
            elif isinstance(v, float) and v.is_integer():
                p[k] = int(v)
            elif isinstance(v, float):
                p[k] = round(v, 3)
            else:
