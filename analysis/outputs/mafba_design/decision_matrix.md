# Decision matrix — outcomes del experimento → confidence updates → next steps

**Pre-resolve item 8 — instrumentación de calibración del sustrato**

Este documento mapea outcomes del experimento N (cualquier TF candidato) a:
1. Posterior confidence updates (Bayesian-flavored)
2. Decisiones de siguiente paso
3. Implicaciones para Tests del sustrato Witt
4. Priors actualizados post-pleiotropy

---

## 1. Priors actualizados (post-pleiotropy check)

El item 7 (pleiotropy comparativo) reveló que **el ranking original priorizaba TFs presentes en pronefros sin distinguir specificity**. Los priors deben actualizarse:

| Candidato | Tier original | Pre-pleiotropy prior | Specificity ratio | **Pre-experiment prior actualizado** |
|---|---|---|---|---|
| `pax2a` | T1 | 0.85 (validated literature) | 0.939 | **0.92** (validated + relatively specific) |
| `wt1a` | T2 | 0.75 (validated) | 0 (in duct subset) | **0.80** (already validated MO data) |
| `wt1b` | T2 | 0.75 (validated) | 0 | **0.78** (validated, complementary to wt1a) |
| `sim1a` | T3 | 0.70 (validated) | 0 | **0.75** (validated MO data) |
| `dzip1l` | T3 | 0.75 (validated ARPKD) | 0.233 | **0.78** (ciliopathy-specific function) |
| `hoxb8a` | T3 | 0.55 (novel) | 0.785 | **0.65** (most specific novel candidate) |
| `sall1a` | T3 | 0.55 (novel) | 0.498 | **0.55** (mouse evidence + medium specificity) |
| `hipk2` | T3 | 0.55 (novel) | 0.443 | **0.45** (lower specificity, mouse evidence) |
| `mafba` | T1 | 0.55 (novel) | 0.145 | **0.30** (very pleiotropic — likely confounded experiment) |
| `ripply1` | T2 | 0.55 (novel) | 0.129 | **0.28** (very pleiotropic) |
| `prox1a` | T3 | 0.55 (novel) | 0.046 | **0.18** (almost certainly bystander or pleiotropic) |
| `foxj1b` | T3 | 0.55 (indirect) | 0.214 | **0.40** (cilia function, not specific) |
| `tbx2b` | bonus | 0.75 (validated) | 0.18 | **0.70** (validated DL fate, but pleiotropic) |

**Ranking final por probability of being a clean pronefros regulator amenable to global KO:**
1. `pax2a` (0.92) — already validated, no need new experiment
2. `dzip1l` (0.78) — already validated, ARPKD
3. `wt1a` / `wt1b` / `sim1a` (~0.78) — already validated
4. `tbx2b` (0.70) — bonus, already validated
5. **`hoxb8a` (0.65) — top novel candidate**
6. `sall1a` (0.55) — second novel candidate
7. `hipk2` (0.45) — third novel candidate
8. `foxj1b` (0.40) — indirect evidence only
9. `mafba` (0.30) — pleiotropy too high for clean global KO
10. `ripply1` (0.28)
11. `prox1a` (0.18) — likely bystander

---

## 2. Outcome categories del experimento

Para cualquier TF candidato (gene-agnostic), el experimento testea 5 predicciones (P1-P5 from `2026-05-09_mafba_experiment_design.html` §2.3):

- **P1:** n cells in target cluster decreases in KO
- **P2:** % cells expressing primary marker[0] decreases
- **P3:** 3+ of 4 primary markers significantly affected
- **P4:** Control markers (general identity) NOT changed (specificity check)
- **P5:** Effect more pronounced 24 → 48 → 72 hpf

Outcomes posibles (n predicciones soportadas / 5):

| Outcome | n predicciones | Likelihood ratio* | Verdict | Posterior confidence |
|---|---|---|---|---|
| **STRONGLY SUPPORTED** | 4-5 | ~10× | H1 fuertemente soportada | ~0.85-0.95 |
| **PARTIALLY SUPPORTED** | 3 | ~3× | H1 parcialmente soportada | ~0.70 |
| **MARGINAL** | 2 | ~1× (no update) | Ambiguous | ~0.45 |
| **WEAKLY AGAINST** | 1 | ~0.3× | H0 más probable | ~0.25 |
| **NOT SUPPORTED** | 0 | ~0.1× | H0 fuertemente soportada | ~0.10 |

*Likelihood ratios son heurísticos basados en assumption de tests P1-P5 razonablemente independientes.

---

## 3. Posterior confidence formula

`posterior = prior × LR / [(prior × LR) + (1 - prior)]`

Worked example para hoxb8a (prior 0.65):

| Outcome | LR | Posterior |
|---|---|---|
| STRONGLY SUPPORTED (4+) | 10 | **0.949** |
| PARTIALLY SUPPORTED (3) | 3 | **0.848** |
| MARGINAL (2) | 1 | 0.65 (no update) |
| WEAKLY AGAINST (1) | 0.3 | 0.358 |
| NOT SUPPORTED (0) | 0.1 | 0.157 |

Worked example para mafba (prior 0.30):

