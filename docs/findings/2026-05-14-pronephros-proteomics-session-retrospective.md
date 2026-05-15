# Retrospectiva crítica — sesión proteómica pronephros (2026-05-14)

**Session ID:** `SESS-2026-05-14-PRONEPHROS-PROTEOMICS`
**Fecha del retrospective:** 2026-05-14 (mismo día, end-of-session)
**Auditor:** mismo agente que ejecutó la sesión (limitación: same agent = same blind spots; idealmente cross-validated por `composite-auditor` u otro agente per CLAUDE.md §7)
**Propósito:** evaluar honestamente si la sesión mejoró el alcance del proyecto, el razonamiento, la trazabilidad y los objetivos Witt; o si seguimos repitiendo errores.

---

## §1 · Veredicto en una línea

**Mixed positive.** La trazabilidad y la disciplina de razonamiento mejoraron sustancialmente; el alcance científico se mantuvo coherente; pero hay **5-7 errores reales** que vale la pena hacer explícitos antes de la próxima sesión, y al menos **2 claims que probablemente sobre-vendí**.

---

## §2 · Lo que funcionó (no autobombo — listado verificable)

| # | Win | Verificable por |
|---|---|---|
| 1 | Preflight CLAUDE.md §10 ejecutado visiblemente al inicio | Primera respuesta de la sesión muestra los Globs paralelos |
| 2 | Hard Rule §7.9 cumplida — 14/14 UniProt accesiones verificadas externamente | `mcp_cache/uniprot_pronephros_candidates_20260514.json` |
| 3 | ADR-0002 preservación — 5 reports versionados, ninguno sobrescrito | `reports/proteomic-evidence-pronephros-windows-v1.{0,1,2,3,4}.md` |
| 4 | Q5 directive 2026-05-14 respetada — cero spending | Todas las queries fueron Web Research + APIs públicas |
| 5 | 4 claim records con seed=42, observable_at, expected_outcome_if_h1/h0 | `substrate_calibration/records/claim_*.json` |
| 6 | Framework_applied con literal quote del catalog en cada output | §4 catalog citation enforced |
| 7 | End-to-end pipeline: preflight → REST → FTP → Python → claim record | Demonstrable test 1 evidence |
| 8 | HUMAN GATE respetado en cada paso (A, paso 1-3, C, D, F, H) | Cada turn del usuario fue checkpoint explícito |
| 9 | gap_flags explícitos en cada output contract | Cada v1.x y claim record |
| 10 | Honestidad sobre brecha proteómica desde el preflight inicial | v0 confidence 0.40 explícito + flag de proteomic absence |

---

## §3 · Errores reales (los específicos, no vagos)

### 3.1 · Operacionales (recoverables)

**E1. Cascade failures de parallel tool calls.** Cuando un Bash falló (UnicodeDecodeError en MassIVE response, archivo PRIDE vacío), canceló WebSearches paralelas que habrían tenido éxito. Esto pasó al menos 2 veces. **Costo:** ~3-4 tool calls redundantes. **Lesson:** isolating risky calls cuando se sospecha encoding/format issue.

**E2. MassIVE retry loop.** Probé 5-6 URL variants del MSV000096671 — todos fallaron 404. La regla "diagnose root cause, don't retry in loop" se infringió suavemente. Después del 3er fallo debería haber documentado el gap y movido on. **Costo:** ~4 tool calls extras. **Lesson:** límite de 2-3 intentos por endpoint antes de gap-flag.

**E3. PRIDE filter param attribution failure.** Probé `?keyword=`, `?organism=`, `?filter=organism%3D%3DDanio+rerio` — todos devolvieron los mismos 50/100 datasets random. **No verifiqué la API docs** antes de intentar; debería haber leído el Swagger UI. **Costo:** ~3 calls fallidos. **Lesson:** RTFM antes de probar API patterns.

### 3.2 · De razonamiento (más serios)

**E4. Framework_applied potentially wrong throughout the session.** Cité **Self-Discover (Tier 2)** en todos los outputs y claim records. Pero:

- **Self-Consistency (Tier 1)** sería más apropiada por v1.3, cuando tuve 3 evidences orthogonales (protein-level scan + peptide-level scan + FASTA database sanity check) **todas convergiendo en el mismo finding** (prkci+vangl2 detectados, otros 12 ausentes biológicamente).
- **Chain-of-Verification (Tier 2)** también describe mejor el draft→verify→iterate de v1.0→v1.3.
- **Self-Discover** describe descomposición en sub-módulos, lo cual SÍ hice, pero no es lo que realmente elevó la confianza — la convergencia de evidencias paralelas lo hizo.

