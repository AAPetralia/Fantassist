# -*- coding: utf-8 -*-
"""
VOTI GIORNATA — Scraper definitivo
Legge voti/fantavoti (3 redazioni: Fantacalcio, Statistico, Italia) e bonus/malus
direttamente dagli attributi data-value del DOM renderizzato.

Struttura scoperta (giornata 16, 2025-26):
  div.team-table-body
    table.grades-table
      thead → nome squadra (.team-name)
      tbody
        tr (un giocatore)
          td[0] div.player-item.cell
            span.role[data-value] → ruolo (p/d/c/a)
            a.player-name span → nome
            a[href] → .../squadre/{team}/{slug}/{id}/{stagione}
            img.player-icon[title] → es. "Sostituito" (opzionale)
          td[1] div.group (3× div.pill, ordine = Fantacalcio, Statistico, Italia)
            span.player-grade[data-value]        → Voto (virgola decimale!)
            span.player-fanta-grade[data-value]  → Fantavoto
          td[2] div.group (N× span.player-bonus.cell[.bonus|.malus][title][data-value])

USO
---
  pip install playwright
  python -m playwright install chromium
  python voti_giornata_scraper_v2.py
"""

import asyncio
import json
import sys
import os
from playwright.async_api import async_playwright

SEASON = "2025-26"
GIORNATA = int(sys.argv[1]) if len(sys.argv) > 1 else 16  # default per test locale
URL = f"https://www.fantacalcio.it/voti-fantacalcio-serie-a/{SEASON}/{GIORNATA}"
os.makedirs("data", exist_ok=True)
OUT_JSON = f"data/voti_giornata_{GIORNATA}.json"

# Ordine presunto dei pill (verificato sull'header della tabella): da confermare a vista
FONTI = ["redazione_fantacalcio", "voto_statistico", "voto_italia"]


async def scrape_voti():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print(f"📡 Navigando a {URL}...")
        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("table.grades-table", timeout=20000)
        await page.wait_for_timeout(1500)  # margine per hydration completa

        data = await page.evaluate("""
            () => {
                const parseNum = (s) => {
                    if (s == null || s === "") return null;
                    const n = parseFloat(String(s).replace(",", "."));
                    if (isNaN(n)) return null;
                    // "55" è un valore SENTINELLA usato dal sito per "non votato da questa fonte"
                    // (verificato: 182/188 valori fuori range erano esattamente 55; i rimanenti
                    // erano fantavoti alti ma reali, es. doppietta+POTM=13,5 — NON vanno corretti).
                    if (n === 55) return null;
                    return n;
                };

                const teams = [];
                document.querySelectorAll('div.team-table-body').forEach(teamBlock => {
                    const teamNameEl = teamBlock.querySelector('.team-name');
                    const teamName = teamNameEl ? teamNameEl.textContent.trim() : null;
                    const teamHref = teamBlock.querySelector('a.team-link')?.getAttribute('href') || '';
                    const teamSlug = (teamHref.match(/\\/squadre\\/([^\\/]+)/) || [])[1] || null;

                    const players = [];
                    teamBlock.querySelectorAll('table.grades-table tbody tr').forEach(row => {
                        const nameA = row.querySelector('a.player-name');
                        if (!nameA) return;

                        const href = nameA.getAttribute('href') || '';
                        const idMatch = href.match(/\\/(\\d+)\\/\\d{4}-\\d{2}\\/?$/);
                        const playerId = idMatch ? idMatch[1] : null;
                        const name = nameA.querySelector('span')?.textContent.trim() || nameA.textContent.trim();
                        const role = row.querySelector('span.role')?.getAttribute('data-value') || null;
                        const sostituito = !!row.querySelector('img.player-icon[title*="Sostitu" i]');

                        // Voti: 3 pill (Fantacalcio, Statistico, Italia)
                        const pills = row.querySelectorAll('td:nth-child(2) .pill');
                        const voti = Array.from(pills).map((pill, i) => ({
                            fonte: i,
                            voto: parseNum(pill.querySelector('.player-grade')?.getAttribute('data-value')),
                            fantavoto: parseNum(pill.querySelector('.player-fanta-grade')?.getAttribute('data-value'))
                        }));

                        // Bonus/Malus
                        const bmEls = row.querySelectorAll('td:nth-child(3) .player-bonus');
                        const bonusMalus = Array.from(bmEls).map(el => ({
                            tipo: el.getAttribute('title') || null,
                            segno: el.classList.contains('malus') ? '-' : '+',
                            valore: parseNum(el.getAttribute('data-value'))
                        })).filter(b => b.valore !== null && b.valore !== 0);

                        players.push({
                            player_id: playerId, name, role, sostituito,
                            voti, bonus_malus: bonusMalus
                        });
                    });

                    teams.push({ team: teamName, team_slug: teamSlug, players });
                });

                return teams;
            }
        """)

        await browser.close()
        return data


async def main():
    print(f"\n▶ Voti giornata {GIORNATA} ({SEASON})\n")

    teams = await scrape_voti()
    if not teams:
        print("❌ Nessun dato estratto")
        return 1

    total_players = sum(len(t["players"]) for t in teams)
    print(f"✅ {len(teams)} squadre, {total_players} giocatori totali\n")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(teams, f, ensure_ascii=False, indent=2)
    print(f"📝 Salvato in {OUT_JSON}")

    # Anteprima
    print("\n📊 Anteprima prima squadra:")
    if teams:
        t = teams[0]
        print(f"   Squadra: {t['team']} ({t['team_slug']})")
        for p in t["players"][:5]:
            voti_str = " | ".join(
                f"{FONTI[v['fonte']] if v['fonte']<len(FONTI) else v['fonte']}: V={v['voto']} FV={v['fantavoto']}"
                for v in p["voti"]
            )
            bm_str = ", ".join(f"{b['tipo']}={b['segno']}{b['valore']}" for b in p["bonus_malus"]) or "—"
            print(f"   {p['name']:20s} id={p['player_id']} ruolo={p['role']} sost={p['sostituito']}")
            print(f"      {voti_str}")
            print(f"      bonus/malus: {bm_str}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:
        print(f"\n❌ Errore: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
