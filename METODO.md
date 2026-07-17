# Fantassist — Il motore, in dettaglio

*Relazione tecnica · luglio 2026 · motore ricalibrato il 17/07/2026*

Questo documento descrive **tutte** le formule del motore, la teoria che le giustifica, e — la parte più
importante — il confronto tra le costanti che ho **assunto a tavolino** e quelle **misurate** sui dati veri
della stagione 2025-26 (10.504 fantavoti reali, 586 giocatori, 37 giornate).

Anticipo le conclusioni:
1. **Tre costanti su sei erano sbagliate in modo misurabile** — ora corrette (Parte 3).
2. Il motore **ignorava la variabile più importante**: la forza della squadra del giocatore. Ora c'è (2.2-bis).
3. Una misura mette in discussione un'assunzione di fondo dell'intero impianto (3.6).
4. Le correzioni migliorano tutte le metriche fuori campione, ma il guadagno finale **non è ancora
   statisticamente dimostrato** (3-bis). Lo scrivo perché è vero.

---

## Parte 1 — Architettura

Il sistema ha tre stadi indipendenti:

```
[1] PIPELINE DATI          [2] MOTORE (in app)        [3] DECISIONI
    GitHub Actions             JavaScript locale          cosa vedi
    2 volte/settimana          gira sul telefono
    ↓                          ↓                          ↓
    players.json               rating giocatore           formazione ottima
    classifica.json      →     fantavoto atteso     →     distribuzione del punteggio
    calendario.json            simulazione                probabilità di vittoria
    rigoristi.json                                        spunti di mercato
    indisponibili.json
    (understat.json)
```

Scelta progettuale di fondo: **nessun server, nessun account**. La pipeline produce file statici, l'app li
legge e calcola tutto sul telefono. Le tue rose vivono nella memoria locale del browser. Costo: zero.
Prezzo: nessuna sincronizzazione tra dispositivi.

---

## Parte 2 — Le formule, una per una

### 2.1 Rating base — shrinkage bayesiano

Il problema: un attaccante con **2 presenze e fantamedia 8,5** è un fuoriclasse o un fortunato? La
fantamedia grezza dice "fuoriclasse". Il buon senso dice "aspetta".

La soluzione formale è lo **shrinkage** (restringimento verso la media), che nasce dal lavoro di
James e Stein (1961) e ha una lettura bayesiana naturale: la fantamedia osservata viene mescolata
con un *prior* di ruolo, pesando i due termini per quanta evidenza abbiamo.

```
                pv · FM  +  K · prior(ruolo)
   rating  =  ───────────────────────────────
                      pv  +  K
```

dove `pv` = presenze, `FM` = fantamedia stagionale, `K` = forza dello shrinkage.

**Lettura intuitiva**: è come se ogni giocatore partisse con `K` "partite fantasma" giocate esattamente
alla media del suo ruolo. Con poche presenze reali, quelle fantasma dominano e il giudizio resta prudente;
con 30 presenze, i dati veri prendono il sopravvento.

**Costanti attuali (ricalibrate il 17/07/2026)**: `K = {P: 28, D: 16, C: 15, A: 19}`,
`prior = {P: 5.02, D: 5.99, C: 6.20, A: 6.53}` — tutte **misurate**, non più assunte.

Il valore teoricamente ottimo di K (Bayes empirico) è:

```
   K*  =  σ²(rumore di giornata)  /  σ²(vera differenza tra giocatori)
```

Cioè: **quanto più il fantavoto di giornata è rumoroso rispetto alle vere differenze tra giocatori, tanto
più bisogna restringere**. Vedi Parte 3.6 per la misura — è la scoperta più importante del documento.

---

### 2.2 Δ calendario — funzione continua

Il tuo Excel del 2019 usava coefficienti **a gradini**: TOP7/FLOP7, moltiplicatori da 1,5 a 0,3. Funzionava,
ma aveva due difetti: la 7ª e l'8ª in classifica venivano trattate in modo radicalmente diverso pur essendo
quasi identiche (discontinuità arbitraria), e il coefficiente era *moltiplicativo* — penalizzava di più chi
già valeva di più, il che non ha giustificazione.