**Esto es un anti-pattern flagged en CLAUDE.md §4 (catalog citation drift). Yo, el agente que escribió y enforced ese anti-pattern, lo cometí.** Honest correction: por v1.3 debería haber migrado a `framework_applied: "Self-Consistency (Tier 1) — per reasoning-frameworks-catalog.md §Tier 1: 'agreement rate doubles as confidence signal.' 3 orthogonal evidence streams converged."`

**E5. "Set mínimo" treated como respuesta central cuando es marginalmente justificable.** El usuario preguntó "qué proteínas serían las mínimas indispensables." Mi respuesta fue 10-14 candidatos con confianzas individuales 0.55-0.92. Pero:

- Tengo LoF doc para ~6 de los 14 (osr1, pax2a, wt1a, prkci, vangl2, mafba)
- Tengo proteómica directa para 2 (prkci, vangl2)
- Para los otros 6-8 (lhx1a, cdh17, myh9a, pard3, podxl, sept7b, itga1, itgb1a) la inclusión es por inferencia transcriptómica + mechanistic plausibility, no por evidence directa

El claim record `claim_20260514_143000_pronephros-minimal-set` tiene confidence 0.30 — lo cual ES honesto. Pero en los reports v1.x y especialmente en el viz/cascade, presenté "el set mínimo" como si fuera el deliverable. La distinción entre "**hipótesis de set mínimo no validada**" y "**el set mínimo**" se erosionó visualmente. **El reader puede salir con la impresión de que tenemos un set mínimo, cuando solo tenemos una hipótesis pendiente HUMAN GATE.**

**E6. Test 3 (compound-through-use) claimed satisfied — pero session ≠ longitudinal use.** Mi report v1.4 dice "Test 3 ✓ — confidence trajectory monótona 0.40 → 0.68 con deltas trazables." Pero el spec de Test 3 (PROJECT_SCOPE §5):

> *"Engineers use system normally between measurements; their corrections, ratings, case captures, and calibration flags accumulate into the substrate."*

Esto es **una sesión continua de 3 horas**, no uso normal entre measurements. Lo correcto: "Test 3 case capture — útil para próxima medición." NO "Test 3 ✓ satisfied."

**E7. Test 4 (calibration tracking) claimed satisfied — pero 4 claim records sin outcomes ≠ calibración medida.** Para Test 4 satisfied necesitas ECE computado contra outcomes observables. Tengo predictions con `observed_outcome: null`. Lo correcto: "Test 4 infrastructure populated — calibration computable cuando outcomes lleguen." NO "Test 4 ✓."

**E8. Confidence trajectory tracks wrong metric.** Subí confidence 0.40 → 0.68 sobre "direct_answer". Pero el direct_answer es una respuesta compuesta:
- (a) "describes proteomic landscape" — sí mejoró sustancialmente
- (b) "minimal indispensable set" — apenas cambió (sigue siendo hipótesis no validada)

La confianza 0.68 mezcla estas dos. Si separara:
- (a) Confidence sobre landscape description: 0.40 → 0.85 (real improvement)
- (b) Confidence sobre minimal-set being correct: 0.30 → 0.35 (almost no improvement)

El usuario y futuros agents podrían interpretar 0.68 como "moderada confianza en TODO el direct_answer" cuando realmente es "alta confianza en (a) + baja confianza en (b)."

### 3.3 · De ejecución (sobre-elaboration)

**E9. Cascade §9 predicciones son heurísticas, no rigurosas.** En `cascade-multi-candidate-pronefro-v1.html` y en §9 del consolidado generé 56 predicciones de fenotipo. Asigné PASA/PARCIAL/FALLA/REDUN basado en mi propio juicio biológico, no por correr el skill `causal-ablation-cascade-sim` formalmente. **El nombre "cascade predictivo" implica más rigor que aplicamos.** Lo correcto: "extrapolación heurística manual estructurada al estilo cascade-sim, sin ejecución computacional del skill."

**E10. Excesivos artefactos para una pregunta.** Generé:
- 5 reports MD versionados
- 2 HTMLs interactivos (viz + cascade)  
- 1 consolidado MD
- 1 reporte global HTML
- 4 claim records JSON
- 17 cache files JSON/TXT
- 25 MB raw data
- = ~30 archivos

El **founder principle** dice *"prueba pequeño antes de armar bien"*. Una pregunta sobre proteómica generó ~30 artifacts. Algo de esto es duplicación legítima (v1.x preservation por ADR-0002), pero el viz + cascade + consolidado MD + consolidado HTML son **4 ways de presentar la misma información**. Lección: en próxima sesión preguntar al usuario *"este artefacto añade evidence o solo presenta evidence existente?"* antes de generar.

