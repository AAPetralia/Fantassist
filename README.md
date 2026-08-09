# Fantassist 2.0

PWA per l'ottimizzazione della formazione fantacalcio (regolamento Classic),
con pipeline dati automatizzata da fantacalcio.it e altre fonti.

**Live:** `https://<utente>.github.io/<repo>/`

---

## Cosa fa l'app

- **Rosa** — la tua rosa con rating (Indice di Schierabilità), titolarità e
  scomposizione del calcolo per ogni giocatore
- **Giornata** — partite della prossima giornata di Serie A con Δ calendario
  per squadra
- **Formazione** — modulo ottimo e undici titolare, basati **solo** su
  performance e titolarità: un consiglio universale, indipendente dalle
  regole della tua lega. Simulazione Monte Carlo (3000 giornate) con banda
  di incertezza P10/mediana/P90. Sotto-scheda **Dettagli Lineup** con tutti
  i giocatori (titolari e panchina) e i calcoli completi
- **Sfida** — confronto testa a testa Monte Carlo contro l'avversario di
  giornata, con selezione automatica dal **Calendario Lega** (round-robin
  generato o importato)
- **Top 11** — classifica di lega sulla migliore formazione *realmente*
  giocata a giornata conclusa (voti reali, non previsioni), con Bonus
  Capitano/Vice e Modificatore di Difesa applicati secondo le **Regole Lega**
- **Regole Lega** — Bonus Capitano (raddoppio / fisso / a fasce, con vice
  automatico) e Modificatore di Difesa (meccanismo reale fantacalcio.it:
  media voto puro di portiere + 3 migliori difensori, richiede 4+ difensori
  schierati), entrambi opzionali e configurabili — si applicano solo al
  Top 11, non alla Formazione
- **Mercato / Asta** — spunti di mercato (con fallback su FVM del listone
  ufficiale a campionato fermo) e appunti d'asta
- **Listone** — import quotazioni ufficiali (Excel), usato anche come
  fonte complementare di matching quando un giocatore manca dal database
  statistiche

## L'Indice di Schierabilità (motore)

```
Schierabilità = (Fantamedia shrunk + Forza squadra + Δ calendario
                 + Performance Understat + bonus rigorista) × Indice di Titolarità
```

**Indice di Titolarità (IT)**:
```
IT = 0,12 · TS + 0,88 · consensus_fonti_reali   (quando le fonti reali sono disponibili)
IT = TS                                          (altrimenti)
```
- **TS**: transizione graduale da rateo presenze stagione precedente
  (`storico_presenze.json`) a rateo presenze stagione corrente, man mano
  che le giornate reali si accumulano. Fallback neutro (0,7) se non c'è
  storico per un giocatore.
- **Fonti reali**: consensus pesato tra fantacalcio.it (probabili
  formazioni) e altre fonti future, calcolato da `titolarita_consensus.py`.

## Struttura

```
fantassist/
├── index.html                        # la PWA
├── scraper.py                        # statistiche stagionali (pv/mv/fm/gol/...)
├── understat_pull.py                 # scarica CSV Understat (disabilitato fuori stagione)
├── understat_process.py              # CSV → understat.json
├── voti_giornata_scraper_v2.py       # voti reali di una giornata (3 redazioni)
├── integra_voti_storico.py           # consensus voti → voti_storico.json
├── titolarita_scraper.py             # probabili formazioni fantacalcio.it
├── titolarita_consensus.py           # combina N fonti → titolarita_reale.json
├── player_name_matcher.py            # matching nome→id riusabile da qualsiasi fonte
├── requirements.txt
├── data/                             # output JSON, letti dalla PWA
│   ├── players.json                  # statistiche stagione corrente
│   ├── classifica.json
│   ├── calendario.json
│   ├── rigoristi.json
│   ├── indisponibili.json
│   ├── meta.json
│   ├── understat.json                # feed offensivo (quando attivo)
│   ├── voti_storico.json             # voti reali per giornata (accumulo progressivo)
│   ├── titolarita_reale.json         # consensus titolarità da probabili formazioni
│   ├── storico_presenze.json         # presenze stagione precedente (statico, per TS)
│   └── fonti_titolarita/             # output grezzo per-fonte (input di titolarita_consensus.py)
└── .github/workflows/update-data.yml # automazione
```

## Messa in funzione (una tantum, ~10 minuti)

1. Crea un repository su GitHub (es. `fantassist`), anche privato*.
2. Carica questi file rispettando la struttura (la cartella `.github/workflows` è essenziale).
3. Tab **Actions** → abilita i workflow → seleziona "Aggiorna dati Fantassist" → **Run workflow** per la prima esecuzione manuale.
4. Controlla che in `/data` compaiano i JSON e leggi `meta.json` per gli esiti.
5. **Settings → Pages** → Source: branch `main` → la PWA e i JSON saranno serviti da `https://<utente>.github.io/<repo>/`.

*Con repo privato, GitHub Pages richiede un piano a pagamento: per l'hosting gratuito della PWA usa un repo pubblico.

## Esecuzione dei singoli script

```bash
pip install -r requirements.txt

# Statistiche stagionali (automatico, lun+ven)
python scraper.py

# Voti di una giornata conclusa (manuale, via workflow_dispatch con numero giornata)
python voti_giornata_scraper_v2.py 1
python integra_voti_storico.py data/voti_giornata_1.json 1

# Probabili formazioni (manuale, vicino alla giornata — le formazioni cambiano
# nei giorni precedenti la partita, non ha senso lanciarlo con troppo anticipo)
python titolarita_scraper.py 1
python titolarita_consensus.py
```

## Dati statici da caricare una tantum

- **`storico_presenze.json`** — costruito da `Statistiche_Fantacalcio_Stagione_2025_26.xlsx`
  (l'ultimo export prima del reset stagionale), filtrato solo sui giocatori
  ancora in Serie A. Non cambia più durante la stagione, va caricato in
  `data/` una volta sola.
- **Listone quotazioni** — si importa dall'app stessa (Altro → Listone),
  non dalla pipeline GitHub.

## Manutenzione prevista

- **Inizio stagione**: aggiornare `SEASON_ID` in `scraper.py` (vedi commento nel file).
- **Calendario di lega**: si genera/importa dall'app (Altro → Calendario
  Lega), resta valido tutta la stagione salvo correzioni manuali.
- Se una fonte HTML cambia struttura, il relativo job fallisce ma gli altri
  proseguono; l'ultimo JSON valido resta in uso dalla PWA. Gli errori sono
  registrati in `data/meta.json` e nel log del workflow.
- **Modificatore di Difesa / fasce Capitano**: i valori di default nel
  codice sono preset comuni (es. "modificatore a 3 fasce") — vanno
  corretti in Regole Lega con i valori reali della propria lega quando
  configurata.

## Limiti noti

- `titolarita_scraper.py` è stato validato contro un campione reale della
  pagina ma non ancora testato in produzione end-to-end nel workflow.
- Il matching nome→id (`player_name_matcher.py`) è pensato per fonti
  future senza ID compatibili con fantacalcio.it (es. Sky Sport); va
  esteso con un parser dedicato per fonte quando se ne aggiunge una nuova.