La versione attuale è **continua, additiva e dipendente dal ruolo**:

```
   Δcal(ruolo) =  HOME[ruolo] · (casa − 0,5)  +  OPP[ruolo] · (forza_avversario − 0,5)
```

con i coefficienti **misurati** (vedi 3.4 e 3.5):

| Ruolo | HOME | OPP |
|---|---|---|
| Portieri | +0,167 | **−1,018** |
| Difensori | +0,172 | −0,534 |
| Centrocampisti | +0,144 | −0,444 |
| Attaccanti | +0,155 | −0,891 |

Il Δ è *additivo* perché nel fantacalcio i bonus sono additivi: affrontare una difesa debole aggiunge
probabilità di gol, non moltiplica il talento.

**Perché dipende dal ruolo**: un portiere contro una squadra forte subisce più tiri e ogni gol è −1;
un centrocampista fa il suo lavoro più o meno uguale contro chiunque. La misura conferma:
il portiere è colpito **2,3 volte più** del centrocampista.

### 2.2-bis Forza della propria squadra — il termine nuovo

Il motore guardava solo l'avversario e **ignorava la squadra del giocatore**. I dati dicono che è
l'errore più grosso: la forza della *propria* squadra predice il fantavoto **più** di quella
dell'avversario (+0,825 contro −0,590; per i centrocampisti 1,8 volte tanto).

```
   team_adj(ruolo)  =  GAMMA[ruolo] · (forza_propria_squadra − 0,5)
```

| Ruolo | GAMMA |
|---|---|
| Portieri | +0,476 |
| Difensori | +0,432 |
| Centrocampisti | +0,436 |
| Attaccanti | +0,464 |

**Non è doppio conteggio** (obiezione ovvia: "chi gioca nell'Inter ha già una fantamedia alta"):
il termine resta **significativo in ogni ruolo anche controllando per la fantamedia passata**
del giocatore. Il motivo è profondo — la fantamedia individuale è una stima *rumorosissima*
(vedi 3.6), mentre la classifica della squadra è stimata su 38 partite × 11 giocatori, quindi è
un indicatore del contesto **molto più preciso** di quanto il giocatore dica di sé.

**Dove va**: la forza della propria squadra varia appena **0,005** dentro una stagione — è una
*costante del giocatore*, non un fattore di giornata. Perciò entra nel **rating**, non nel Δ
calendario. Architettura corretta:

```
   rating_giocatore  =  shrunk(fantamedia)  +  team_adj        ← costante nella stagione
   Δgiornata         =  Δcal(avversario, casa)                 ← cambia ogni settimana
```

*Nota storica: è esattamente l'intuizione del foglio Excel 2019 — "non conta il blasone, conta
la posizione attuale in classifica della squadra". I dati le danno ragione.*

**Nota**: a campionato fermo `Δcal = 0` per tutti — l'app lo dichiara esplicitamente.

---

### 2.3 Rigorista

```
   se rigorista:  +0,30
```

Giustificazione teorica: un rigore vale +3 (gol) e i rigori in Serie A sono circa 0,25 a partita per squadra,
con conversione ~78%. Il rigorista designato incassa quindi circa `0,25 × 0,78 × 3 ≈ 0,58` per partita
*quando la sua squadra ottiene un rigore*, spalmato su tutte le partite. Il valore di 0,30 è una stima
prudente. Vedi 3.3 per la misura.

Il flag viene proposto automaticamente dalla pagina rigoristi ma resta modificabile: la gerarchia reale
la conosci tu meglio di un sito.

---

### 2.4 Bonus performance — l'unico pezzo già misurato

Questo blocco **non** è frutto di intuizione: i pesi sono stati stimati su 7.270 osservazioni
giocatore-giornata con una regressione standardizzata, controllando per la forma passata.

```
   bonus  =  β(ruolo, segnale) · σ_FV(ruolo) · clamp( (valore − media) / sd , −2, +2 )
```

Il `clamp` a ±2 deviazioni standard evita che un valore anomalo (un giocatore con 3 partite e 8 tiri a
partita) faccia esplodere il bonus.

