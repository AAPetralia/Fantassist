# -*- coding: utf-8 -*-
"""
FANTASSIST — Titolarità da SOS Fanta (seconda fonte per il consensus)
Pagina: lista-formazioni/probabili-formazioni-serie-a — percentuali titolari/
ballottaggi/panchina per ogni partita della giornata. Nessun ID giocatore
diretto (solo nome): matching via player_name_matcher.py, stesso approccio
già validato per gli indisponibili SOS Fanta.

Output nello stesso schema "per-fonte" di fantacalcio.it, così
titolarita_consensus.py li combina automaticamente:
  data/fonti_titolarita/sosfanta.json

NOTA: come già successo con fantacalcio.it, il testo "pulito" che si vede
navigando la pagina può NON corrispondere all'HTML grezzo/renderizzato reale.
Questo script include una diagnostica di sicurezza: se l'estrazione fallisce
(0 giocatori), stampa un pezzo di HTML vero nel log invece di fallire e basta,
così un solo giro con dati reali basta a correggere il parser.

USO
---
  pip install playwright
  python -m playwright install chromium --with-deps
  python sosfanta_titolarita_scraper.py
"""

import re
import sys
import json
import os
import asyncio
from datetime import datetime, timezone
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from player_name_matcher import PlayerMatcher

URL = "https://www.sosfanta.com/lista-formazioni/probabili-formazioni-serie-a/"
OUT_JSON = "data/fonti_titolarita/sosfanta.json"


async def fetch_rendered():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(URL, wait_until="load", timeout=30000)
        await page.wait_for_timeout(2000)

        # Estrazione DOM: per ogni partita, cerca i contenitori squadra e le liste
        # Titolari/Panchina al loro interno. Tentativo primario basato su selettori
        # plausibili (h2 nome squadra, liste percentuale+nome vicine); se fallisce
        # (0 partite estratte), la diagnostica sotto rivela la struttura vera.
        risultati = await page.evaluate("""
            () => {
                const risultati = [];
                // Ogni "## NomeSquadra" nella pagina è un h2; cerchiamo tutti gli h2
                // che corrispondono a nomi di squadra noti, e per ciascuno risaliamo
                // al contenitore comune per trovare le liste titolari/panchina vicine.
                const squadre = ['Inter','Monza','Udinese','Como','Parma','Cagliari',
                    'Genoa','Napoli','Venezia','Lecce','Frosinone','Juventus',
                    'Atalanta','Sassuolo','Torino','Milan','Bologna','Lazio','Roma','Fiorentina'];
                document.querySelectorAll('h2, h3').forEach(h => {
                    const testo = h.textContent.trim();
                    if (!squadre.includes(testo)) return;
                    // Cerca la prima lista con percentuali dopo questo header, entro un
                    // contenitore ragionevolmente vicino (non l'intera pagina).
                    let container = h.closest('section, article, div') || h.parentElement;
                    if (!container) return;
                    const items = container.querySelectorAll('li');
                    items.forEach(li => {
                        const t = li.textContent.trim();
                        const m = t.match(/^(\\d{1,3})%\\s*(.+)$/);
                        if (m) {
                            risultati.push({squadra: testo, percentuale: parseInt(m[1]), nome: m[2].trim()});
                        }
                    });
                });
                return risultati;
            }
        """)

        diagnostica = None
        if not risultati:
            html = await page.content()
            idx = html.find("Titolari")
            diagnostica = html[max(0, idx-500): idx+3000] if idx >= 0 else html[:3000]

        await browser.close()
        return risultati, diagnostica


def main():
    risultati, diagnostica = asyncio.run(fetch_rendered())
    print(f"Elementi estratti (grezzi, con probabili duplicati titolari/panchina): {len(risultati)}")

    if not risultati:
        print("\n⚠️  ATTENZIONE: 0 elementi estratti. Struttura pagina diversa dal previsto.")
        if diagnostica:
            print("\n" + "="*70)
            print("DIAGNOSTICA — HTML reale attorno a 'Titolari':")
            print("="*70)
            print(diagnostica)
            print("="*70)
        return 1

    if not os.path.exists("data/players.json"):
        print("⚠️  data/players.json non trovato — lancia prima scraper.py per il matching nomi.")
        return 1
    matcher = PlayerMatcher.from_players_json("data/players.json")

    giocatori = {}
    non_trovati = []
    for r in risultati:
        pid, score = matcher.match(r["nome"], squadra_hint=r["squadra"])
        if pid is None:
            non_trovati.append((r["squadra"], r["nome"]))
            continue
        # Se un giocatore compare più volte (es. titolare+ballottaggio), tiene la
        # percentuale più alta vista finora.
        prec = giocatori.get(pid)
        if prec is None or r["percentuale"] > prec["percentuale"]:
            giocatori[pid] = {
                "nome": r["nome"], "squadra": r["squadra"].lower(),
                "percentuale": r["percentuale"], "confidence": round(r["percentuale"]/100, 2),
                "match_score": score,
            }

    print(f"Giocatori riconosciuti (per ID): {len(giocatori)}")
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
