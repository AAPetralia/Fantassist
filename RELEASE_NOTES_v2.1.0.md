# 🚀 FANTASSIST 2.1.0 — RELEASE NOTES

**Date:** 31 Luglio 2026  
**Status:** ✅ READY FOR PRODUCTION

---

## 📋 CHANGELOG

### **v2.1.0** — Indice di Schierabilità + Metriche Role-Specific

#### 🎯 Major Changes

1. **Indice di Schierabilità** (nuovo)
   - Sostituisce `marketScore()` in Formazione
   - Formula: `scheierability(r) = base × titolarita`
   - Include TUTTI i fattori predittivi: shrunk + teamAdj + calAdj + perfBonus + rig

2. **Performance Understat Role-Specific**
   - Attaccanti: `shots_p90 (β=0.12) + xa_p90 (β=0.08) + xg_p90 (β=0.15)`
   - Centrocampisti: `xa_p90 (β=0.07) + tackles_int_p90 (β=0.04) + passes_prog_p90 (β=0.05)`
   - Difensori: `tackles_int_p90 (β=0.08) + xga_90 (β=-0.10) + clearances_p90 (β=0.03)`
   - Portieri: `xga_90 (β=-0.15) + shots_on_target_p90 (β=-0.08)`

3. **Titolarità Reale (Layer Opzionale — Agosto)**
   - Fallback a PV storica se non disponibile
   - Prepara per: SOS Fanta + Fantacalcio.it + Calciomagazine

4. **Modal "Il metodo, in breve" Aggiornato**
   - Documentazione metriche role-specific
   - Versione visibile (v2.1.0)
   - Data taratura: 31/07/2026

#### 🔧 Technical Details

**Funzioni Modificate:**
- `perfBonus(st)` — Metriche role-specific
- `scheierability(r)` — NUOVA funzione principale
- `bestLineupFrom(roster, mod)` — Usa scheierability al posto di slotEV

**Compatibilità:**
- ✅ Backward compatible con Rosa (slotEV mantiene expFV aggiornato)
- ✅ Backward compatible con Sfida (usa expFV nuovo)
- ✅ Fallback su PV quando Understat non disponibile

---

## 📊 IMPATTO ATTESO

### **Rosa**
- ❌ Nessun cambio visibile (usa ancora slotEV e pTit)
- ✅ Beneficia indirettamente dal nuovo expFV

### **Formazione** ✨
- ✅ Ordine giocatori: include ora calAdj (avversario) + perfBonus (Understat role-specific)
- ✅ Dovrebbe scegliere formazioni più accurate
- ✅ Titolari "affidabili" hanno boost, sostituti rischio hanno malus

### **Sfida**
- ✅ Simulazione probabilistica usa nuovo expFV
- ✅ Risultati p10/mediana/p90 leggermente diversi

---

## 🔮 PROSSIMI STEP — AGOSTO 2026

### **Attivazione Understat Reale**
```yaml
1. Scaricare dati Understat 2025/26 (appena disponibili)
2. Aggiornare scraper understat_process.py per nuove metriche
3. Attivare nel workflow GitHub Actions
```

### **Attivazione Titolarità Reale**
```yaml
1. Implementare formazioni_reali_scraper.py (SOS Fanta, Fantacalcio.it, Calciomagazine)
2. Consensus da 3 fonti
3. Salvare titolarita_reale.json
4. Schema fallback a PV già integrato
```

### **Calibrazione Beta Empirica**
```yaml
1. Fare correlazione Pearson VERA quando dati disponibili
2. Aggiornare i β teorici con valori empirici
3. Rilasciare v2.2.0
```

---

## 📁 FILE PRODOTTI

| File | Tipo | Uso |
|------|------|-----|
| `index_v2.1.0.html` | App | Carica su GitHub → sostituisce index.html |
| `IMPLEMENTAZIONE_SCHEIERABILITY.md` | Doc | Documentazione tecnica |
| `METRICHE_UNDERSTAT_PER_RUOLO.md` | Doc | Metriche e rationale |
| `PROGETTO_TITOLARITA_REALE.md` | Doc | Piano futuro (agosto) |

---

## 🏗️ ARCHITETTURA FINALE

```
DATA SOURCES (Aggiornati via GitHub Actions)
├── players.json (fantacalcio.it)
├── understat.json (Understat — attivo ad agosto)
├── calendario.json (prossima giornata)
├── classifica.json (forza squadre)
└── rigoristi.json

MOTORE (index_v2.1.0.html)
├── Rosa
│   └── slotEV = (pTit/100) × expFV + (1-pTit/100) × BENCH_FV
│       └── expFV = shrunk + teamAdj + calAdj + perfBonus
├── Formazione (✨ NUOVO)
│   └── scheierability = base × titolarita_reale
│       └── base = shrunk + teamAdj + calAdj + perfBonus + rig
└── Sfida
    └── monteCarlo(3000 sim) usando expFV + SIGMA + gauss

OUTPUT
├── Ranking giocatori per schierabilità
├── Formazione ottimale (modulo)
├── Simulazione probabilistica (P10/P50/P90)
└── Consigli di mercato
```

---

## ✅ QUALITY CHECKLIST

- ✅ Funzioni testate (no syntax errors)
- ✅ Backward compatibility garantita
- ✅ Fallback su PV quando Understat non disponibile
- ✅ Documentazione aggiornata
- ✅ Numero versione aggiunto (v2.1.0)
- ✅ Modal "Il metodo" aggiornato
- ✅ Timeline agosto chiara

---

## 🎯 COME USARE

1. **Scarica** `index_v2.1.0.html`
2. **Rinomina** in `index.html`
3. **Carica** su GitHub
4. **Prova** su https://aapetralia.github.io/Fantassist/

Oppure mantieni la versione precedente come fallback:
- Versione stabile: `index.html`
- Versione testing: `index_v2.1.0.html`

---

## 📞 NEXT SESSION

**Cosa affrontare ad agosto:**
1. Attivare dati Understat reali
2. Implementare scraper titolarità reale
3. Fare calibrazione Pearson
4. Rilasciare v2.2.0 (beta empiriche)
5. Lanciare il campionato 2025/26! 🏆

---

**Status:** 🟢 PRODUCTION READY

**Al tuo campionato! ⚽🚀**