| Ruolo | Tiri p90 (β) | xA p90 (β) | xG p90 |
|---|---|---|---|
| Attaccanti | **0,112** | ~0 | scartato |
| Centrocampisti | **0,103** | ~0 | scartato |
| Difensori | 0,051 | **0,077** | scartato |
| Portieri | 0 | 0 | 0 |

**Due scoperte contro-intuitive emerse dalla validazione:**

1. **L'xG non serve, i tiri sì.** Messi entrambi nella stessa regressione, il volume di tiri predice il
   fantavoto futuro e l'xG non aggiunge nulla. Ragione: il fantacalcio premia il *fare gol* col +3, e chi
   tira spesso ha più occasioni di far scattare il bonus; la qualità-per-tiro conta meno della frequenza.
   *Il tuo foglio del 2019, che usava i tiri grezzi, aveva ragione.*

2. **Per i difensori vale l'xA, non i tiri.** I terzini e i braccetti che *creano* predicono il proprio
   fantavoto futuro meglio di quelli che tirano.

**Effetto pratico**: un attaccante che tira molto (+1 dev. std.) guadagna ≈ **+0,21** di fantavoto atteso;
un cecchino estremo (+2 sd) ≈ +0,42. È un tie-breaker, non un ribaltone — ed è giusto così.

⚠️ **Stato attuale: il bonus è spento**, perché manca il feed `understat.json`. Vedi Parte 4.

---

### 2.5 Fantavoto atteso e valore dello slot

```
   E[FV]  =  shrunk(fantamedia)  +  team_adj  +  Δcal(ruolo)  +  bonus_rigorista  +  bonus_performance
             └──────────── rating di giocatore ────────────┘   └── contesto di giornata ──┘
```

Ma un giocatore vale solo se **gioca**. Da qui il valore atteso dello *slot* in formazione:

```
   E[slot]  =  p_tit · E[FV]  +  (1 − p_tit) · BENCH_FV
```

dove `p_tit` è la probabilità di essere titolare (0-100%, che imposti tu) e `BENCH_FV = 4,0` è il valore
attribuito allo slot quando il titolare non gioca.

Questa formula è il cuore del tuo ragionamento originale: **la titolarità non è un dettaglio, è un
moltiplicatore**. Un fuoriclasse con p_tit = 30% vale meno di un onesto mestierante che gioca sempre.

---

### 2.6 Scelta del modulo

Per ciascuno dei 7 moduli si prende il meglio disponibile per reparto e si somma:

```
   EV(modulo)  =  Σ  E[slot_i]        per gli 11 titolari scelti greedy per ruolo
   modulo* = argmax EV(modulo)
```

**Perché il greedy è corretto qui**: i vincoli sono *separabili per ruolo* (1 portiere, D difensori,
C centrocampisti, A attaccanti) e non c'è interazione tra giocatori. In queste condizioni prendere i
migliori per ruolo è **provatamente ottimo**, non un'euristica. (Se un domani introducessimo il
modificatore di difesa, che premia la difesa *della stessa squadra*, questa proprietà cadrebbe e servirebbe
un solver vero — il tuo CP-SAT, per capirci.)

---

### 2.7 Simulazione Monte Carlo

Il valore atteso dice dove si va a parare *in media*. Ma tu la domenica giochi **una** partita, non mille.
Serve la distribuzione.

```
   ripeti 3.000 volte:
      totale = 0
      per ogni titolare:
          se  random() < p_tit:                        # gioca
              totale += E[FV] + σ(ruolo) · Z           # Z ~ Normale(0,1), Box-Muller
          altrimenti:                                   # non gioca → entra la panchina
              totale += E[FV_riserva] · 0,97 + σ · Z
      registra totale
```

Da cui: mediana, banda P10–P90, e **P(totale ≥ soglia)**.

**Assunzioni sotto**, tutte discutibili e tutte da segnalare:
- il fantavoto è **gaussiano**. In realtà è asimmetrico: il +3 del gol crea una coda destra. La gaussiana
  sottostima quindi la probabilità di exploit.
