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
                p[k] = norm(v)
        players.append(p)

    save_json("players.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stagioneId": SEASON_ID,
        "giocatori": players,
    })
    print(f"    {len(players)} giocatori")


# ── 2. CLASSIFICA ─────────────────────────────────────────────────
def job_classifica() -> None:
    html = fetch(CLASSIFICA_URL).text
    tables = pd.read_html(io.StringIO(html))
    # scegliamo la tabella che contiene sia 'Squadra' sia i punti
    table = None
    for t in tables:
        cols = [norm(c).lower() for c in t.columns.astype(str)]
        if any("squadra" in c for c in cols) and any(c in ("pt", "punti", "pti") for c in cols):
            table = t
            break
    if table is None:
        raise ValueError("Tabella classifica non trovata")

    table.columns = [norm(c).lower() for c in table.columns.astype(str)]
    col_sq = next(c for c in table.columns if "squadra" in c)
    col_pt = next(c for c in table.columns if c in ("pt", "punti", "pti"))

    standings = []
    for _, r in table.iterrows():
        squadra = norm(r[col_sq])
        squadra = re.sub(r"^(\d+\s*)", "", squadra)
        try:
            punti = int(r[col_pt])
        except (ValueError, TypeError):
            continue
        standings.append({"squadra": squadra, "punti": punti})

    if len(standings) < 18:
        raise ValueError(f"Classifica incompleta: {len(standings)} squadre")
    save_json("classifica.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "classifica": standings,
    })
    print(f"    {len(standings)} squadre")


# ── 3. CALENDARIO / PROSSIMA GIORNATA ─────────────────────────────
def job_calendario() -> None:
    """
    Estrae dalla pagina calendario gli accoppiamenti squadra-squadra.
    La pagina mostra la giornata corrente/prossima; salviamo le coppie
    trovate con l'indicazione casa/trasferta.
    """
    html = fetch(CALENDARIO_URL).text
    slugs = re.findall(r"/serie-a/squadre/([a-z0-9\-]+)", html)
    seen_pairs, fixtures = set(), []
    for i in range(0, len(slugs) - 1, 2):
        home, away = slugs[i], slugs[i + 1]
        if home == away:
            continue
        key = (home, away)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        fixtures.append({"casa": home, "trasferta": away})
        if len(fixtures) == 10:
            break

    if len(fixtures) < 8:
        raise ValueError(f"Calendario: trovate solo {len(fixtures)} partite, struttura pagina cambiata?")
    save_json("calendario.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "partite": fixtures,
    })
    print(f"    {len(fixtures)} partite")


# ── 4. RIGORISTI ──────────────────────────────────────────────────
def job_rigoristi() -> None:
    html = fetch(RIGORISTI_URL).text
    matches = re.findall(r"/serie-a/squadre/([a-z0-9\-]+)/([a-z0-9\-\.]+)/\d+", html)
    per_team = {}
    for team, player in matches:
        per_team.setdefault(team, [])
        if player not in per_team[team] and len(per_team[team]) < 3:
            per_team[team].append(player)

    if len(per_team) < 15:
        raise ValueError("Rigoristi: pagina non riconosciuta")
    save_json("rigoristi.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rigoristi": per_team,
    })
    print(f"    {len(per_team)} squadre")


# ── 5. INDISPONIBILI (infortunati + squalificati) ─────────────────
def job_indisponibili() -> None:
    html = fetch(INDISPONIBILI_URL).text
    matches = re.findall(r"/serie-a/squadre/([a-z0-9\-]+)/([a-z0-9\-\.]+)/\d+", html)
    out = {}
    for team, player in matches:
        out.setdefault(team, [])
        if player not in out[team]:
            out[team].append(player)

    save_json("indisponibili.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "indisponibili": out,
    })
    print(f"    {sum(len(v) for v in out.values())} giocatori in {len(out)} squadre")


# ── MAIN ──────────────────────────────────────────────────────────
JOBS = [
    ("Statistiche giocatori", job_statistiche),
    ("Classifica", job_classifica),
    ("Calendario", job_calendario),
    ("Rigoristi", job_rigoristi),
    ("Indisponibili", job_indisponibili),
]


def main() -> int:
    esiti = {}
    for nome, fn in JOBS:
        print(f"\n▶ {nome}")
        try:
            fn()
            esiti[nome] = "ok"
        except Exception as e:
            esiti[nome] = f"ERRORE: {e}"
            print(f"  ✘ {e}", file=sys.stderr)

    save_json("meta.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "esiti": esiti,
    })
    # exit code 0 anche con errori parziali: i JSON validi vanno comunque committati
    print("\nRiepilogo:", json.dumps(esiti, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
