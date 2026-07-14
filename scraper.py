# -*- coding: utf-8 -*-
"""
FANTASSIST — pipeline dati
Scarica statistiche giocatori (tabella pubblica fantacalcio.it),
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


# ── 1. STATISTICHE GIOCATORI (tabella HTML, nessun login richiesto) ──
def job_statistiche() -> None:
    """
    L'endpoint Excel richiede il login (401), ma la tabella della pagina
    /statistiche-serie-a è renderizzata lato server e liberamente leggibile.
    Le celle vengono allineate alle intestazioni per nome, così l'ordine o
    le colonne-icona in più non rompono nulla. Il ruolo (P/D/C/A) è cercato
    con più euristiche; se non trovato resta null e si integra in app.
    """
    from bs4 import BeautifulSoup

    html = fetch(f"{BASE}/statistiche-serie-a").text
    soup = BeautifulSoup(html, "lxml")

    table = None
    for t in soup.select("table"):
        head = " ".join(norm(th.get_text()) for th in t.select("thead th, tr th")).lower()
        if "mv" in head.split() and "fm" in head.split():
            table = t
            break
    if table is None:
        raise ValueError("Tabella statistiche non trovata nella pagina")

    headers = [norm(th.get_text()).lower() for th in table.select("thead th, tr th")]

    def col(label):
        return headers.index(label) if label in headers else None

    idx = {
        "pv": col("pv"), "mv": col("mv"), "fm": col("fm"),
        "gol": col("gol"), "golSubiti": col("gs"), "rig": col("rig"),
        "rigoriParati": col("rp"), "assist": col("ass"),
        "ammonizioni": col("amm"), "espulsioni": col("esp"),
    }

    def to_num(s):
        s = norm(s).replace(",", ".") if s else ""
        if not s or s == "-":
            return None
        try:
            f = float(s)
            return int(f) if f.is_integer() else round(f, 3)
        except ValueError:
            return None

    ROLE_TITLES = {"portiere": "P", "difensore": "D",
                   "centrocampista": "C", "attaccante": "A"}

    players = []
    for tr in table.select("tbody tr"):
        a = tr.select_one("a[href*='/serie-a/squadre/']")
        if not a:
            continue
        m = re.search(r"/serie-a/squadre/([^/]+)/([^/]+)/(\d+)", a.get("href", ""))
        cells = [norm(td.get_text()) for td in tr.select("td")]

        role = None
        el = tr.select_one("[data-value]")
        if el and norm(el.get("data-value", "")).lower() in ("p", "d", "c", "a"):
            role = norm(el.get("data-value")).upper()
        if role is None:
            for el in tr.select("[class]"):
                for cls in el.get("class", []):
                    mm = re.fullmatch(r"role[-_]?([pdca])", cls.lower())
                    if mm:
                        role = mm.group(1).upper()
                        break
                if role:
                    break
        if role is None:
            for el in tr.select("[title], [aria-label]"):
                lab = (el.get("title") or el.get("aria-label") or "").strip().lower()
                if lab in ROLE_TITLES:
                    role = ROLE_TITLES[lab]
                    break

        def cell(key):
            i = idx.get(key)
            return cells[i] if i is not None and i < len(cells) else None

        rig_s = rig_c = None
        rig_raw = cell("rig")
        if rig_raw:
            mm = re.match(r"(\d+)\s*/\s*(\d+)", rig_raw)
            if mm:
                rig_s, rig_c = int(mm.group(1)), int(mm.group(2))

        players.append({
            "id": int(m.group(3)) if m else None,
            "nome": norm(a.get_text()),
            "squadra": m.group(1) if m else None,
            "ruolo": role,
            "pv": to_num(cell("pv")), "mv": to_num(cell("mv")), "fm": to_num(cell("fm")),
            "gol": to_num(cell("gol")), "golSubiti": to_num(cell("golSubiti")),
            "rigoriSegnati": rig_s, "rigoriCalciati": rig_c,
            "rigoriParati": to_num(cell("rigoriParati")), "assist": to_num(cell("assist")),
            "ammonizioni": to_num(cell("ammonizioni")), "espulsioni": to_num(cell("espulsioni")),
        })

    if len(players) < 200:
        raise ValueError(f"Statistiche: trovati solo {len(players)} giocatori, struttura pagina cambiata?")

    con_ruolo = sum(1 for p in players if p["ruolo"])
    save_json("players.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "fonte": "tabella HTML statistiche-serie-a",
        "giocatori": players,
    })
    print(f"    {len(players)} giocatori ({con_ruolo} con ruolo riconosciuto)")


# ── 2. CLASSIFICA ─────────────────────────────────────────────────
def job_classifica() -> None:
    html = fetch(CLASSIFICA_URL).text
    tables = pd.read_html(io.StringIO(html))
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
        raise ValueError(f"Calendario: trovate {len(fixtures)} partite (normale a campionato fermo)")
    save_json("calendario.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "partite": fixtures,
    })
    print(f"    {len(fixtures)} partite")


# ── 4. RIGORISTI ──────────────────────────────────────────────────
def job_rigoristi() -> None:
    html = fetch(RIGORISTI_URL).text
    matches = re.findall(r"/serie-a/squadre/([^/]+)/([^/]+)/\d+", html)
    per_team = {}
    for team, player in matches:
        per_team.setdefault(team, [])
        if player not in per_team[team] and len(per_team[team]) < 3:
            per_team[team].append(player)

    if len(per_team) < 15:
        raise ValueError("Rigoristi: meno di 15 squadre trovate (normale a campionato fermo)")
    save_json("rigoristi.json", {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rigoristi": per_team,
    })
    print(f"    {len(per_team)} squadre")


# ── 5. INDISPONIBILI (infortunati + squalificati) ─────────────────
def job_indisponibili() -> None:
    html = fetch(INDISPONIBILI_URL).text
    matches = re.findall(r"/serie-a/squadre/([^/]+)/([^/]+)/\d+", html)
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
    print("\nRiepilogo:", json.dumps(esiti, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