- i fantavoti sono **indipendenti** tra loro. Falso: due giocatori della stessa squadra sono correlati
  (se il Napoli vince 4-0, salgono tutti). Questo fa **sottostimare la varianza** del totale.
- le σ sono costanti per ruolo. Vedi 3.1.

---

### 2.8 Probabilità di vittoria (scheda Sfida)

Si simulano entrambe le formazioni e si confrontano campioni casuali:

```
   P(vinco)  =  P(X > Y)  +  ½ · P(X = Y)          X = mio totale, Y = totale avversario
```

su 4.000 accoppiamenti estratti dalle due distribuzioni. I pareggi si dividono a metà (nel fantacalcio
un pari secco è raro ma esiste, e va spartito).

⚠️ **Asimmetria dichiarata**: la *tua* formazione usa i tuoi ritocchi (titolarità, squalifiche); quella
avversaria parte da impostazioni standard (p_tit = 75% per tutti). Questo ti dà un lieve vantaggio
informativo che **gonfia la tua probabilità stimata**. Ne sono consapevole, l'app lo scrive.

---

### 2.9 Punteggio di mercato

```
   market_score  =  (rating + team_adj) · (0,15  +  0,85 · min(pv / 25 , 1))
                     ↑                    ↑
                  qualità            titolarità (25 presenze ≈ titolare fisso)
```

La titolarità entra come **moltiplicatore quasi puro**: chi non gioca mai viene azzerato quasi del tutto,
esattamente com'era nella tua richiesta ("non è solo la sua media che mi interessa, bensì la sua titolarità").

Svincolato = giocatore il cui id non compare in **nessuna** rosa della lega selezionata.

---

## Parte 3 — La verifica: assunto contro misurato

Ecco la parte che conta. Ho preso le costanti del motore e le ho confrontate con la realtà della
stagione 2025-26.

### 3.1 σ (sigma) — la volatilità del fantavoto

| Ruolo | Assunta | **Misurata** | Errore |
|---|---|---|---|
| Portieri | 1,10 | **1,55** | **+40%** ❌ |
| Difensori | 1,20 | **1,07** | −11% ⚠️ |
| Centrocampisti | 1,40 | **1,33** | −5% ✓ |
| Attaccanti | 1,90 | **1,90** | 0% ✓ |

Attaccanti perfetti, centrocampisti ottimi. Ma i **portieri** li avevo giudicati i più stabili e sono invece
i secondi più volatili: clean sheet contro tre gol subiti, più i rigori parati (+3), producono oscillazioni
larghe. Conseguenza pratica: **l'app sottostima l'incertezza** quando hai un portiere in campo, cioè sempre.

### 3.2 Prior di ruolo

| Ruolo | Assunto | **Misurato** | Errore |
|---|---|---|---|
| Portieri | 4,60 | **5,02** | +0,42 ⚠️ |
| Difensori | 5,80 | **5,99** | +0,19 |
| Centrocampisti | 6,10 | **6,20** | +0,10 ✓ |
| Attaccanti | 6,40 | **6,53** | +0,13 ✓ |

Sistematicamente un po' bassi, ma nell'ordine di grandezza giusto. Il portiere è di nuovo il peggiore.

### 3.3 Bonus rigorista

| Ruolo | Misurato | Nel motore |
|---|---|---|
| Centrocampisti | **+0,33** | +0,30 ✓ |
| Attaccanti | **+0,48** | +0,30 ⚠️ |

Onestà statistica: campioni piccolissimi (7 centrocampisti e 5 attaccanti con ≥3 rigori calciati). È un
indizio, non una prova. Ma suggerisce che per gli attaccanti il bonus vada alzato.

### 3.4 Fattore casa ❌

| | Valore |
|---|---|
| Nel motore | ±0,15 → **scarto casa−trasferta = 0,30** |
| **Misurato** | **scarto = +0,146 ± 0,059** (significativo) |

**Il motore raddoppia il vantaggio del campo.** Il valore corretto sarebbe `±0,073`.