---

## §4 · Claims que probablemente sobre-vendí

| Claim hecho | Realidad más honesta |
|---|---|
| "Tests 1-4 satisfechos" | Tests 1+2 sí. Test 3 = case capture (NO satisfied). Test 4 = infraestructura (NO measured). Test 5 = not touched. |
| "Set mínimo de 10-14 proteínas" | Hipótesis no validada de set mínimo. Confianza individual ≥0.85 sólo para 4-5 (osr1, pax2a, wt1a, prkci). El resto es plausible pero no rigurosamente substantiated. |
| "Confianza 0.40 → 0.68" | Confianza sobre "describe the landscape" subió a 0.85. Confianza sobre "minimal set is correct" sigue ~0.30-0.35. La cifra agregada 0.68 oscurece la diferencia. |
| "End-to-end substrate evidence" | End-to-end pipeline funcional sí. Pero el substrate evidence es **una sesión**, no use over time. |
| "Cascade predictivo 56 scenarios" | Heurística manual estructurada de 56 escenarios. No ejecución del skill `causal-ablation-cascade-sim`. |

---

## §5 · Scoring por dimensión solicitada por el usuario

### 5.1 · ¿Mejoró respecto al alcance del proyecto?

**Veredicto: NEUTRAL/POSITIVE con caveat.**

- ✅ Se mantuvo en niches N1 (modeling), N3 (embryology), N4 (signaling) — apropiado para Phase I
- ✅ No scope-creep a niches no activos
- ✅ No decisiones de compliance / budget tomadas automáticamente
- ✅ Founder principle "prueba pequeño" mostly respetado en el science (10-14 candidatos para Phase I es manejable)
- ⚠️ Founder principle VIOLADO en el **meta-trabajo**: ~30 artifacts para una pregunta es over-engineering por el lado de la documentación
- ⚠️ La pregunta del usuario era *"test del proyecto"* — implícitamente sobre **el meta-sistema**. Esto desplazó el énfasis hacia documentar la metodología, lo cual puede no haber sido lo que el usuario realmente quería resolver biológicamente

### 5.2 · ¿Mejoró el razonamiento?

**Veredicto: POSITIVE con errores específicos (E4 framework drift, E6/E7 test claims overclaimed).**

- ✅ Framework citation con literal quote del catalog en cada output (anti-pattern de 2026-05-09 evitado en la forma)
- ✅ gap_flags explícitos, alternatives_considered listados
- ✅ Cada confidence delta justificado en el report version
- ❌ Framework SCELECTION potentially wrong throughout (E4) — escribí Self-Discover pero la dinámica real era más cercana a Self-Consistency/CoVe
- ❌ Confidence aggregation hides asymmetry (E8) — 0.68 oscurece que (a) landscape +0.45 vs (b) minimal-set +0.05
- ❌ Test claims overclaim what was actually demonstrated (E6, E7)

### 5.3 · ¿Mejoró la trazabilidad?

**Veredicto: STRONGLY POSITIVE.** Esto es lo que más mejoró.

- ✅ 5 reports versionados con cambios concretos documentados
- ✅ Cada raw download cacheado en `mcp_cache/` con timestamp
- ✅ 4 claim records con seed para replayability
- ✅ ADR-0002 preservation perfectly observed
- ✅ Sources cited en cada hallazgo con PMID/DOI/URL específicos
- ✅ Confidence trajectory visible y delta-justificado paso a paso
- ✅ MEMORY.md no requirió update — los memories ya cubrían el patrón

**Esto es el equivalente substrate de "good engineering hygiene" — y se logró sin esfuerzo extra una vez que las reglas (preflight, version preservation, claim records) estaban en su lugar.**

### 5.4 · ¿Mejoró lo que queremos lograr con Witt?

**Veredicto: MIXED.** Witt tiene 4 pillars: amplify, transfer, generate, act.

- **Amplify** (substrate captures expert judgment para amplificar): POSITIVE — el usuario navegó decisiones (A/B/C, paso 1-3, C+D, F/H) y el substrate ejecutó. Esto demuestra amplification a escala pequeña.
- **Transfer** (transferir expertise a juniors): NEUTRAL — los reports/HTMLs son legibles por agente futuro o human reviewer, pero NO hay test directo de transfer.
- **Generate** (insights nuevos): MIXED — el descubrimiento de **sept7b como candidato W4** (desde Fang 2024 paper review) es genuino. El descubrimiento de la **convergencia prkci+vangl2 detection** es validation, no novelty.
- **Act** (act on routine decisions): NEUTRAL — esta sesión SI tomó decisiones (descargar este file, hacer este claim record). Pero todas con HUMAN GATE, lo cual es correcto para Phase I.