| Outcome | LR | Posterior |
|---|---|---|
| STRONGLY SUPPORTED (4+) | 10 | 0.811 |
| PARTIALLY SUPPORTED (3) | 3 | 0.563 |
| MARGINAL (2) | 1 | 0.30 (no update) |
| WEAKLY AGAINST (1) | 0.3 | 0.114 |
| NOT SUPPORTED (0) | 0.1 | 0.041 |

**Implicación:** con prior bajo (mafba 0.30), incluso un STRONGLY SUPPORTED outcome solo sube posterior a 0.81 — no a 0.95. Pero con prior alto (hoxb8a 0.65), el mismo outcome llega a 0.95. Esto explica por qué mover el experimento a hoxb8a es más informativo.

---

## 4. Decisión de siguiente paso por outcome

| Outcome | Decisión recomendada | Acción Witt × Organogenesis |
|---|---|---|
| **STRONGLY SUPPORTED** (4-5/5) | Publicar paper. Generar stable mutant line para Phase II. | TF añadido a programa pruned (puerta Parsimonia). Substrate evidence: Test 4 calibration update +0.4. |
| **PARTIALLY SUPPORTED** (3/5) | Análisis adicional: subcluster effects, pseudobulk DE, alternative resolutions. WISH validation. Si still positivo → publicar. | TF en programa pruned con caveat. Test 4 update +0.2. |
| **MARGINAL** (2/5) | No moverse de la conclusión. Re-design con stable line + tissue-specific KO si Phase II permite. Considerar pivot a siguiente candidato. | TF marcado como "ambiguous in Phase I". Test 4 update modest. |
| **WEAKLY AGAINST** (1/5) | Documentar negative finding. Pivot a siguiente candidato (next prior-ranked novel). | TF removido de programa pruned. Test 4 update −0.2. |
| **NOT SUPPORTED** (0/5) | Documentar bystander finding. Pivot inmediato. | TF marcado como bystander. Substrate evidence: Test 4 calibration update −0.3 (calibrar el survey: TFs cluster-restricted no automáticamente reguladores). |

---

## 5. Substrate evidence implications por outcome

Para cada outcome, qué se aprende del SUSTRATO Witt (independiente de la biología):

| Outcome | Substrate finding | Test alimentado |
|---|---|---|
| STRONGLY SUPPORTED | "Survey computacional + cross-validation + perturbación literario predicen causalidad reliably" | Test 1 (orchestration), Test 3 (iteration), Test 4 (calibration) |
| PARTIALLY SUPPORTED | "El framework identifica TFs candidatos pero specificity ratio es moderate" | Test 1, Test 4 |
| MARGINAL | "El survey no es suficiente; necesitamos additional layers (ATAC-seq, spatial)" | Test 4 (calibration update needed) |
| WEAKLY/NOT SUPPORTED | "Cluster-restricted ≠ regulator. El framework necesita refinement de los criterios Tier" | Test 3 (iteration loop: el framework aprende), Test 4 |

**Crítico:** **cualquier outcome es valioso para el sustrato.** H0 soportada es tan informativo como H1 soportada — confirma que el survey no auto-genera evidencia confidently-wrong (Test 2 agency), y calibra los priors para el next candidate.

---

## 6. Recomendación operativa de la matriz

Dado los priors actualizados post-pleiotropy:

1. **mafba como target (prior 0.30):** un experimento positivo daría posterior 0.81. Un experimento negativo daría posterior 0.04. Información gain modesta (~0.4 de spread).

2. **hoxb8a como target (prior 0.65):** un experimento positivo daría posterior 0.95. Un experimento negativo daría posterior 0.16. Información gain alta (~0.6 de spread).

3. **sall1a como target (prior 0.55):** posterior range 0.92 a 0.10. Información gain ~0.55.

**El target óptimo para maximizar información gain es `hoxb8a`.** Este es el primer candidato cuya posterior puede legítimamente alcanzar > 0.90 con un experimento positivo, y simultáneamente caer fuerte (< 0.20) con uno negativo.

`mafba` con prior 0.30 está en una zona de "información ya obtenida" — el pleiotropy check ya reveló que es probable confundido, así que el experimento adicional aporta menos.

---

## 7. Trayectoria de calibración del sustrato post-experimento

Independiente del outcome, el sustrato registra:

```
{
  "experiment_id": "experiment_N_<gene>_<date>",
  "prior_confidence": <0.30 or 0.65 etc>,
  "outcome_n_supported": <0-5>,
  "posterior_confidence": <calculated>,
  "actual_phenotype_observed": "<descripción biológica>",
  "calibration_data_point": {
    "predicted_probability": <prior>,
    "observed_outcome": <0|1>,
    "log_likelihood": <-log P(observed|prior)>
  }
}
```

Estos data points alimentan calibration analytics del sustrato (Test 4 — isotonic regression of predicted vs observed). Es la primera evidencia "real-world" para el sistema.

---

## 8. Conclusión

La decision matrix muestra que la elección del target gene tiene mayor impacto que el outcome del experimento — porque el prior establece el techo y piso del posterior. **Maximizar información gain → elegir target con prior más cercano a 0.5** (donde un experimento es más informativo) **AND con specificity ratio adecuado** (donde el experimento puede ser interpretado limpiamente).

Per esta matriz, **hoxb8a es el candidato óptimo para experimento N**, no mafba.