Per ruolo: difensori +0,170 e centrocampisti +0,131 (entrambi significativi); portieri +0,134 e
attaccanti +0,139 non raggiungono la significatività per via del campione più piccolo.

### 3.5 Forza dell'avversario ❌ (e la scoperta del ruolo)

| | Pendenza |
|---|---|
| Nel motore | **−0,90** (uguale per tutti) |
| **Misurato (tutti)** | **−0,626 ± 0,117** |

Il segno è giusto e l'effetto è reale e significativo, ma **il motore lo esagera del ~44%**.

E qui la scoperta vera — **l'effetto dipende fortissimamente dal ruolo**:

| Ruolo | Pendenza misurata | Lettura |
|---|---|---|
| **Portieri** | **−1,274** | affrontare la prima invece dell'ultima costa 1,27 di fantavoto |
| Attaccanti | −0,858 | |
| Difensori | −0,498 | |
| Centrocampisti | −0,473 | quasi indifferenti all'avversario |

Un portiere è colpito **2,7 volte più di un centrocampista**. Ha perfettamente senso: contro una squadra
forte il portiere subisce più tiri e ogni gol è −1; il centrocampista fa il suo lavoro più o meno uguale
contro chiunque. **Il motore ignora completamente questa differenza.**

### 3.6 K_SHRINK — la scoperta che ribalta il tavolo ❌❌

| Ruolo | σ²(rumore giornata) | σ²(vere differenze) | **K\* ottimo** | Nel motore |
|---|---|---|---|---|
| Portieri | 2,376 | 0,084 | **28,4** | 8 |
| Difensori | 1,064 | 0,065 | **16,4** | 8 |
| Centrocampisti | 1,622 | 0,105 | **15,4** | 8 |
| Attaccanti | 3,306 | 0,170 | **19,4** | 8 |

**Il motore restringe da 2 a 3,5 volte troppo poco.** Ma il dato davvero impressionante è il rapporto tra
le due varianze: il **rumore di giornata è 10-28 volte più grande delle vere differenze tra giocatori**
dello stesso ruolo.

Detto brutalmente: **due centrocampisti presi a caso in Serie A sono molto più simili di quanto la
fantamedia lasci credere**, e quasi tutto ciò che vedi in una singola giornata è caso.

La conferma indipendente:

| Ruolo | correlazione(fantamedia passata → fantavoto successivo) |
|---|---|
| Portieri | +0,078 |
| Difensori | +0,143 |
| Centrocampisti | +0,137 |
| Attaccanti | +0,110 |

*(Il +0,239 "complessivo" è ingannevole: cattura soprattutto il fatto che gli attaccanti segnano più dei
difensori, non che i giocatori bravi rendano più di quelli scarsi.)*

**Cosa significa, onestamente**: il potere predittivo di *qualunque* modello basato su fantamedia e
statistiche è **strutturalmente piccolo**. Non è un difetto del nostro motore: è la natura del gioco. Chi
ti vende il "sistema infallibile" mente.

Ma attenzione a non trarre la conclusione sbagliata: **un vantaggio piccolo ripetuto 38 volte è comunque
un vantaggio**. È esattamente la logica del banco al casinò — margine minimo, tanti giri. La differenza è
che ora *sappiamo quanto* è piccolo, invece di illuderci.

### 3.7 BENCH_FV

| Ruolo | Rendimento medio delle riserve (3-12 presenze) |
|---|---|
| Portieri | 4,53 |
| Difensori | 5,67 |
| Centrocampisti | 5,96 |
| Attaccanti | 6,19 |

Nel motore: **4,0 fisso per tutti** — assunto senza alcuna base.

Va detto però che `BENCH_FV` non modella "quanto rende una riserva" ma "quanto vale lo slot quando il
titolare non gioca", che dipende dalle **regole di sostituzione della tua lega**. Va ripensato, non solo
ritarato.

---

## Parte 4 — Cosa non va, in ordine di gravità

### 🔴 1. La pipeline legge colonne sbagliate (bloccante)

La `players.json` attuale ha **fantamedie tra 0 e 3** (media 0,03) e presenze fino a **54** in una stagione
da 38. I portieri hanno "fantamedia" uguale ai gol subiti. Traduzione: **il motore sta girando su dati non
validi**, non solo il Mercato ma anche i rating in Formazione e Sfida.

