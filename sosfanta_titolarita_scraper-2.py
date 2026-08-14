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
        try:
            await page.get_by_text("Titolari", exact=True).first.wait_for(timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)

        # Scroll a passi larghi attraverso tutta la pagina: con 10 partite elencate,
        # è probabile che solo le prime si idratino subito e le altre solo quando
        # entrano in viewport (stessa tecnica già validata su fantacalcio.it).
        altezza_totale = await page.evaluate("document.body.scrollHeight")
        step = 1500
        y = 0
        max_iterazioni = 20
        i = 0
        while y < altezza_totale and i < max_iterazioni:
            await page.evaluate(f"window.scrollTo(0, {y})")
            await page.wait_for_timeout(400)
            y += step
            i += 1
            altezza_totale = await page.evaluate("document.body.scrollHeight")
        await page.wait_for_timeout(1000)

        # Estrazione DOM sulla struttura REALE (scoperta da diagnostica su dati veri,
        # non ipotizzata): ogni sezione "Titolari" è un <h3> dentro un div con 2 span
        # vuoti; il div FRATELLO successivo contiene 2 <ul> (indice 0 = squadra di
        # casa, indice 1 = trasferta, stesso ordine di calendario.json). Ogni <li> ha
        # 2 <span>: uno con la percentuale ("95%"), uno col nome.
        risultati = await page.evaluate("""
            () => {
                const risultati = [];
                const headers = Array.from(document.querySelectorAll('h3'))
                    .filter(h => h.textContent.trim() === 'Titolari');
                headers.forEach((h3, matchIdx) => {
                    const headerDiv = h3.closest('div');
                    const gridDiv = headerDiv ? headerDiv.nextElementSibling : null;
                    if (!gridDiv) return;
                    const uls = gridDiv.querySelectorAll('ul');
                    uls.forEach((ul, teamIdx) => {
                        ul.querySelectorAll('li').forEach(li => {
                            let perc = null, nome = null;
                            li.querySelectorAll('span').forEach(s => {
                                const t = s.textContent.trim();
                                const m = t.match(/^(\\d{1,3})%$/);
                                if (m) perc = parseInt(m[1]);
                                else if (t) nome = t;
                            });
                            if (perc !== null && nome) {
                                risultati.push({matchIdx, teamIdx, percentuale: perc, nome});
                            }
                        });
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
    if not os.path.exists("data/calendario.json"):
        print("⚠️  data/calendario.json non trovato — serve per abbinare matchIdx→squadre.")
        print("   Lancia prima probabili_formazioni_scraper.py nello stesso workflow.")
        return 1
    with open("data/calendario.json", encoding="utf-8") as f:
        partite = json.load(f).get("partite", [])
    print(f"Calendario: {len(partite)} partite disponibili per l'abbinamento")

    matcher = PlayerMatcher.from_players_json("data/players.json")

    giocatori = {}
    non_trovati = []
    non_abbinati_partita = 0
    for r in risultati:
        if r["matchIdx"] >= len(partite):
            non_abbinati_partita += 1
            continue
        squadra = partite[r["matchIdx"]]["casa"] if r["teamIdx"] == 0 else partite[r["matchIdx"]]["trasferta"]
        pid, score = matcher.match(r["nome"], squadra_hint=squadra)
        if pid is None:
            non_trovati.append((squadra, r["nome"]))
            continue
        # Se un giocatore compare più volte (es. titolare+ballottaggio), tiene la
        # percentuale più alta vista finora.
        prec = giocatori.get(pid)
        if prec is None or r["percentuale"] > prec["percentuale"]:
            giocatori[pid] = {
                "nome": r["nome"], "squadra": squadra,
                "percentuale": r["percentuale"], "confidence": round(r["percentuale"]/100, 2),
                "match_score": score,
            }

    print(f"Giocatori riconosciuti (per ID): {len(giocatori)}")
    if non_abbinati_partita:
        print(f"⚠️  {non_abbinati_partita} elementi con matchIdx oltre il numero di partite in calendario.json")
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
