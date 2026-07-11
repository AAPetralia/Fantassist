# ⚽ Fantassist

Motore probabilistico open source per la formazione del Fantacalcio:
statistiche aggiornate automaticamente, coefficienti calendario continui,
simulazione Monte Carlo per la scelta del modulo ottimo. PWA per cellulare.

## Come funziona

- `scraper.py` scarica due volte a settimana (GitHub Actions) statistiche
  giocatori, classifica, calendario, rigoristi e indisponibili, salvandoli
  come JSON in `/data`
- La web-app legge i JSON e calcola formazione e modulo con simulazione
  probabilistica (3000 giornate simulate)

## Fonte dati e crediti

I dati provengono da [fantacalcio.it](https://www.fantacalcio.it)
(statistiche ufficiali Fantacalcio® Serie A Enilive), che ne detiene
ogni diritto. Questo progetto è un tool hobbistico senza fini di lucro:
ogni utente scarica i dati per uso personale tramite il proprio workflow.
Non affiliato a fantacalcio.it né alla Lega Serie A.

## Licenza

Codice rilasciato sotto GPL-3.0 — vedi [LICENSE](LICENSE).
Nato da un foglio Excel con 500 ore di volo. 🛩️