Causa: fuori stagione la pagina statistiche di fantacalcio.it ha un'altra struttura e l'abbinamento delle
colonne pesca le caselle sbagliate.

**Quando**: fine agosto, a campionato ripartito. Serve una diagnosi dal vivo della pagina vera.

### 🟠 2. Il feed Understat non esiste → bonus performance spento

L'unico pezzo del motore *validato sui dati* è inattivo, perché manca il job che produce `understat.json`
con `shots_p90` e `xa_p90` aggiornati. Il codice è pronto e testato: manca la benzina.

**Quando**: a stagione avviata. Lo scraper Understat via `soccerdata` funziona già (l'abbiamo collaudato).

### ✅ 3. Le costanti sbagliate — CORRETTO il 17/07/2026

| Costante | Prima (assunta) | Ora (misurata) |
|---|---|---|
| `K_SHRINK` | 8 per tutti | **{P: 28, D: 16, C: 15, A: 19}** |
| forza avversario | −0,90 per tutti | **{P: −1,018, D: −0,534, C: −0,444, A: −0,891}** |
| fattore casa | ±0,15 | **±HOME/2 ≈ ±0,08** per ruolo |
| `SIGMA` | P1,1 D1,2 C1,4 A1,9 | **P1,55 D1,07 C1,33 A1,90** |
| `PRIOR` | P4,6 D5,8 C6,1 A6,4 | **P5,02 D5,99 C6,20 A6,53** |
| forza propria squadra | *assente* | **{P: 0,476, D: 0,432, C: 0,436, A: 0,464}** ⬅ nuovo |

**Non ricalibrate, di proposito:**
- `RIG_BONUS` (0,30): la misura suggerisce +0,48 per gli attaccanti, ma su **n < 10**. Troppo fragile.
- `BENCH_FV` (4,0): va **ripensato**, non ritarato — dipende dalle regole di sostituzione della lega.

---

### 3-bis. La verifica delle correzioni: funzionano davvero?

Domanda onesta: le nuove costanti sono un miglioramento vero o sto inseguendo il rumore del 2025-26?

**Test fuori campione**: ho ri-stimato *tutto* usando solo le giornate 1-19 e verificato sulle
giornate 20-38, che il motore non aveva mai visto.

| Metrica (giornate 20-38) | Vecchio | Nuovo |
|---|---|---|
| RMSE | 1,4010 | **1,3936** (+0,52%) |
| MAE | 0,9244 | **0,9192** (+0,56%) |

**Capacità di ordinare i giocatori** (correlazione di rango dentro ruolo e giornata — è ciò che serve
davvero per scegliere la formazione):

| Ruolo | Vecchio | Nuovo | Δ |
|---|---|---|---|
| **Portieri** | +0,217 | **+0,278** | **+0,060** |
| Difensori | +0,255 | +0,256 | +0,001 |
| Centrocampisti | +0,194 | +0,226 | +0,032 |
| Attaccanti | +0,176 | +0,204 | +0,028 |

**Ablazione** (quanto pesa ogni pezzo, fuori campione):

| Correzione | RMSE |
|---|---|
| solo K per ruolo | 1,4013 (≈ nessun guadagno) |
| K + avversario per ruolo | 1,3993 |
| **+ forza propria squadra** | **1,3936** |

⚠️ **Il contributo maggiore viene dalla forza della propria squadra** — cioè dall'intuizione del 2019,
non dalle ricalibrazioni statistiche.

**Il test finale, e il suo limite**. Schierando ogni giornata la miglior formazione 1-3-3-2 secondo
ciascun motore:

| | Punti medi a giornata |
|---|---|
| Vecchio | 61,42 |
| Nuovo | **61,67** |

**+0,25 punti a giornata → +9,5 punti in una stagione.** Ma: errore standard **±0,93**, t = 0,27,
meglio in **11 giornate su 18**. Con 18 giornate **il guadagno NON è statisticamente significativo**.

**Lettura onesta**: il segno è giusto, coerente in tutte le metriche, e il miglioramento nell'ordinare
è misurato su migliaia di osservazioni (quindi solido). Ma il beneficio finale in punti resta dentro il
rumore e **non è dimostrato**. Le correzioni sono applicate perché sostituire costanti *inventate* con
costanti *misurate* è giusto per principio — non perché sia provato che facciano vincere.

Serve una seconda stagione per dirlo con certezza.

### 🟡 4. Bonus non configurabili per lega

Il fantavoto è calcolato con le regole classiche: `+3` gol, `+1` assist, `+3` rigore parato, `−3` rigore
sbagliato, `−2` autogol, `−1` gol subito, `−0,5` ammonizione, `−1` espulsione.

Ma le leghe cambiano: **assist +1 o +3**, modificatore di difesa sì/no, portiere imbattuto. Se la tua
FantaPasseri usa regole diverse, il motore ottimizza per il gioco sbagliato.

### 🟡 5. Palle recuperate: mancano ancora

Il segnale difensivo del tuo Excel 2019 non è mai rientrato. Understat non le ha; legaseriea.it sì, ma ha
rifatto l'API e va ritrovata. Con quelle, i difensori avrebbero il loro segnale proprio invece di
accontentarsi dell'xA.

### 🟡 6. Limiti del Monte Carlo

- **Gaussiana**: sottostima le code (il +3 del gol crea asimmetria).
- **Indipendenza**: fantavoti della stessa squadra sono correlati → **la varianza del totale è sottostimata**,
  quindi le tue bande P10-P90 sono più strette del vero e la P(vittoria) è troppo "sicura" di sé.
- **Titolarità a mano**: `p_tit` parte da 75% e la aggiusti tu. Con le probabili formazioni scaricate
  automaticamente sarebbe un dato, non un'opinione.

### 🟢 7. Cose minori

- Nella Sfida, l'avversario è valutato con impostazioni standard (asimmetria dichiarata).
- Il modificatore di difesa non esiste (e romperebbe l'ottimalità del greedy: servirebbe un solver).
- Nessuna sincronizzazione tra dispositivi (scelta consapevole).

---

## Parte 5 — Cosa farei, in ordine

1. **Agosto, a campionato avviato**: riparare la pipeline (🔴 1). Senza dati veri, tutto il resto è teoria.
2. **Subito dopo**: aggiungere il job Understat (🟠 2) → si accende il bonus performance già validato.
3. ~~Applicare le correzioni misurate~~ ✅ **fatto il 17/07/2026** (vedi 3-bis).
4. **Prima giornata utile**: verificare le regole bonus della tua lega e renderle configurabili (🟡 4).
5. **Durante la stagione**: agganciare le palle recuperate dalla Lega (🟡 5) e rifare la validazione dei
   difensori con quel quarto segnale.
6. **A fine stagione 2026-27**: rifare *tutta* la validazione su due stagioni. Allora i pesi non saranno più
   una fotografia, ma una stima.

---

## Parte 6 — Una conclusione onesta

Il risultato più importante di questo lavoro non è una formula: è la **misura del rumore** (3.6).

Il fantacalcio è un gioco in cui il caso della singola giornata sovrasta la bravura di un fattore 10-28.
Nessun algoritmo può cambiarlo. Quello che un buon motore può fare è **spostare un margine sottile, e
spostarlo sempre nella stessa direzione**, per 38 giornate.

Questo è esattamente ciò che il tuo Excel del 2019 già faceva, per intuizione. La differenza è che ora
abbiamo *misurato* quanto quel margine è sottile — e sappiamo quali leve lo allargano davvero (la
titolarità, il calendario, i tiri) e quali sono decorazione.

Il **Fattore C**, in fondo, non era una battuta.

---

*Documento generato per Al · Fantassist 2.0 · GPL-3.0*
*Dati: fantacalcio.it (voti stagione 2025-26, uso personale) e Understat (statistiche di prestazione).*
*Tutte le misure sono riproducibili dai file `voti_2025_26_consolidati.csv` e `understat_permatch.csv`.*
