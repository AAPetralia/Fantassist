# -*- coding: utf-8 -*-
"""
FANTASSIST — Matcher di nomi riusabile
Collega giocatori di QUALSIASI fonte esterna (nome, eventualmente squadra) al
player_id canonico di fantacalcio.it (quello usato ovunque in players.json,
voti_storico.json, ecc). Estratto e generalizzato dalla logica già validata
in understat_process.py, così ogni nuova fonte (Sky, altre) riusa lo stesso
codice testato invece di reinventarlo.

USO
---
    from player_name_matcher import PlayerMatcher

    matcher = PlayerMatcher.from_players_json("data/players.json")
    pid, score = matcher.match("Lautaro Martínez", squadra_hint="inter")
    # pid = "2764" (o None se sotto soglia), score = 0.0-1.0
"""

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


def normalize_name(name: str) -> str:
    """Normalizza un nome per il confronto: minuscolo, senza accenti,
    senza iniziali puntate finali, spazi puliti."""
    if not name:
        return ""
    name = name.lower().strip()
    name = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    name = re.sub(r'\s+[a-z]\.$', '', name)          # "Martinez L." -> "martinez"
    name = re.sub(r"['`]", "", name)                  # apostrofi (Dodô, N'Dicka...)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def levenshtein_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


ALIAS = {
    "lautaro martinez": "martinez l",
    "josep martinez": "martinez jo",
    "c.augusto": "carlos augusto",
}


class PlayerMatcher:
    def __init__(self, players):
        """players: lista di dict con almeno {id, nome, squadra}."""
        self.by_id = {str(p["id"]): p for p in players if p.get("id") is not None}
        self.index = []  # [(norm_name, id, squadra_norm)]
        for p in players:
            if p.get("id") is None or not p.get("nome"):
                continue
            norm = normalize_name(p["nome"])
            self.index.append((norm, str(p["id"]), normalize_name(p.get("squadra", ""))))

    @classmethod
    def from_players_json(cls, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        players = data.get("giocatori", data if isinstance(data, list) else [])
        return cls(players)

    def match(self, nome, squadra_hint=None, soglia=0.6):
        """Ritorna (player_id, score) del miglior match, o (None, 0) se sotto soglia."""
        norm = normalize_name(nome)
        norm = ALIAS.get(norm, norm)
        squadra_norm = normalize_name(squadra_hint) if squadra_hint else None

        best_id, best_score = None, soglia
        for cand_norm, pid, cand_squadra in self.index:
            score = levenshtein_ratio(norm, cand_norm)

            norm_parts, cand_parts = norm.split(), cand_norm.split()
            if norm_parts and cand_parts and norm_parts[-1] == cand_parts[-1]:
                score = max(score, 0.85)

            if squadra_norm and cand_squadra and squadra_norm == cand_squadra:
                score += 0.05

            if score > best_score:
                best_score, best_id = score, pid

        return (best_id, round(min(best_score, 1.0), 3)) if best_id else (None, 0.0)

    def match_all(self, entries, squadra_field="squadra", nome_field="nome", soglia=0.6):
        out = []
        for e in entries:
            pid, score = self.match(e.get(nome_field, ""), e.get(squadra_field), soglia)
            out.append({**e, "player_id": pid, "match_score": score})
        return out


if __name__ == "__main__":
    fake_players = [
        {"id": "2764", "nome": "Martinez L.", "squadra": "inter"},
        {"id": "5116", "nome": "Martinez Jo.", "squadra": "inter"},
        {"id": "4433", "nome": "Zortea", "squadra": "bologna"},
    ]
    m = PlayerMatcher(fake_players)
    print(m.match("Lautaro Martínez", squadra_hint="inter"))
    print(m.match("Josep Martínez", squadra_hint="inter"))
    print(m.match("Zortea N.", squadra_hint="bologna"))
    print(m.match("Giocatore Inesistente Xyz"))
