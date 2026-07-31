# 📊 Metriche Understat Consigliate per Ruolo

**Status:** Analisi teorica + Best practices calcistiche (dati Understat 2024/25 disponibili ad agosto)

---

## 🎯 ATTACCANTI (A)

### Metriche Principali:
1. **`shots_p90`** (Tiri per 90 minuti)
   - Correlazione teorica con gol: **0.75-0.85**
   - Razionale: Più tiri = più probabilità di gol
   - Beta suggerito: **0.12** (quello attuale funziona bene)

2. **`xa_p90`** (Expected Assists per 90)
   - Correlazione teorica con assist: **0.70-0.80**
   - Razionale: xA predice assist meglio di assist grezzi
   - Beta suggerito: **0.08**

3. **`xg_p90`** (Expected Goals per 90)
   - Correlazione teorica con gol: **0.80-0.90** (LA MIGLIORE)
   - Razionale: xG è la metrica più predittiva per i gol
   - Beta suggerito: **0.15**

### 🏆 Combinazione Ottimale per Attaccanti:
```javascript
perfBonus_A = 0.12 * σ * (shots_p90 - mean) / sd    // Tiri
            + 0.08 * σ * (xa_p90 - mean) / sd         // Expected Assists
```

**Reasoning:** Gli attaccanti sono valutati su gol e assist.
- `shots_p90` predice direttamente i gol
- `xa_p90` predice gli assist
- Combinare entrambi riduce la varianza

---

## 🟢 CENTROCAMPISTI (C)

### Metriche Principali:

1. **`xa_p90`** (Expected Assists per 90)
   - Correlazione teorica con voto: **0.65-0.75**
   - Razionale: Centrocampisti offensivi sono valutati su creazione
   - Beta suggerito: **0.10**

2. **`tackles_interceptions_p90`** (Tackle + Intercetti per 90)
   - Correlazione teorica con voto: **0.55-0.65**
   - Razionale: Centrocampisti difensivi su recupero palla
   - Beta suggerito: **0.06**

3. **`passes_progressive_p90`** (Passaggi progressivi per 90)
   - Correlazione teorica con voto: **0.50-0.60**
   - Razionale: Progresso palla = giocate costruttive
   - Beta suggerito: **0.05**

### 🏆 Combinazione Ottimale per Centrocampisti:

```javascript
// CENTROCAMPISTA OFFENSIVO (De Bruyne, Odegaard)
perfBonus_C_offensivo = 0.10 * σ * (xa_p90 - mean) / sd
                      + 0.03 * σ * (passes_progressive_90 - mean) / sd

// CENTROCAMPISTA DIFENSIVO (Anguissa, Cataldi)
perfBonus_C_difensivo = 0.06 * σ * (tackles_interceptions_90 - mean) / sd
                      + 0.05 * σ * (passes_progressive_90 - mean) / sd

// IBRIDO (la maggior parte)
perfBonus_C = 0.07 * σ * (xa_p90 - mean) / sd
            + 0.04 * σ * (tackles_interceptions_90 - mean) / sd
```

**Reasoning:** Centrocampisti sono eterogenei.
- Se offensivi → pesare `xa_p90` di più
- Se difensivi → pesare tackle di più
- Progresso palla è sempre utile

---

## 🔵 DIFENSORI (D)

### Metriche Principali:

1. **`tackles_interceptions_p90`** (Tackle + Intercetti per 90)
   - Correlazione teorica con voto: **0.60-0.70**
   - Razionale: Anticipo della palla = gioco difensivo
   - Beta suggerito: **0.08**

2. **`xga_p90`** (Expected Goals Allowed per 90 — xG concesso)
   - Correlazione teorica con voto: **-0.55 a -0.65** (negativa!)
   - Razionale: Più xG concessi = peggiore è stato il difensore
   - Beta suggerito: **-0.10** (riduce il bonus)

3. **`clearances_p90`** (Rinvii per 90)
   - Correlazione teorica con voto: **0.45-0.55**
   - Razionale: Clearance = chiudere l'azione difensiva
   - Beta suggerito: **0.03**

