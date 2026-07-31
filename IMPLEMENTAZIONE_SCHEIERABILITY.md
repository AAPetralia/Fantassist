# ✅ IMPLEMENTAZIONE INDICE DI SCHIERABILITÀ — RIEPILOGO

**Data:** 31 Luglio 2026  
**Status:** 🟢 IMPLEMENTATO

---

## 🎯 COSA È CAMBIATO

### **PRIMA:**
```javascript
// FORMAZIONE (INCOMPLETO)
marketScore(st) = (shrunk(st) + teamAdj(st)) × (0.15 + 0.85×availab(st))
                  ❌ Manca calAdj (avversario prossima giornata)
                  ❌ Manca perfBonus (Understat)
                  ❌ Moltiplicatore hardcoded (0.15 + 0.85)
```

### **DOPO:**
```javascript
// FORMAZIONE (COMPLETO)
scheierability(st) = (shrunk(st) + teamAdj(st) + calAdj(st) + perfBonus(st)) × titolarita_reale(st)
                     ✅ Inclusi TUTTI i fattori
                     ✅ Understat role-specific
                     ✅ Titolarità reale (fallback a PV se non disponibile)
```

---

## 📋 DETTAGLI IMPLEMENTAZIONE

### **1. Funzione `perfBonus()` — Aggiornata per ruolo-specific**

```javascript
function perfBonus(st) {
  // Metriche specifiche per ruolo da Understat:
  
  // ATTACCANTI (A): Offensiva pura
  // metrics = ["shots_p90", "xa_p90", "xg_p90"]
  
  // CENTROCAMPISTI (C): Mix difesa + creazione
  // metrics = ["xa_p90", "tackles_interceptions_p90", "passes_progressive_p90"]
  
  // DIFENSORI (D): Anticipo + mitigazione danni
  // metrics = ["tackles_interceptions_p90", "xga_90", "clearances_p90"]
  
  // PORTIERI (P): Mitigazione senza save_rate (non disponibile)
  // metrics = ["xga_90", "shots_on_target_p90"]
}
```

### **2. Funzione `scheierability()` — NUOVA**

```javascript
function scheierability(r) {
  // BASE: Tutto ciò che predice il voto IN CAMPO
  const base = shrunk(st)           // Rating core (Fantamedia)
              + teamAdj(st)         // Forza squadra (costante stagione)
              + calAdj(st, role)    // Avversario prossima giornata
              + perfBonus(st)       // Understat (role-specific)
              + rig_bonus;          // Se rigorista
  
  // TITOLARITÀ: Certezza che gioca
  const titolarita = titolarita_reale[st.id]?.confidence 
                     ?? Math.min(1, st.pv / 25);
  
  // RISULTATO: Base × probabilità di giocare
  return base × titolarita;
}
```

### **3. Funzione `bestLineupFrom()` — Aggiornata**

```javascript
// FORMAZIONE: Ordina per scheierability (valore QUANDO gioca)
const by = role => avail
  .filter(r => roleOf(S.byId.get(r.id)) === role)
  .sort((a,b) => scheierability(b) - scheierability(a));

// EV: Valore totale formazione (scheierability, non slotEV)
ev: xi.reduce((s,r) => s + scheierability(r), 0)
```

---

## 📊 METRICHE UNDERSTAT PER RUOLO (Pesi Teorici)

| Ruolo | Metrica 1 | β | Metrica 2 | β | Metrica 3 | β |
|-------|-----------|------|-----------|------|-----------|------|
| **A** | shots_p90 | 0.12 | xa_p90 | 0.08 | xg_p90 | 0.15 |
| **C** | xa_p90 | 0.07 | tackles_int_p90 | 0.04 | passes_prog_p90 | 0.05 |
| **D** | tackles_int_p90 | 0.08 | xga_90 | -0.10 | clearances_p90 | 0.03 |
| **P** | xga_90 | -0.15 | shots_on_target_90 | -0.08 | — | — |

---

## 🔄 PROPAGAZIONE NEI SEZIONI

### **ROSA**
- **Formula:** `slotEV(r) = (pTit/100) × expFV.val + (1-pTit/100) × BENCH_FV`
- **Significato:** Valore di portafoglio (considerando panchina)
- **Cambio:** ✅ Mantiene expFV aggiornato automaticamente

### **FORMAZIONE** (AGGIORNATO ✨)
- **Formula:** `scheierability(r) = base × titolarita_reale`
- **Significato:** Valore QUANDO gioca (esclude panchina)
- **Cambio:** ✅ Ora include `calAdj + perfBonus` (prima mancava!)

### **SFIDA**
- **Formula:** `monteCarlo(3000 sim) usando expFV + SIGMA + gauss`
- **Significato:** Simulazione probabilistica
- **Cambio:** ✅ Usa automaticamente il nuovo expFV

---

## 🔮 TITOLARITÀ REALE — Layer Opzionale (AGOSTO)

Quando le **probabili formazioni** saranno disponibili (agosto):

```javascript
// AD AGOSTO: Attiva titolarita_reale.json
S.titolarita_reale = {
  "player_id_1": {
    "status": "titolare",
    "confidence": 1.0,
    "fonti": ["SOS Fanta", "Fantacalcio.it", "Calciomagazine"]
  },
  ...
}

// scheierability() userà automaticamente il nuovo valore
scheierability = base × 1.0  // Titolare certo
scheierability = base × 0.5  // Ballottaggio
scheierability = base × 0.0  // Fuori
```

**Fallback:** Se non disponibile, usa PV storica (come ora)

---

## 📈 IMPATTO ATTESO

### **Prima** (senza calAdj + perfBonus)
- Formazione non considera l'avversario della prossima giornata
- Formazione non usa Understat (performance storica)
- Rating fisso per tutta la stagione

### **Dopo** (con calAdj + perfBonus)
- ✅ Formazione aggiornata ogni giornata (avversario diverso)
- ✅ Formazione migliora con Understat ad agosto
- ✅ Attaccanti con xG alto → rating più alto
- ✅ Difensori con xGA basso → rating più alto
- ✅ Titolarità reale overrides PV storica (ad agosto)

---

## 🚀 TIMELINE

**ORA (Luglio 2026):**
- ✅ Motore implementato con `scheierability`
- ✅ Metriche role-specific Understat integrate
- ⏸️ Titolarità reale non disponibile (fallback a PV)

**AGOSTO 2026 (Campionato riprende):**
- ✅ Attiva `understat.json` (dati veri 2025/26)
- ✅ Attiva `titolarita_reale.json` (da 3 fonti: SOS Fanta, Fantacalcio.it, Calciomagazine)
- ✅ Motore raggiunge MASSIMA ACCURACY

---

## 📝 TEST CONSIGLIATI

1. **Rosa:** Malen dovrebbe avere `slotEV ≠ scheierability`
   - slotEV include probabilità panchina
   - scheierability è valore puro se gioca

2. **Formazione:** Ordine dei giocatori deve cambiare
   - Prima: ordinato per slotEV
   - Dopo: ordinato per scheierability (include calAdj + perfBonus)

3. **Sfida:** Totale atteso leggerm ente diverso
   - Usa il nuovo expFV (con perfBonus role-specific)

---

**✅ IMPLEMENTAZIONE COMPLETATA**  
**📅 Pronto per il campionato 2025/26!** 🚀