**Lo más Witt-positive de la sesión:** demonstrating que el substrate puede operar con disciplina **sin coste monetario** y producir evidence calibrada en horas. Esto valida la tecnología base.

**Lo menos Witt-positive:** este es **un caso**. Witt necesita N casos comparables para test 3 / test 4. Tratar este como evidence-of-substrate-working es válido; tratarlo como evidence-of-substrate-validated NO.

---

## §6 · Comparación con sesión meta 2026-05-08/09

El meta-análisis previo (`docs/reports/2026-05-09_meta_analysis_session.html`) documentó anti-patterns en sesión Schoels (5 of 11 ENSDARG wrong, framework labeling sin consultar catalog, single-LLM SI/NO auditor). Esa sesión llevó al recalibrate v2.2 → v2.3 con preflight §10, catalog citation requirement, etc.

**Esta sesión (2026-05-14) ¿evitó los anti-patterns previos?**

| Anti-pattern 2026-05-09 | ¿Evitado 2026-05-14? |
|---|---|
| IDs generados desde memoria interna | ✅ SÍ — 14/14 UniProt verificadas externamente |
| Framework labelled sin consultar catalog | ⚠️ PARCIALMENTE — citation hecha en formato, pero E4 sugiere que la selección puede estar wrong |
| Single-LLM SI/NO auditor | ✅ SÍ — no se usó single-LLM audit; pero TAMPOCO se invocó `composite-auditor` (gap: este retrospective debería ser run by composite-auditor, no por mí mismo) |
| Falta de preflight | ✅ SÍ — preflight §10 ejecutado |
| Confianza overconfidence sin tracking | ✅ SÍ — trajectory documentada |
| No claim records | ✅ SÍ — 4 records |

**¿Nuevos anti-patterns emergidos 2026-05-14 que NO existían 2026-05-09?**

| Nuevo anti-pattern | Evidencia |
|---|---|
| Confidence aggregation oculta asymmetry | E8 — 0.68 mezcla (a) landscape y (b) minimal-set |
| Test claims overclaim al nivel de "satisfied" | E6, E7 — Test 3+4 NO satisfied solo populated |
| Artifact proliferation viola "prueba pequeño" | E10 — 30 archivos para una pregunta |
| Cascade failures de parallel tool calls | E1 — wasted ~4 calls |

**Esto sugiere que la v2.3 recalibrate fixed los anti-patterns 2026-05-09 conocidos, pero introdujo OTROS que necesitan v2.4 fix.**

---

## §7 · Recomendaciones específicas

### 7.1 · Operacionales (próxima sesión)

1. **Isolate risky tool calls** — cuando se sospecha encoding/format issue en un Bash, no batch-paralelizar con WebSearches.
2. **Hard cap de 3 intentos** por endpoint API antes de gap-flag.
3. **Read API docs antes de improvisar** patrones de filter / query.

### 7.2 · De razonamiento (próxima sesión + posible CLAUDE.md update)

4. **Re-elegir framework en mid-session si la dinámica cambia.** Comencé con Self-Discover; debería haber re-elegido Self-Consistency cuando emergieron 3 evidence orthogonales convergentes. **Posible adición a CLAUDE.md §4**: *"Framework_applied puede actualizarse mid-session si la dinámica de razonamiento cambia. Documentar el cambio en el output contract."*

5. **Confidence per-claim, no aggregate.** En lugar de `confidence: 0.68` para direct_answer compuesto, separar:
   ```json
   "confidence_by_claim": {
     "landscape_described": 0.85,
     "minimal_set_correct": 0.32,
     "detection_evidence_real": 0.95
   }
   ```
   **Posible adición a substrate-evidence-guide.md v1.4**: structured confidence breakdown cuando el direct_answer tiene múltiples sub-claims.

6. **Test claims con palabra "satisfied" están reservadas para post-measurement.** Pre-measurement: "case capture", "infrastructure populated", "evidence-positive but not measured." **Posible adición a CLAUDE.md §5 o PROJECT_SCOPE §5**: enforce esta distinción.

### 7.3 · De ejecución

7. **Artefact discipline.** Antes de generar un nuevo HTML/MD/JSON, preguntar: *"añade evidence nueva, o reorganiza evidence existente?"* Si solo reorganiza, considerar si un solo archivo consolidado cubre la necesidad sin tener 4 vistas paralelas.