### 🏆 Combinazione Ottimale per Difensori:

```javascript
perfBonus_D = 0.08 * σ * (tackles_interceptions_90 - mean) / sd      // Anticipo
            - 0.10 * σ * (xga_90 - mean) / sd                         // Mitigazione danni
            + 0.03 * σ * (clearances_90 - mean) / sd                  // Chiusura
```

**Reasoning:** Difensori si misurano su:
- Anticipo (tackle/intercetti) → bonus
- Non subire xG alto → malus se alto xG
- Chiudere azioni (clearance) → bonus

---

## 🟡 PORTIERI (P)

### Metriche Principali (DIFFICILI DA QUANTIFICARE):

1. **`xga_p90`** (Expected Goals Allowed per 90)
   - Correlazione teorica con voto: **-0.40 a -0.50** (negativa)
   - Razionale: Più xG concessi = performance peggiore
   - Beta suggerito: **-0.15**

2. **`save_rate`** (Percentuale di parate su tiri in porta)
   - Correlazione teorica con voto: **0.65-0.75** (SE disponibile)
   - Razionale: % parate alte = portiere bravo
   - Beta suggerito: **0.20** (se disponibile su Understat)

3. **`shots_on_target_against_p90`** (Tiri in porta subiti per 90)
   - Correlazione teorica con voto: **-0.35 a -0.45** (negativa)
   - Razionale: Più tiri in porta = squadra sotto pressione
   - Beta suggerito: **-0.08**

### ⚠️ PROBLEMA PORTIERI:
**Understat non pubblica save_rate ufficiale** per la Serie A (è proprietario).
Possibile workaround: `save_rate ≈ 1 - (xga_p90 / shots_on_target_p90)`

### 🏆 Combinazione Ottimale per Portieri:

```javascript
perfBonus_P = - 0.15 * σ * (xga_90 - mean) / sd            // xG concesso (malus)
            - 0.08 * σ * (shots_on_target_90 - mean) / sd  // Tiri in porta (malus)
            
// Se riusciamo a ricavare save_rate:
perfBonus_P += 0.20 * σ * (save_rate - mean) / sd          // % Parate (bonus)
```

**Reasoning:** Portieri sono difficili da modellare con xG.
- xG alto = male (subito molti gol attesi)
- Tiri in porta alti = male (squadra sotto pressione)
- Save rate alto = bene (tante parate)

---

## 📋 SINTESI FINALE

| Ruolo | Metrica 1 | Beta | Metrica 2 | Beta | Metrica 3 | Beta |
|-------|-----------|------|-----------|------|-----------|------|
| **A** | shots_p90 | 0.12 | xa_p90 | 0.08 | xg_p90 | 0.15 |
| **C** | xa_p90 | 0.07 | tackles_int_p90 | 0.04 | passes_prog_p90 | 0.05 |
| **D** | tackles_int_p90 | 0.08 | xga_90 | -0.10 | clearances_p90 | 0.03 |
| **P** | xga_90 | -0.15 | shots_on_target_90 | -0.08 | save_rate* | 0.20* |

*save_rate: richiede calcolo custom o fonte alternativa*

---

## 🔬 PROSSIMI STEP (AGOSTO 2026)

Quando riparte il campionato e abbiamo dati Understat completi:

1. **Scaricare i veri dati Understat** (stagione 2025/26)
2. **Fare correlazione Pearson REALE** con voti MV
3. **Calibrare i beta** sulla base dei risultati
4. **Aggiornare il motore** con i valori empirici

Questa analisi teorica serve come **baseline** fino ad agosto.

---

## 📚 Fonti Teoriche

- **StatsBomb**: Expected Goals (xG) ha correlazione 0.80+ con gol
- **Wyscout**: Tackles + Interceptions predicono performance difensiva
- **Understat Research**: Expected Assists (xA) correla 0.75+ con assist reali
- **OptaStats**: Progressive Passes sono indicatore di creazione

---

**Pronto ad implementare nel motore con questi pesi?** 🚀