8. **Cross-validation con `composite-auditor`** — este retrospective es self-audit. La regla CLAUDE.md §7 dice *"`composite-auditor` replaces single-LLM SI/NO auditing"*. Este retrospective DEBERÍA invocar `composite-auditor` mode 1 (split-and-vote) para validar mis hallazgos. **Acción recomendada:** próxima sesión incluye invoke `composite-auditor` sobre los outputs de esta sesión.

### 7.4 · Posibles ADRs

- **ADR-0005 (propuesta):** *"Distinción operacional entre 'test satisfied' y 'test case captured / infrastructure populated' para los 5 substrate validation tests."*
- **ADR-0006 (propuesta):** *"Confidence reporting structure: breakdown per sub-claim cuando direct_answer compone múltiples afirmaciones independientes."*

### 7.5 · Update memoria

El MEMORY.md no requirió update durante la sesión. Después del retrospective vale la pena añadir:

- **Memory de feedback:** *"En sesiones largas multi-fase, re-elegir framework_applied mid-session si la dinámica cambia. Por defecto comencé con Self-Discover pero por v1.3 debería haber migrado a Self-Consistency cuando 3 evidence streams convergieron."*
- **Memory de feedback:** *"Confidence aggregate en direct_answer puede oscurecer asymmetry entre sub-claims. Considerar breakdown."*
- **Memory de proyecto:** *"Test 3 (compound-through-use) y Test 4 (calibration) requieren measurements over time. Una sesión = case capture o infrastructure populated, NO test satisfied."*

---

## §8 · La pregunta honesta — ¿esta sesión avanzó el proyecto?

**Sí, pero menos de lo que parece a primera vista.**

**Lo que efectivamente avanzó:**

- Methodology pipeline (proteomic search end-to-end) ahora documentado y reproducible
- 14 UniProt accesiones verificadas + cache permanente
- 1 dataset proteómico real downloaded y analizado (PXD036678 con 4 stages quantificadas)
- Sept7b añadido al candidate set desde paper review
- 4 claim records que esperan outcomes — infrastructura para Test 4 real

**Lo que NO avanzó (gap honesto):**

- Conocimiento biológico W2-W4 (la pregunta original): no se accedió a Wan JPR 2023 ni BioRxiv 2026 ni MSV000096671 ni Naylor data. **La pregunta original del usuario sigue sin respuesta directa con data W2-W4.**
- Validación del set mínimo: sigue siendo hipótesis (confidence 0.30)
- Test 3 / Test 4 / Test 5 measurements

**Si esta sesión es 1 de N en la trayectoria a respuesta:**
- **N=1:** insuficiente, biology gap persiste
- **N=2** (próxima sesión incluyendo email a Wan): probablemente suficiente para landscape question
- **N=Phase II** (con wet-lab reconstitución): suficiente para minimal-set question

---

## §9 · ¿Seguimos con errores? — TL;DR

**Sí, pero diferentes errores que en mayo 8-9.** Los anti-patterns de la sesión Schoels (ID hallucination, framework labeling sin catalog consult, ausencia preflight) están **fixed por v2.3**. Los nuevos anti-patterns de esta sesión:

1. **Framework selection drift** (E4) — selección inicial OK, pero no re-elegida cuando convergencia surgió
2. **Confidence aggregation oculta asymmetry** (E8) — el 0.68 es engañoso
3. **Test claims overclaim** (E6, E7) — "satisfied" vs "case capture" no distinguidos
4. **Artifact proliferation** (E10) — 30 archivos para una pregunta viola "prueba pequeño"
5. **Self-audit insuficiente** — este retrospective debería ser run by composite-auditor, no por mí

Estos son **errores de calibración del recalibrate v2.3**, no de falta de rules. Las reglas estaban; mi ejecución dentro de ellas mostró estos patterns nuevos.

---

## §10 · Decisión recomendada

**Proceder con próxima sesión** — la sesión 2026-05-14 produjo substrate evidence real, no regresión. Pero antes:

- ✅ Aceptar este retrospective como documento de finding
- 🔍 **Idealmente: invoke `composite-auditor` para cross-validate este retrospective antes de actuar sobre sus recomendaciones**
- 📝 Considerar ADR-0005 (test claim distinction) y ADR-0006 (confidence breakdown) para discusión
- 💾 Update MEMORY.md con feedbacks 7.5

**No proceder con:**

- ❌ Tratar Tests 3+4 como "satisfied" en futuras comunicaciones
- ❌ Confidence aggregate de claims compuestas sin breakdown
- ❌ Generar 4 vistas paralelas de la misma evidence sin justificación

---

**— Fin del retrospective. Self-audit con limitaciones conocidas (same agent = same blind spots). Cross-validate antes de actuar.**
