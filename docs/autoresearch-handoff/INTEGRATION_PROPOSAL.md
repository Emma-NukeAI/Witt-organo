# INTEGRATION_PROPOSAL.md — Subsistema de generación de hipótesis para witt-organogenesis, gobernado por la disciplina de STRATEGY_FINAL

> **Status:** propuesta de integración, no plan de implementación firmado.
> **Compañero:** lee este documento DESPUÉS de `STRATEGY_FINAL.md`.
> **Branch sugerido para PRs:** `feature/hypothesis-generation-subsystem`.
> **Autor:** equipo autoresearch (handoff packet, mayo 2026).
> **READ ME FIRST:** este documento está listo para **revisión arquitectónica**, NO
> como plan de implementación firmado. Antes de abrir las PRs de §7, lee **Anexo C**
> al final del doc — 18 gaps abiertos detectados por un crítico adversarial, incluyendo
> uno notable (la guía fuente tiene 11 campos, no 7 — §3.2/§3.3 necesitan ese remapeo).
>
> **Audiencia:** Emmanuel, Martín Gleizer, futuro cognitive scientist hire, agent designer aplicando `organogenesis-agent-architect` Mode A/B.

---

## 0. TL;DR — una pantalla

**Qué propone:** añadir un único agente nuevo, `hypothesis-generator`, al catálogo Fase I de witt-organogenesis, instrumentado con la misma disciplina que `STRATEGY_FINAL` extrajo del run de `autoresearch` (sonda de ruido, frontier efectivo, EPS empírico, calibración reactiva, PIVOT_AFTER, governance-proposals). El agente produce **candidatos estructurados de hipótesis** sobre el dominio de organogénesis renal (default Phase I: pronephros zebrafish), no validez científica.

**Cómo encaja:**
- **STRATEGY_FINAL** = capa de disciplina (cómo medir sin auto-engaño).
- **Este doc** = capa de arquitectura (qué agente lo encarna y cómo se enchufa al catálogo existente).

**Lo que cambia de witt v2.2:**
- 1 agente nuevo (`hypothesis-generator`), 1 slot cedido (candidatos: `accumulator` se extiende en vez de duplicarse; o se suspende `investor-relations-drafter`/`ip-patent-watcher`). Cap = 16 preservado.
- Extensiones (no reescrituras) a 6 agentes existentes: `reasoning-exposer`, `calibration-tracker`, `evaluation-runner`, `case-capture-elicitor`, `composite-auditor`, `domain-knowledge-curator`.
- Una regla nueva en `program-manager.md`: PIVOT_AFTER con dos triggers de plateau.
- Una sección nueva en `SKILL.md`: 4 plantillas de `governance-proposal` pre-aprobadas.

**Método elegido (Phase I):** **Hybrid, default Method 2** per v2.2. Method 1 (con `composite-auditor`) se activa SOLO cuando una hipótesis escala a wet-lab; ahí el **human-gate es obligatorio 100%**.

**Headline ROI:**
- Tests 3 (iteration loop) y 4 (calibration) reciben evidencia substrato **directa y fuerte**, si y solo si cada hipótesis se trata como `case-capture` obligatorio.
- Test 1 (orchestration) y Test 2 (agency) reciben evidencia **indirecta**.
- **Test 5 (cross-field) NO se demuestra acá** — sigue exploratorio per v1.2; cualquier corrida cross-corpus lleva flag arquitectónico `EXPLORATORY-NOT-TEST-5`.

**Costo Phase I estimado:** cabe en $297K / 8 meses / 4 personas **si y solo si** se respeta "start simple RAG, measure bottleneck" (Magraner Aug 2025) y no se infla N de Self-Consistency ni eval set sin evidencia de bottleneck. Desglose en §4.

---

## 1. Por qué este doc va junto a STRATEGY_FINAL

`STRATEGY_FINAL.md` es el extracto de disciplina del run de `autoresearch`. Sus 6 prescripciones (§5.1–§5.6) son protocolos contra **auto-engaño en un loop iterativo con métrica ruidosa, drift de entorno, y un humano caro al final**. Esa descripción es exactamente la del problema de generación de hipótesis biomédicas:

| Característica de `autoresearch` | Característica del hypothesis-generation loop |
|---|---|
| `val_bpb` con ruido estocástico (temperature, seed, hardware) | Output de hipótesis con ruido estocástico (temperature, seed, retrieval set) |
| Drift de entorno: laptop throttling, VRAM, OS | Drift de entorno: model-id deprecation, corpus PubMed crece, embedding model versioning |
| Humano caro al final (autor revisa `program.md`) | Humano caro al final (panel de expertos rate-ea rubric) |
| Iteración por edición de un único archivo (`program.md`) | Iteración por edición de prompt, retriever, ranker, corpus |
| Necesidad de meta-loop (agente que propone su propio fix) | Misma necesidad (agente detecta drift, propone fix) |

Sin esta capa de disciplina, el subsistema reportará **variabilidad estocástica como "novedad"** y **quemará revisores humanos en falsos positivos** — el pecado original de `autoresearch v1`.

**Modelo mental del lector:**
- STRATEGY_FINAL responde "¿cómo no engañarse al medir?"
- Este doc responde "¿qué agente encarna eso, dónde se enchufa, y qué cambia en witt v2.2?"

**Lo que NO hace este doc:**
- No reescribe witt v2.2. Lo extiende.
- No introduce un Method nuevo. Reusa Method 1/2 con disciplina añadida.
- No sustituye validación experimental. Un LLM produce **plausibles**, no **válidas**; la validez sigue siendo wet-lab + experto.

---

## 2. La forma de la integración

### 2.1 Diagrama de flujo (ASCII)

```
SEED QUERY (del investigador humano o de literature-monitor)
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│  domain-knowledge-curator (EXTENDIDO)                             │
│  · ownership del pipeline RAG (Phase I = bge-large solo,          │
│    parsing crudo, metadata mínima)                                │
│  · vector + keyword hybrid index                                  │
│  · pipeline_config_hash → framework_applied                       │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│  hypothesis-generator (AGENTE NUEVO)                              │
│  · contrato 7 campos del research-hypothesis-generation-guide     │
│    mapeado al schema Witt 6 campos (ver §3.2)                     │
│  · pre_registered_confidence obligatoria                          │
│  · flag requires_ethics_review boolean                            │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│  reasoning-exposer (EXTENDIDO)                                    │
│  · valida poblamiento de los 6 campos                             │
│  · alternatives_considered con sub-schema obligatorio:            │
│    {considered:[...], contradictory_evidence_cited:[...]}         │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼
   ┌────┴──────────────────────────────────┐
   │   PRE-DISPLAY HOOK (deterministic)    │
   │   regulatory-ethics deny-list:        │
   │   human embryo / germline humano /    │
   │   gain-of-function pathogens / ...    │
   │   BLOQUEA antes de que humano lea     │
   └────┬──────────────────────────────────┘
        │ (pasa)
        ▼
┌───────────────────────────────────────────────────────────────────┐
│  case-capture-elicitor (EXTENDIDO)                                │
│  · snapshot INMUTABLE de TODA hipótesis al momento de generación  │
│  · schema: {hypothesis_id, generated_at, agent_version,           │
│    pipeline_config_hash, pre_registered_confidence, rater_id,     │
│    expert_score (nullable T+48h), escalated_to_wetlab (bool),     │
│    wetlab_outcome (nullable T+meses)}                             │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼
   ┌────┴──────────────────────────────┐
   │       METHOD 2  (default Phase I) │
   │                                   │
   │  ┌─────────────────────────────┐  │
   │  │ accumulator                 │  │
   │  │ · lee case-captures +       │  │
   │  │   outcomes                  │  │
   │  │ · mantiene curva            │  │
   │  │   compound-through-use      │  │
   │  │   (Test 3)                  │  │
   │  └─────────────────────────────┘  │
   │                                   │
   │     HUMAN  (1 de 4 del equipo,    │
   │      rotativo, rater_id reg.)     │
   │                                   │
   │     ──> expert_score T+48h ───┐   │
   └───────────────────────────────┼───┘
        │                          │
        │  (hipótesis escalada     │
        │   a wet-lab)             │
        ▼                          │
   ┌────┴──────────────────────────┴───┐
   │       METHOD 1 (escalamiento)     │
   │                                   │
   │  composite-auditor (3 modos):     │
   │   (a) Self-Consistency N=3-5,     │
   │       FAMILIAS DISTINTAS de       │
   │       modelos (Claude + Gemini    │
   │       + GPT cuando hay budget)    │
   │   (b) Logic-LM:                   │
   │       citation-coverage ✓         │
   │       contradiction-coverage ≥1   │
   │       schema-completeness ✓       │
   │   (c) HUMAN GATE OBLIGATORIO      │
   │       100% — el triage prioriza   │
   │       la cola, NO la salta        │
   │                                   │
   │  regulatory-ethics-advisor        │
   │   (post-display LLM-classifier    │
   │    para edge cases)               │
   └───────────────────────────────────┘
        │
        ▼
   ┌────┴──────────────────────────────┐
   │  calibration-tracker (EXTENDIDO)  │
   │  · stream rápido: expert_score    │
   │    T+48h, rolling K=6 PER-OUTPUT  │
   │  · stream lento: wet-lab T+meses, │
   │    K=3 anual                      │
   │  · isotonic regression POR        │
   │    sub-dominio desde día 1        │
   │    (Vega et al. Feb 2025)         │
   │  · auto-cap rule: hit-rate <60%   │
   │    → confidence clamp ≤0.6        │
   └───────────────────────────────────┘
        │
        ▼
   ┌────┴──────────────────────────────┐
   │  program-manager (EXTENDIDO)      │
   │  · PIVOT_AFTER triggers (§5.5)    │
   │  · governance-proposal queue      │
   │  · §15 v3 rule: human aprueba     │
   │    cualquier switch de Method     │
   └───────────────────────────────────┘
```

### 2.2 Resumen de la integración

| Capa | Quién | Función |
|---|---|---|
| Substrato del corpus | `domain-knowledge-curator` (extendido) | Owner versionado del pipeline RAG; empieza minimal |
| Generación | `hypothesis-generator` (nuevo) | Produce candidatos 7-campos con pre-registered confidence |
| Validación de schema | `reasoning-exposer` (extendido) | Verifica los 6 campos Witt + sub-schema obligatorio |
| Guard ético pre-display | hook + `regulatory-ethics-advisor` | Capa 1 deny-list determinística; Capa 2 LLM-classifier |
| Linaje | `case-capture-elicitor` (extendido) | Snapshot inmutable de TODA hipótesis |
| Curva Test 3 | `accumulator` (extendido) | Mantiene compound-through-use sobre case-captures |
| Filtro (solo escalamiento wet-lab) | `composite-auditor` (extendido) | Self-Consistency multi-familia + Logic-LM + human-gate |
| Calibración | `calibration-tracker` (extendido) | Dos streams (rápido K=6 per-output / lento K=3 anual) |
| Meta-loop | `program-manager` (extendido) + `SKILL.md` | PIVOT_AFTER + 4 plantillas de governance-proposal |
| Ground truth de rubric | humano del equipo o LLM de familia distinta | Generator ≠ rater no negociable |

### 2.3 Dónde está el human-gate

| Punto del flujo | Tipo de gate | Skippable? |
|---|---|---|
| Antes de display (regulatory deny-list) | hook automático determinístico | No (bloquea matches inequívocos) |
| Method 2 — review de candidato | humano del equipo | No, pero rápido (~minutos) |
| Method 2 → Method 1 (escalamiento wet-lab) | human-gate via `composite-auditor` | **OBLIGATORIO 100%** |
| Switch de Method 1 → Method 2 (PIVOT_AFTER) | human-gate via `program-manager` (§15 v3) | No, dispara governance-proposal pero el switch lo aprueba el humano |

---

## 3. Subsistema propuesto: agentes nuevos / extensiones

### 3.1 Decisión de Method y contabilidad del cap ~16

**Method elegido: Hybrid, default Method 2 per v2.2 Phase I.**

Justificación:
- v2.2 declara Method 2 como default exploratorio.
- Method 1 requiere `composite-auditor` con thresholds calibrados; en bootstrap **no existe** eval-set congelado con ratings de panel previos contra los cuales calibrar.
- PIVOT_AFTER (§5.5) puede pivotar Method 1 → Method 2 vía `governance-proposal`, **no auto-aplicado**. Regla §15 del `program.md` v3 aplica idéntica.

**Contabilidad del cap:**

| Opción | Movimiento | Total |
|---|---|---|
| **A (recomendada)** | Extender `accumulator` con responsabilidad del contrato de 7 campos para hipótesis (no fork). Añadir `hypothesis-generator` como agente separado. Suspender `ip-patent-watcher` en Phase I (no crítico a defensibilidad técnica). | 16 |
| B | Mantener `accumulator` separado y `hypothesis-generator` separado. Suspender `investor-relations-drafter` Y `ip-patent-watcher`. | 16 |
| C | Fusionar `hypothesis-generator` dentro de `accumulator`. | 16 sin nuevos slots |

**Decisión final del slot la firma `program-manager` en un ADR (ver §7).** Recomendación de este doc: opción A.

### 3.2 `hypothesis-generator` — role spec en formato Phase-4 de `organogenesis-agent-architect`

**Nombre:** `hypothesis-generator`
**Status:** NUEVO en Phase I
**Method en el que opera:** Method 2 por default; sus outputs alimentan Method 1 solo cuando escalan a wet-lab.
**Cap budget:** 1 slot (ver §3.1 opción A).

**Responsabilidades:**
1. Tomar un seed query (del investigador, de `literature-monitor`, o de un sub-corpus designado por `domain-knowledge-curator`).
2. Consultar el índice mantenido por `domain-knowledge-curator`.
3. Producir N hipótesis estructuradas (default N=1 en Method 2; N=3-5 multi-familia en Method 1).
4. Poblar el contrato de 7 campos del `research-hypothesis-generation-guide`, mapeado al contrato Witt de 6 campos (ver §3.3).
5. Auto-emitir `governance-proposal` cuando dispare uno de los 4 triggers de §5.6.
6. Producir flag `requires_ethics_review` (boolean) detectado por keywords (human-translation, disease-model, drug-target con indicación clínica, propuestas wet-lab).

**Contrato estructurado (output):**
- `direct_answer` ← **Hypothesis** + **Testable Prediction** (sub-campos)
- `confidence` ← **Confidence** (numérica, `pre_registered_confidence`)
- `evidence_cited` ← **Rationale** + **Citations** (con DOI verificable)
- `alternatives_considered` ← sub-schema obligatorio `{considered: [...], contradictory_evidence_cited: [{paper_id, finding}, ...]}`; `contradictory_evidence_cited` **no-vacío** requerido (no opcional)
- `gap_flags` ← **Possible Confounders** + **Required Controls**
- `framework_applied` ← **self-report** del stack: `{llm_model_id, embedding_model_version, corpus_snapshot_hash, prompt_hash, reranker_hash, retrieval_k, rerank_top_n}` — NO es introspección, es hash de pipeline (Anthropic Apr 2025)
- `proposed_experiment` ← sub-campo de `direct_answer`, no séptimo campo universal — esto preserva retro-compatibilidad real con agentes no-hypothesis

**Justificación de Method:**
- Method 2 (default): el `hypothesis-generator` produce candidatos, `accumulator` los agrega, humano del equipo decide cuáles avanzan. Coherente con v2.2 default Phase I.
- Method 1 (escalamiento): solo cuando una hipótesis se encamina a wet-lab. `composite-auditor` entra con sus 3 modos, human-gate obligatorio 100%.

**Anti-patterns evitados:**
- No es un swarm de N=5 generadores corriendo permanentemente (eso sería Method 1 por default — violación v2.2).
- No es un single-LLM SI/NO auditor (eso violaría composite-auditor v2.2).
- No es introspección (`framework_applied` es self-report).

**Dependencias upstream:**
- `domain-knowledge-curator` (índice RAG).
- `literature-monitor` (puede inyectar seed queries por gaps detectados).

**Dependencias downstream:**
- `reasoning-exposer` (valida schema).
- hook `regulatory-ethics` (pre-display).
- `case-capture-elicitor` (snapshot inmutable).
- `accumulator` (agrega para Test 3).

### 3.3 Mapeo del contrato 7 → 6 (decisión final)

**Decisión:** mantener 6 campos universales en el contrato Witt v2.2; NO bifurcar a 7. El sub-schema de `alternatives_considered` se redefine para tareas hypothesis con `contradictory_evidence_cited` obligatorio no-vacío. `proposed_experiment` vive como sub-campo de `direct_answer` o como output downstream de `experiment-designer`.

Razón: bifurcar el schema universal (6 para no-hypothesis, 7 para hypothesis) NO es retro-compatible — es un fork. La opción minimal-invasive preserva un único contrato.

### 3.4 Extensiones a agentes existentes (resumen, detalle en §7)

| Agente | Cambio core |
|---|---|
| `reasoning-exposer` | Valida sub-schema obligatorio en `alternatives_considered` para outputs de hypothesis |
| `calibration-tracker` | Dos streams (rápido K=6 per-output / lento K=3 anual); isotonic por sub-dominio desde día 1 |
| `evaluation-runner` | 3 ejes de noise probe específicos a hypothesis: retrieval-Jaccard, citation-overlap, hypothesis-cosine. EPS=2σ por eje |
| `case-capture-elicitor` | Schema explícito; snapshot inmutable al momento de generación |
| `composite-auditor` | Self-Consistency multi-familia, no multi-seed; thresholds = percentil empírico (p25), no arbitrarios |
| `domain-knowledge-curator` | Owner del pipeline RAG (start simple); upgrades solo con bottleneck evidence |
| `regulatory-ethics-advisor` | Capa 2 LLM-classifier post-display; Capa 1 es hook determinístico pre-display |
| `program-manager` | PIVOT_AFTER triggers; cola de governance-proposals |

---

## 4. Stack técnico para Phase I

### 4.1 Componentes y nombres

| Componente | Phase I (start simple) | Upgrade SOLO si bottleneck evidence |
|---|---|---|
| LLM de síntesis | Claude Opus 4.7 (`claude-opus-4-7-20260120`, model-id pineado con fecha) | Multi-familia (Claude + Gemini + GPT) en Method 1 |
| Embedding model | `bge-large-en-v1.5` | SPECTER2 si recall biomédico es bottleneck |
| Retriever | dense-only (bge) | Hybrid BM25 + dense |
| Parser de PDFs | parsing crudo (PyMuPDF / pdfplumber) | GROBID por sección |
| Metadata | DOI, year, species (mínimo) | Enriquecimiento MeSH, sample_size, method |
| Reranker | ninguno | cross-encoder fine-tuned solo si filtros MeSH no recuperan |
| Vector DB | local (Chroma / FAISS) | escalar si volumen lo justifica |
| Logic-LM | reglas Python deterministas | Z3 / formal solver solo si volumen lo justifica |

**Principio rector (Magraner Aug 2025):** *"start with simple RAG, measure bottleneck, then decide"*. Comprometer SPECTER+hybrid+GROBID upfront es anti-pattern — el equivalente witt de "build before measuring".

### 4.2 Integración con infra existente

- **MCP / ToolUniverse:** el `hypothesis-generator` puede invocar herramientas existentes de ToolUniverse para verificación de citas (PubMed lookup), enriquecimiento de targets (ChEMBL, OpenTargets), y substrate de literatura. Esto NO añade dependencias nuevas — usa el stack que el equipo Witt ya tiene corriendo bajo `setup-tooluniverse`.
- **Verificación de DOI (Proxy-0):** Crossref API + `tooluniverse-chemical-compound-retrieval` style lookup pattern.
- **Coordinación BWH:** `regulatory-ethics-advisor` ya está en el catálogo bajo esta coordinación; este doc no toca esa relación, solo añade la capa 1 de deny-list pre-display.

### 4.3 Costo estimado Phase I

| Item | Volumen estimado | Comentario |
|---|---|---|
| Eval set inicial | **15 ítems** (no 30) | Escalable si bottleneck evidence lo justifica |
| Generaciones por eval run | 15 × N × 3 perturbaciones × 2 noise probes | N=3 en Method 1; N=1 en Method 2 baseline |
| Frecuencia de eval | semanal | Sonda mensual de drift se super-impone |
| LLM calls por eval semanal | 15 × 3 × 3 × 2 ≈ 270 calls | |
| Eval calls × 32 semanas | ≈ 8.6K calls anuales | |
| Generación productiva | ~10 hipótesis/semana × 32 sem = 320 | Method 2 estándar |
| Rating humano | ~2 h/sem × persona (rotativo) | 1 de 4 del equipo cada semana |
| Infra retriever | Chroma/FAISS local; PyMuPDF | Sin servidor dedicado en Phase I |

**Cabe en $297K / 8 meses / 4 personas con holgura SI Y SOLO SI:**
- N de Self-Consistency se mantiene en 3 (no 5) en Method 1.
- Eval set arranca en 15 ítems (no 30).
- Retriever empieza simple (bge solo, no SPECTER+hybrid).
- GROBID y reranker se difieren hasta tener bottleneck evidence.
- Panel humano = 1 rater rotativo del equipo, no panel externo.

Si Proxy-2 (rating humano) se vuelve bottleneck: muestrear solo top-Q% (Q ≤ 30%) del composite-auditor para el panel en Method 1; en Method 2 el humano del equipo rate-ea solo los candidatos que pasan el pre-filter de schema-completeness.

### 4.4 Caveats de stack

- **Model-id pineado con fecha** (e.g., `claude-opus-4-7-20260120`) es relativamente seguro contra "drift silencioso del proveedor" — Anthropic ya pinea por model-id con date stamps. Los modos reales de drift son: (a) deprecación de model-id con grace period, (b) cambios en wrapper/rate-limiter no documentados, (c) versión del embedding model, (d) corpus PubMed crece ~3000 papers/día.
- **Independencia de generadores en Self-Consistency:** N=5 con mismo modelo y seeds distintas tiene **independencia débil** (mode collapse correlacionado). El composite-auditor entonces NO protege contra alucinación sistémica, solo contra ruido de sampling. Por eso §3.4 exige **familias distintas** cuando el budget lo permite, con anotación en `framework_applied` cuando no hay.

---

## 5. Disciplina overlay: las 6 prescripciones de STRATEGY_FINAL aplicadas OPERACIONALMENTE

Cada subsección de §5 traduce la prescripción correspondiente de `STRATEGY_FINAL.md §5.1–§5.6` a este pipeline.

### 5.1 Sonda de ruido (STRATEGY_FINAL §5.1) → operacional

**Qué es "ruido" aquí:** la misma seed query (e.g., *"novel regulators of pronephros nephron segmentation in zebrafish"*) corrida dos veces con `temperature > 0`, mismo corpus, mismo prompt, mismo embedding index, produce dos sets de hipótesis **no idénticos**.

**Tres ejes medibles:**
- **(a) Retrieval set Jaccard** entre las dos corridas (¿el top-K de papers cambia?).
- **(b) Citation set overlap** en el output sintetizado.
- **(c) Hypothesis-text similarity** (cosine entre embeddings de cada hipótesis pareada por nearest-match).

**Procedimiento:**
- En cada snapshot mensual: eval-set congelado de 15 queries × 2 réplicas idénticas.
- Registrar la mediana de cada eje.
- **EPS = 2σ por eje** (one-sided, alineado con STRATEGY_FINAL §5.1).
- Una "mejora" de prompt/retrieval/reranker cuenta SOLO si el delta supera EPS en su eje correspondiente.

**Esta sonda es complementaria** a la sonda numérica/order/surface de v2.2; no la reemplaza. Las perturbaciones order y surface siguen aplicando literalmente:
- *order*: permutar el orden de papers retrieved — el ranking de hipótesis debe ser estable.
- *surface*: parafrasear el query — top-3 hipótesis deben solaparse ≥2/3.

**Sin esto:** cualquier iteración sobre prompt o retriever reporta ruido de muestreo como progreso — el pecado original v1 de `autoresearch`.

### 5.2 Frontier efectivo (STRATEGY_FINAL §5.2) → operacional

**Qué drifta concretamente:**
- LLM: deprecación anunciada de model-id con grace period; cambios en wrapper/rate-limiter API.
- Embedding model version.
- Corpus PubMed (~3000 papers/día).
- Prompt hash.
- Reranker hash.

**El "config"** que define una corrida es la tupla:
```
(llm_model_id, embedding_model_version, corpus_snapshot_hash,
 prompt_hash, reranker_hash, retrieval_k, rerank_top_n)
```

**Métrica del frontier:** rubric average (Factuality + Citation correctness + Completeness + Novelty + Testability + Uncertainty + Safety) sobre el eval-set congelado, anotado por panel (ver §5.4).

**Re-medición same-config:** cada `REMEASURE_EVERY = 20` hipótesis evaluadas, re-correr el eval-set con el **mismo config que estableció el frontier**. Si la métrica drifta >EPS sin que cambiamos nada nosotros, es drift de fondo (proveedor o corpus) y el "frontier" se reajusta a la medición fresca.

**Sin esto:** comparar una nueva versión de prompt contra un número de `best` de hace dos meses contamina con drift — el caso 1.2577 frío vs 1.2848 caliente de `autoresearch`.

### 5.3 EPS empírico en thresholds del `composite-auditor` (STRATEGY_FINAL §5.3) → operacional

El `composite-auditor` filtra candidatos **SOLO en Method 1** (escalamiento a wet-lab) con dos modos per v2.2 + un gate humano:

**Modo (a) — Self-Consistency:**
- N=3-5 generadores de **FAMILIAS DISTINTAS** de modelos (e.g., 2× Claude + 2× Gemini + 1× GPT cuando el budget lo permite).
- Si solo un modelo está disponible: anotar limitación en `framework_applied` y bajar la confianza por defecto.
- **Threshold = percentil empírico (p25)** de la distribución de agreement-rates bajo replicación idéntica del eval-set, no el "70% arbitrario" — STRATEGY_FINAL §5.3.

**Modo (b) — Logic-LM (criterios formalizables booleanos):**
- *Citation-coverage*: ¿todas las refs citadas existen en el index y resuelven a DOI válido?
- *Contradiction-coverage*: ¿al menos 1 contradictory paper citado en `alternatives_considered.contradictory_evidence_cited`?
- *Schema-completeness*: ¿los 6 campos del contrato Witt + sub-schema obligatorio están poblados?
- EPS binario aquí, no umbral continuo.

**Modo (c) — Human-gate OBLIGATORIO 100%:**
- Toda hipótesis que escale a wet-lab pasa por humano, sin excepción.
- El triage automático (flag `requires_ethics_review`, novelty-score alta) **prioriza la cola**, **NO decide si hay gate**.
- Esto preserva el anti-pattern v2.2: HUMAN GATE not skippable in Method 1.

**Lo que NO es composite-auditor:**
- *Citation-coverage* como puntaje continuo → es **Proxy-0** (calibración, §5.4), NO modo del auditor.
- *Novelty-score* → es **output del `hypothesis-generator`** para que el panel humano ordene la cola — **ADVISORY-ONLY**, análogo a `causal-pruner` v2.2. NO se usa como filtro pre-humano automático (riesgo de filtrar hipótesis verdaderamente novel pero textualmente cercanas a un paper irrelevante).

### 5.4 Calibración reactiva (STRATEGY_FINAL §5.4) → operacional

**Cantidad calibrada:** la `confidence` declarada en el contrato estructurado vs ground truth eventual.

**Problema crítico:** ground truth verdadero (wet-lab) llega meses después — inservible para calibración online.

**Solución: cascada de proxies por latencia:**

| Proxy | Latencia | Qué mide | Owner |
|---|---|---|---|
| **0** | segundos | Verificación automática de citas (DOI exists; claim aparece en abstract) | hook automático |
| **1** | minutos | Self-Consistency agreement rate sobre N=3-5 regeneraciones | composite-auditor (solo Method 1) |
| **2** | días (T+48h) | Panel humano rate-eando rubric (7 ejes) | **ground truth interim canónico** — humano del equipo o LLM de familia distinta |
| **3** | meses | Wet-lab outcome cuando aplica | re-calibra retroactivamente |

**Reglas de actualización:**
- **Rolling K=6 PER-OUTPUT sobre Proxy-2** (no batch de 6 — STRATEGY_FINAL §5.4 exige actualización cada output emitido).
- **Auto-cap rule:** si hit-rate (fracción de hipótesis "high-confidence" rate-eadas ≥4/5 en Factuality+Testability) cae <60% en la ventana K=6, todas las confidences siguientes se clamp-ean al techo `max(declared, 0.6)` hasta que la ventana se recupere.
- **Calibrador isotonic por sub-dominio desde día 1** (Vega et al. Feb 2025): regresiones separadas para signaling vs morphogenesis vs single-cell. No como remedio reactivo — como diseño inicial.

**Identidad del rater obligatoria:**
- Humano del equipo (1 de 4, rotativo, registrado en `case-capture` como `rater_id`), o
- Segundo LLM de **familia distinta** al generador (e.g., Gemini si generador es Claude).
- **Generator ≠ rater no negociable.**

**Budget realista:**
- ~2 h/sem × persona × 4 = ~8 h/sem de rating capacity.
- ~10 hipótesis/sem productivas → cada hipótesis recibe rating en T+48h sin sobrecarga.
- K=6 ventana = ~6 semanas de horizonte → viable dentro de 8 meses de Phase I.

### 5.5 PIVOT_AFTER (STRATEGY_FINAL §5.5) → operacional

**Dos patrones de plateau, ambos detectables con telemetría:**

**Plateau-batch:**
- Trigger: 3 batches consecutivos sin un solo candidato aprobado (`expert_rating ≥ 4` Y `composite-auditor PASS`).
- Implicación: el corpus actual o la estrategia de retrieval no contienen el material para responder la pregunta-semilla.
- Acción: **dispara `governance-proposal` automática** proponiendo switch Method 1 → Method 2; **el switch lo aprueba el humano** vía `program-manager` queue, no el agente solo.

**Plateau-revision:**
- Trigger: 3 ciclos de revisión sobre la misma hipótesis sin que el rubric average suba >EPS.
- Implicación: la hipótesis está atascada en un máximo local de redacción.
- Acción: escalar a `domain-knowledge-curator` para sub-corpus alternativo. Cascada de fixes:
  1. Hybrid retrieval BM25 + dense.
  2. Filtros MeSH ajustados.
  3. Reranker cross-encoder fine-tuned (solo si 1 y 2 fallan).
  4. Fine-tune del embedding (último recurso explícito; anti-pattern Magraner Aug 2025 si se hace antes).

**Sin esta regla:** el agente quema presupuesto del panel humano en lo que `autoresearch` llamó *"20 exps confirmando defaults"*.

### 5.6 Governance-proposals desde el agente (STRATEGY_FINAL §5.6) → operacional

El `hypothesis-generator` puede escribir entradas en su cola de human-gate cuando detecte patología en su propio proceso. **Siempre vía `governance-proposal`, nunca auto-aplicada.**

**Cuatro plantillas pre-aprobadas:**

| # | Trigger telemétrico | Fix-cascade propuesto |
|---|---|---|
| 1. Domain-recall-drop | Fracción de hipótesis sobre sub-dominio X rate-eadas ≥4 en Completeness cae bajo mediana global por 2 ventanas K=6 consecutivas | (a) Hybrid retrieval BM25+dense, (b) filtros MeSH ajustados, (c) reranker tuneado, (d) fine-tune embedding (último recurso) |
| 2. Contradiction-section-empty | Campo `contradictory_evidence_cited` vacío en >40% de outputs | Añadir step "contradiction search" obligatorio (query negada + filtro opposing-conclusion). Flag-eado por `reasoning-exposer` antes de pasar al pipeline |
| 3. Citation-coverage-drift | Proxy-0 cae sin cambios locales | Candidatos: deprecación de model-id anunciada; cambios en wrapper API. Fix: re-pinear model-id, re-correr sonda de ruido §5.1 |
| 4. Sub-domain-calibration-divergence | ECE Proxy-2 diverge por sub-dominio biológico | Isotonic regression separado por sub-dominio (Vega et al. Feb 2025) — pero ya se hace desde día 1; aquí el fix es ajuste de bins, no introducción |

**Reglas de gobierno transversales:**
- `framework_applied` y los triggers auto-detectados son **self-report**. La verificación pasa por la sonda de ruido externa (§5.1) y Proxy-2 (panel humano), NO por la introspección del agente.
- Tener las 4 plantillas pre-aprobadas acorta el ciclo de human-gate de semanas a días — exactamente el patrón meta-loop demostrado por v2 → v3 de `autoresearch`.

---

## 6. Evidencia de substrato producida

### 6.1 Tabla Test-por-Test

| Test | Evidencia DIRECTA del pipeline | Soporte INDIRECTO | Lo que NO se prueba | Failure mode a vigilar |
|---|---|---|---|---|
| **1 Orchestration** | Casi nula como evidencia directa. El pipeline ES una orquestación interna (retriever → reranker → generator → auditor), pero la orquestación Witt es la del *sistema entero* (sim-orchestrator + experiment-designer + scrna-seq-analyst + composite-auditor + accumulator) | Las hipótesis estructuradas alimentan a `experiment-designer` y `benchmark-designer` — esa interface cuenta como pieza orquestable | NO demuestra que múltiples agentes Witt coordinen sin redundancia | Reportar "orquestación" cuando solo hay un pipeline RAG monolítico vestido de multi-agent |
| **2 Agency** | Débil. La "agencia" Witt requiere que el sistema escoja qué pregunta investigar, no solo responder a un query dado. El pipeline default es reactivo | Si se acopla con `literature-monitor` (detecta gaps), el conjunto puede pasar de reactivo a proactivo: literature-monitor identifica el gap → pipeline genera hipótesis sobre ese gap | NO prueba agencia sustantiva. Generar hipótesis es producir texto estructurado, no ejercer agencia sobre el mundo | Confundir "structured output" con "agency". Un JSON bien formado no es un agente con goals |
| **3 Iteration loop** | **Directa y fuerte**, si CADA hipótesis se snapshotea como `case-capture` con `pre_registered_confidence` y luego `accumulator` la compara contra `expert_score` (T+48h) y `wetlab_outcome` (T+meses). Dos agentes distintos del catálogo, NO se confunden | El stream de expert-ratings habilita rolling calibration K=6 per-output (§5.4) | NO prueba mejora si los case captures se hacen ad-hoc o solo para "casos buenos". Sample exhaustivo o el sesgo invalida el claim | Cherry-picking. La regla: todo output del pipeline es case capture, sin excepción |
| **4 Calibration** | **Directa.** El campo `confidence` ES una predicción cuantitativa pre-registrada. Comparada contra `expert_score` (Factuality + CitationCorrectness) produce calibration curves directas. Isotonic / histogram binning per Vega et al. Feb 2025 | El stream lento de wet-lab outcomes da un segundo punto de calibración con horizonte distinto (gold standard, lag meses) | NO prueba calibración del *sistema Witt completo*. Solo del agente generador sobre la métrica "experto califica esta hipótesis como Factual+Cited" | Mezclar horizontes de ground-truth (rapid review vs wet-lab) en una sola curva. Streams separados, K rolling separado |
| **5 Cross-field** | **Cero evidencia directa en Phase I.** | Preliminary feasibility: el mismo pipeline corriendo sobre arXiv (física) vs PubMed (bio) sin cambios arquitectónicos sería *señal débil* de portabilidad — NO demostración. **Regla operativa:** cualquier artefacto cross-corpus lleva flag `EXPLORATORY-NOT-TEST-5` que `investor-relations-drafter` NO puede remover sin escalar a `program-manager` | NO prueba que el substrato Witt generaliza. Test 5 es EXPLORATORIO por la recalibración v1.2 | Sobrevender una demo cross-corpus como "Test 5 evidence" |

### 6.2 Lo que la disciplina de STRATEGY_FINAL habilita por Test

- **Test 3:** sin sonda de ruido (§5.1), las curvas de mejora son ruido. Sin `case-capture-elicitor` exhaustivo, el sample está sesgado. Sin `accumulator` separado, el linaje colapsa.
- **Test 4:** sin calibración reactiva K=6 per-output (§5.4), las curvas se desfasan del drift de proveedor. Sin isotonic por sub-dominio desde día 1, ECE se mezcla.
- **Test 1 y 2:** la disciplina no aporta evidencia nueva — solo asegura que la integración del `hypothesis-generator` con otros agentes Witt sea trazable (via `framework_applied` hash).

### 6.3 Test 5: declaración explícita de no-claim

**Este subsistema NO demuestra Test 5 en Phase I.** Cualquier corrida cross-corpus (arXiv ↔ PubMed, biomédico ↔ física) que se ejecute durante Phase I:
- Lleva flag arquitectónico `EXPLORATORY-NOT-TEST-5`.
- `investor-relations-drafter` no puede remover el flag sin escalar a `program-manager`.
- El reporte explícito incluye: *"exploratory feasibility only, not Test 5 evidence per Phase I recalibración v1.2"*.

Esto materializa la recalibración v1.2 en el pipeline, no solo en el reporte.

---

## 7. Cambios concretos a artefactos existentes de witt

Cada cambio se propone como PR independiente o ADR. Branch base: `feature/hypothesis-generation-subsystem`.

### 7.1 PR-01 — `agent-catalog.md`: añadir `hypothesis-generator`

**Target:** `witt-organogenesis/agent-catalog.md`
**Tipo:** PR
**Cambio:**
- Añadir nuevo bloque `hypothesis-generator` con role spec de §3.2 de este doc.
- Tabla de cap actualizada con conteo pre/post = 16.
- Decisión del slot cedido (opción A recomendada: suspender `ip-patent-watcher`).

**Rationale:** STRATEGY_FINAL §4 pilar 4 (contrato estructurado por experimento) + `research-hypothesis-generation-guide` (los 7 campos del output canónico, mapeados al schema Witt de 6). Sin agente dedicado con contrato explícito, no hay superficie sobre la cual aplicar las prescripciones §5.

### 7.2 ADR-XX — Decisión de slot cedido del cap ~16

**Target:** `witt-organogenesis/adr/` (nuevo ADR)
**Tipo:** ADR
**Decisión:** opción A — extender `accumulator` con responsabilidad del contrato de 7 campos para hipótesis; añadir `hypothesis-generator` como agente separado; suspender `ip-patent-watcher` en Phase I (no crítico a defensibilidad técnica).

**Alternativas consideradas:** B (suspender `investor-relations-drafter` Y `ip-patent-watcher`), C (fusionar `hypothesis-generator` en `accumulator`).

**Firma:** `program-manager`.

### 7.3 PR-02 — `reasoning-exposer.md`: sub-schema obligatorio para hypothesis

**Target:** `agents/reasoning-exposer/SKILL.md`
**Cambio:**
- Mantener el contrato Witt v2.2 de 6 campos sin bifurcar.
- Redefinir el sub-schema de `alternatives_considered` para tareas hypothesis: `{considered: [...], contradictory_evidence_cited: [{paper_id, finding}, ...]}` con `contradictory_evidence_cited` **obligatorio no-vacío**.
- `proposed_experiment` vive como sub-campo de `direct_answer`, NO como séptimo campo universal.
- Documentar que `framework_applied` es self-report (hash de pipeline/prompt/modelo), NO introspección — Anthropic Apr 2025.

**Rationale:** preserva retro-compatibilidad real (un único schema universal). Sin el sub-schema obligatorio, el campo `contradictory_evidence` del `research-hypothesis-generation-guide` (REQUIRED, no opcional) se diluye en `alternatives_considered` históricamente lleno como "considered X and Y" sin evidencia.

### 7.4 PR-03 — `evaluation-runner.md`: 3 ejes de noise probe para hypothesis

**Target:** `agents/evaluation-runner/SKILL.md`
**Cambio:**
- Añadir al protocolo de sonda de ruido tres ejes específicos para outputs de hypothesis:
  1. Retrieval-set Jaccard
  2. Citation-set overlap
  3. Hypothesis-text cosine
- Procedimiento: eval-set congelado de 15 queries × 2 réplicas idénticas, mensual.
- EPS = 2σ por eje (one-sided).
- Mantener las 3 perturbaciones existentes (numerical / order / surface) aplicadas a outputs de hypothesis:
  - *numerical*: alterar sample sizes en el prompt → confidence debe ajustarse.
  - *order*: permutar papers retrieved → ranking estable.
  - *surface*: parafrasear query → top-3 overlap ≥2/3.

**Rationale:** STRATEGY_FINAL §5.1 directo. Sin sonda específica para output multimodal (texto + citas + retrieval), la sonda numérica existente no aplica.

### 7.5 PR-04 — `substrate-evidence-guide.md` (Test 3 section)

**Target:** `witt-organogenesis/substrate-evidence-guide.md`
**Cambio:** bajo Test 3, añadir:
- Definición explícita del "config" de hypothesis-generación como tupla:
  ```
  (llm_model_id, embedding_model_version, corpus_snapshot_hash,
   prompt_hash, reranker_hash, retrieval_k, rerank_top_n)
  ```
- Procedimiento de re-medición same-config cada `REMEASURE_EVERY = 20` hipótesis evaluadas.
- Regla: ningún delta cuenta como "mejora" sin (a) same-config re-measure + (b) EPS check.

**Rationale:** STRATEGY_FINAL §5.2. Drift de proveedor LLM y de corpus PubMed son comparables al drift de throttling laptop de `autoresearch`. Sin same-config re-measure, comparaciones de versión de prompt son ruido.

### 7.6 PR-05 — `composite-auditor.md`: thresholds empíricos + multi-familia

**Target:** `agents/composite-auditor/SKILL.md`
**Cambio:**
- Reemplazar thresholds fijos por percentil empírico:
  - Self-Consistency agreement-rate → **p25** de la distribución de agreement bajo replicación idéntica del eval-set (no "70% arbitrario").
  - Logic-LM checks → binarios (EPS binario, no umbral continuo).
- N=3-5 generadores de **FAMILIAS DISTINTAS** de modelos (no mismo modelo con seeds distintas).
- Si solo un modelo disponible: anotar limitación en `framework_applied` y bajar confianza por defecto.
- Re-clasificar:
  - Citation-coverage → **Proxy-0** (calibration-tracker), NO modo del auditor.
  - Novelty-score → output del `hypothesis-generator`, advisory-only, NO filtro pre-humano automático.
- Human-gate OBLIGATORIO 100% en Method 1.
- Documentar la elección de estadísticos: 2σ para deltas vs baseline (one-sided, novel signal); percentil p25 para thresholds pass/fail en métricas acotadas en [0,1].

**Rationale:** STRATEGY_FINAL §5.3. Cumple el anti-pattern v2.2 (composite-auditor obligatorio en Method 1) y lo refuerza con números reales. Evita scope creep del auditor (citation-coverage y novelty no son funciones de auditor).

### 7.7 PR-06 — `calibration-tracker.md`: cascada de proxies + dos streams

**Target:** `agents/calibration-tracker/SKILL.md`
**Cambio:**
- Definir cascada de proxies (Proxy-0 segundos / Proxy-1 minutos / Proxy-2 días / Proxy-3 meses).
- **Dos streams separados:**
  - Stream rápido: expert ratings T+48h, **rolling K=6 PER-OUTPUT** (no batch).
  - Stream lento: wet-lab outcomes T+meses, K=3 anual.
- Identidad del rater obligatoria (humano del equipo o LLM de familia distinta); generator ≠ rater.
- Auto-cap rule: hit-rate <60% → confidence clamp a `max(declared, 0.6)`.
- Calibrador **isotonic regression por sub-dominio desde día 1** (Vega et al. Feb 2025), no como remedio reactivo.

**Rationale:** STRATEGY_FINAL §5.4. Resuelve el problema de lag de wet-lab que se ignoraba originalmente. La separación de streams evita que el lag de Proxy-3 contamine la calibración online de Proxy-2.

### 7.8 PR-07 — `case-capture-elicitor.md`: snapshot exhaustivo

**Target:** `agents/case-capture-elicitor/SKILL.md`
**Cambio:**
- Cada hipótesis = un case capture obligatorio, sin excepción.
- Schema explícito:
  ```
  {
    hypothesis_id,
    generated_at,
    agent_version,
    pipeline_config_hash,
    pre_registered_confidence,
    rater_id,
    expert_score (nullable, llega T+48h),
    escalated_to_wetlab (bool),
    wetlab_outcome (nullable, llega T+meses)
  }
  ```
- Snapshot INMUTABLE al momento de generación (no esperar outcome).
- Separación explícita de responsabilidades con `accumulator`: `case-capture-elicitor` snapshotea; `accumulator` agrega y mantiene la curva compound-through-use de Test 3.

**Rationale:** Test 3 requiere mostrar que el sistema mejora con uso. Eso solo se demuestra si cada hipótesis queda registrada pre-registered. Cherry-picking colapsa Test 3.

### 7.9 PR-08 — `program-manager.md`: PIVOT_AFTER + governance queue

**Target:** `agents/program-manager/SKILL.md`
**Cambio:**
- Añadir dos triggers PIVOT_AFTER:
  - **Plateau-batch:** 3 batches sin candidatos aprobados → governance-proposal automática proponiendo Method 1 → Method 2 (switch lo aprueba humano, no agente).
  - **Plateau-revision:** 3 ciclos sin mejora >EPS sobre la misma hipótesis → escalar a `domain-knowledge-curator` para sub-corpus alternativo (cascada de fixes documentada).
- Reafirmar regla §15 v3: ningún cambio de Method auto-aplicado.

**Rationale:** STRATEGY_FINAL §5.5; alinea con witt v2.2 donde Method 2 ya es default exploratorio. Evita quemar el panel humano en plateau.

### 7.10 PR-09 — `domain-knowledge-curator.md`: ownership del pipeline RAG

**Target:** `agents/domain-knowledge-curator/SKILL.md`
**Cambio (extender, NO crear agente nuevo — preserva cap):**
- Añadir responsabilidad explícita del pipeline-versioning + parsing + embeddings ownership.
- Phase I empieza minimal: bge-large solo + parsing crudo + metadata mínima.
- Upgrade a SPECTER+hybrid+GROBID **solo si el eval set muestra que el retriever es el bottleneck**.
- `framework_applied` lleva el hash del pipeline para trazabilidad.
- Caveat explícito: cualquier upgrade requiere bottleneck evidence (Magraner Aug 2025).

**Rationale:** El cap de ~16 agentes y el principio "start simple RAG" prohíben tanto crear agente nuevo upfront como comprometer stack pesado. Extender `domain-knowledge-curator` es la opción minimal-invasive.

### 7.11 PR-10 — `regulatory-ethics-advisor.md`: dos capas

**Target:** `agents/regulatory-ethics-advisor/SKILL.md`
**Cambio:**
- **Capa 1 (hook pre-display, determinístico):** deny-list de keywords + patrones MeSH (human embryo, germline editing humano, gain-of-function pathogens). Alta-precisión, baja-recall. Bloquea matches inequívocos ANTES de que cualquier humano lea el output.
- **Capa 2 (post-display LLM-classifier):** edge cases que la deny-list no captura; escala para revisión ética detallada.
- Documentar tasas esperadas FP/FN y proceso de actualización de la deny-list.
- Flag `requires_ethics_review` en el output del `hypothesis-generator` dispara la Capa 2 sin pasar por la Capa 1 (ya pasó).

**Rationale:** Si el control corre solo después de revisión humana, ya leíste el output y sesgaste tu pensamiento. El guard arquitectónico (Capa 1) protege contra eso. La Capa 2 maneja matiz que la deny-list no captura. Sin esta separación, el guard es teatro de seguridad.

### 7.12 PR-11 — `SKILL.md` (meta-loop section)

**Target:** `witt-organogenesis/SKILL.md` (nueva sección)
**Cambio:** codificar las 4 plantillas de `governance-proposal` pre-aprobadas (§5.6 de este doc):
1. domain-recall-drop
2. contradiction-section-empty
3. citation-coverage-drift
4. sub-domain-calibration-divergence

Cada una con:
- Trigger telemétrico explícito (qué métrica, qué umbral, qué ventana).
- Fix-cascade propuesto.
- Owner del approval (humano via `program-manager` queue, regla §15 v3).

**Rationale:** STRATEGY_FINAL §5.6 + meta-loop demostrado por v2 → v3 de `autoresearch`. Tener templates pre-aprobadas acorta human-gate de semanas a días.

### 7.13 Resumen de PRs

| PR | Target | Tipo | Bloquea |
|---|---|---|---|
| 01 | `agent-catalog.md` | PR | Ninguno (entry point) |
| ADR-XX | `adr/` | ADR | Decide slot cedido |
| 02 | `reasoning-exposer.md` | PR | 01, ADR-XX |
| 03 | `evaluation-runner.md` | PR | 01 |
| 04 | `substrate-evidence-guide.md` | PR | 02, 03 |
| 05 | `composite-auditor.md` | PR | 04 |
| 06 | `calibration-tracker.md` | PR | 04 |
| 07 | `case-capture-elicitor.md` | PR | 04 |
| 08 | `program-manager.md` | PR | 05, 06, 07 |
| 09 | `domain-knowledge-curator.md` | PR | 03 |
| 10 | `regulatory-ethics-advisor.md` | PR | 01 |
| 11 | `SKILL.md` (meta-loop) | PR | 08 |

---

## 8. Lo que esto NO resuelve (honesto)

Esta sección existe para evitar el sobre-claim que `STRATEGY_FINAL §3` identifica como el pecado original del run v1 de `autoresearch`. Lo que sigue son **límites duros** de este subsistema en Phase I.

### 8.1 No produce validez científica

Un LLM produce hipótesis **plausibles**, no **válidas**. Las 6 prescripciones de §5 aseguran que las hipótesis que llegan al panel humano sean **honestas en su incertidumbre y libres de auto-engaño por ruido**. La validez sigue siendo wet-lab + experto.

Implicación: ningún reporte de Phase I puede decir "el sistema produjo N hipótesis validadas". La forma correcta es "el sistema produjo N hipótesis con confidence pre-registrada, de las cuales el panel rate-eó M como Factuality+Testability ≥4, y de las cuales K escalaron a wet-lab".

### 8.2 No demuestra Test 5

Test 5 (cross-field) sigue exploratorio per recalibración v1.2 de witt. Cualquier corrida cross-corpus en Phase I lleva flag arquitectónico `EXPLORATORY-NOT-TEST-5` que `investor-relations-drafter` no puede remover.

### 8.3 No resuelve la independencia perfecta de generadores

Self-Consistency con N=3-5 generadores de familias distintas reduce — no elimina — el riesgo de alucinación correlacionada. Si los modelos disponibles entrenan sobre corpora parcialmente solapados (PubMed indexado por todos), modos de fallo compartidos persisten. La detección de esos modos requiere wet-lab.

### 8.4 No sustituye al cognitive scientist hire

El cognitive scientist (a contratar en Phase I per scope original) sigue siendo necesario para:
- Diseñar el rubric de 7 ejes operacionalmente.
- Calibrar el rating humano entre raters (inter-rater agreement).
- Auditar `framework_applied` como self-report (Anthropic Apr 2025) — el cognitive scientist es quien decide qué grado de self-report es aceptable.

Este subsistema no automatiza ese rol.

### 8.5 No protege contra drift de panel humano

Si los 4 raters del equipo derivan su criterio sobre 8 meses, la calibración Proxy-2 deriva con ellos. Mitigación parcial: rotar raters y registrar `rater_id` en `case-capture` permite **detectar** el drift, no **prevenirlo**. Investigación futura.

### 8.6 No es Test 5 ni preliminary feasibility de translation a humano

Cualquier hipótesis del `hypothesis-generator` que toque keywords de translation humana dispara `requires_ethics_review` y pasa por `regulatory-ethics-advisor`. Phase I NO produce evidencia de que el substrato witt aplique a riñón humano — sigue siendo pronephros zebrafish bajo coordinación BWH.

### 8.7 No reemplaza el rol de `literature-monitor`

`literature-monitor` sigue siendo el agente que detecta gaps y emite alerts. El `hypothesis-generator` consume seed queries — incluyendo las que `literature-monitor` emite — pero no las origina por sí mismo. Confundir esto colapsaría Test 2 (agency).

---

## 9. Rollout recomendado

**Principio rector:** *"prueba pequeño antes de armar bien"* — paralelo directo a la lección del run v1 → v2 → v3 de `autoresearch`.

### 9.1 Phase I, mes 1-2 — Bootstrap minimal

**Objetivo:** demostrar que el contrato de 7 campos mapea limpio al schema Witt y que `case-capture-elicitor` snapshotea sin pérdida.

**Pasos:**
1. PRs 01, 02, ADR-XX merged (`hypothesis-generator` declarado, contrato definido, slot cedido).
2. PR 09 merged (`domain-knowledge-curator` extendido, retriever simple).
3. Implementar `hypothesis-generator` minimal: 1 modelo (Claude), bge-large, parsing crudo, sin Self-Consistency.
4. Corrida sobre 5 seed queries de pronephros zebrafish.
5. Validar: ¿el contrato se puebla? ¿`contradictory_evidence_cited` aparece no-vacío? ¿`case-capture` snapshotea?

**Gate al mes 2:** si menos del 80% de los outputs poblan los 6 campos correctamente, NO avanzar — fix prompt/schema antes.

**Lo que NO se hace todavía:**
- Sonda de ruido (necesita eval set congelado).
- `composite-auditor` (no hay Method 1 todavía).
- Calibración (no hay rating histórico).

### 9.2 Phase I, mes 3-4 — Instrumentación de disciplina

**Objetivo:** activar las prescripciones §5.1, §5.2, §5.4 (rápido).

**Pasos:**
1. PR 03 merged (`evaluation-runner` con 3 ejes de noise probe).
2. PR 04 merged (definición de `config` tupla, REMEASURE_EVERY=20).
3. PR 07 merged (`case-capture-elicitor` schema explícito).
4. PR 06 merged (`calibration-tracker` con dos streams; Proxy-2 stream rápido activo, Proxy-3 stream lento aún sin datos).
5. Construir eval set de 15 ítems con ground-truth experta (humano del equipo).
6. Correr sonda de ruido inicial: medir EPS por eje.
7. Activar isotonic regression por sub-dominio (Vega et al.).

**Gate al mes 4:**
- ¿EPS estable entre dos corridas mensuales consecutivas?
- ¿Stream rápido de calibración produce datos K=6?
- ¿Hit-rate >60% en la ventana inicial?

Si NO: investigar bottleneck (es el retriever? el prompt? el rater?). NO escalar a Method 1.

### 9.3 Phase I, mes 5-6 — Escalamiento controlado a Method 1

**Objetivo:** activar Method 1 SOLO cuando una hipótesis escale a wet-lab; instrumentar `composite-auditor`.

**Pasos:**
1. PR 05 merged (`composite-auditor` multi-familia, thresholds p25, human-gate obligatorio).
2. PR 10 merged (`regulatory-ethics-advisor` capa 1 + capa 2).
3. PR 11 merged (`SKILL.md` 4 plantillas governance-proposal).
4. Calibrar thresholds del `composite-auditor` contra noise floor del eval set (no antes — sin datos no se puede).
5. Primera escalamiento de hipótesis a wet-lab (esperado: 1-3 hipótesis en este periodo).
6. Activar las 4 plantillas de `governance-proposal`.

**Gate al mes 6:**
- ¿`composite-auditor` filtra alineado con el panel humano (FP/FN razonables)?
- ¿Alguna `governance-proposal` se disparó? Si sí: ¿`program-manager` la procesó vía §15 v3?
- ¿Calibración Proxy-2 muestra ECE estable por sub-dominio?

### 9.4 Phase I, mes 7-8 — PIVOT_AFTER en vivo + reporte

**Objetivo:** demostrar que PIVOT_AFTER funciona, cerrar el reporte de Phase I con evidencia honesta.

**Pasos:**
1. PR 08 merged (`program-manager` PIVOT_AFTER triggers).
2. Monitorear plateau-batch y plateau-revision en producción.
3. Cerrar el reporte con la tabla §6.1 poblada con datos reales.
4. **Importante:** `investor-relations-drafter` produce un draft del reporte; el flag `EXPLORATORY-NOT-TEST-5` se verifica que no haya sido removido sin escalación.

**Gate al mes 8 (Phase I close):**
- Test 3: ¿la curva compound-through-use existe y muestra mejora >EPS?
- Test 4: ¿la calibración por sub-dominio muestra ECE razonable?
- Test 1 y 2: ¿la integración con `experiment-designer` y `literature-monitor` se documentó (no se demostró fuerte)?
- Test 5: ¿el reporte explícitamente declara EXPLORATORY?

**Si algún Test falla:** governance-proposal automática propone Phase II adjustments. NO se cierra Phase I declarando éxito sin evidencia.

### 9.5 Tabla de gates

| Mes | Gate | Si falla, NO avanzar |
|---|---|---|
| 2 | Contrato se puebla ≥80% | Fix prompt/schema |
| 4 | EPS estable + hit-rate >60% | Investigar bottleneck |
| 6 | composite-auditor calibrado | Recalibrar contra panel |
| 8 | Tests 3-4 con evidencia >EPS | Phase II adjustments |

### 9.6 Cómo se conecta al meta-loop

El rollout entero ES el meta-loop:
- Mes 1-2: el agente se construye minimal.
- Mes 3-4: el agente mide su propio ruido.
- Mes 5-6: el agente filtra con sus propios thresholds calibrados.
- Mes 7-8: el agente propone sus propios fixes vía governance-proposal.

Esto es **exactamente el patrón v2 → v3 de `autoresearch`** demostrado: el agente detecta su propio bug (drift entre configs distintos), propone el fix (effective frontier via same-config re-measure), el humano lo aprueba, se aplica.

---

## Anexo A — Glosario rápido (referencia para nuevos miembros)

| Término | Definición operacional en este pipeline |
|---|---|
| **EPS** | `2σ` para deltas vs baseline; **percentil p25** para thresholds pass/fail en métricas acotadas [0,1] |
| **Same-config re-measure** | Re-correr el eval set con la tupla `config` exacta que estableció el frontier, cada `REMEASURE_EVERY=20` evaluaciones |
| **Proxy-0/1/2/3** | Cascada de calibración por latencia: cite-check (seg) / Self-Consistency (min) / panel (días) / wet-lab (meses) |
| **Rolling K=6 per-output** | Ventana de 6 outputs más recientes, recalculada CADA output emitido (no batch de 6) |
| **Auto-cap rule** | Si hit-rate <60% en K=6 → confidence clamp a `max(declared, 0.6)` |
| **Plateau-batch** | 3 batches sin candidato aprobado → governance-proposal Method 1 → Method 2 |
| **Plateau-revision** | 3 ciclos sobre la misma hipótesis sin mejora >EPS |
| **framework_applied** | Hash de `(model_id, prompt, pipeline, embedding)` — **self-report, NO introspección** |
| **EXPLORATORY-NOT-TEST-5** | Flag arquitectónico inmutable por `investor-relations-drafter` |

---

## Anexo B — Referencias

- `STRATEGY_FINAL.md` (este packet, capa de disciplina).
- `AUTORESEARCH_SCOPE.md` (este packet, scope del run que produjo la disciplina).
- `FINDINGS_may26.md` (este packet, findings empíricos del run).
- `program.md` v3 (este packet, §15 governance rule).
- `research-hypothesis-generation-guide.md` (witt-organogenesis, contrato 7 campos).
- witt-organogenesis v2.2 catálogo de agentes (Method 1/2, cap ~16).
- Vega et al. Feb 2025 (post-hoc isotonic/histogram-binning).
- Magraner Aug 2025 ("start with simple RAG, measure bottleneck").
- Anthropic Apr 2025 (framework_applied como self-report, no introspección).

---

---

## Anexo C — Gaps abiertos (crítico de completitud)

Esta sección recoge **verbatim** los hallazgos del crítico adversarial que cerró el
workflow de generación de este documento. Cada gap incluye `Lo que falta` y
`Adición sugerida`. **Discutir y resolver antes de firmar implementación.**

### Veredicto general del crítico

The proposal is structurally strong and unusually self-aware: it ports the six STRATEGY_FINAL prescriptions, explicitly marks Test 5 as exploratory (with an architectural flag `EXPLORATORY-NOT-TEST-5`), refuses to introduce a knowledge graph upfront, preserves the cap at 16, keeps composite-auditor multi-modal (not single-LLM SI/NO), and reaffirms HUMAN GATE 100% in Method 1. The mapping table autoresearch ↔ hypothesis-generation in §1 is the kind of motivation a reader needs. The cascade of Proxies 0-3 in §5.4 is the single most useful operationalization in the doc.

However, the proposal has nine non-trivial gaps that should be closed before this becomes an implementation plan. The most serious are: (1) miscounting of the hypothesis contract (the source guide lists ELEVEN fields, not seven) which propagates into a §3.3 "decision" that is solving a problem that does not actually exist as stated; (2) Tests 1-4 substrate evidence claimed but never operationalized with concrete metrics, thresholds, or N — §6.1 describes what evidence would look like but never says "Test 3 = ECE delta of ≥X over Y outputs across two rolling windows"; (3) calibration ground truth is treated as if Proxy-2 (expert rate at T+48h) ≈ truth, but expert rating drift is acknowledged in §8.5 and then never instrumented — there is no inter-rater agreement protocol, no anchor item set, no gold standard cross-check; (4) the budget breakdown in §4.3 omits real costs (multi-family API access for Method 1, panel time amortized over the project, infra for Chroma+embedding regen on PubMed-3000-papers/day, GROBID/reranker upgrades that are listed as "if bottleneck" but for which no budget envelope is reserved); (5) no concrete integration with `experiment-designer` and `bwh-coordinator` — the proposal mentions wet-lab escalation 14 times but never describes the handoff packet schema, when it triggers, or who in `bwh-coordinator` owns the IACUC submission timing; (6) the deny-list pre-display hook is asserted but never sourced (which MeSH terms, who maintains, FP/FN review cadence); (7) the rollout's monthly gates are unrealistic for a 4-person team with one rotating rater producing only 10 hypotheses/week — the K=6 rolling window needs ~6 weeks to populate, which collides with the Month-4 gate; (8) `framework_applied` is correctly framed as self-report once but used downstream (in PIVOT_AFTER trigger #3 "citation-coverage-drift without local changes") as if reliable, with no external check; (9) the proposal claims §15 v3 of `program.md` requires human approval of Method switches, but program.md v3 in this repo has 9 pillars not 15 — the §15 reference is unverifiable as written.

Net verdict: ready for an architectural review meeting, NOT ready as a signed implementation plan. The 6-month-to-Phase-I-close timeline as currently written is the most likely failure mode.

### Gaps detallados

#### C.1 — Contract field count miscount (research-hypothesis-generation-guide)

**Lo que falta:** The proposal repeatedly says 'contrato 7 campos' of the research-hypothesis-generation-guide (§0, §2.2, §3.2, §3.3, §7.1). The actual guide at C:\Users\Emmanuel\dev\autoresearch\research-hypothesis-generation-guide.md §1 lists ELEVEN fields: Summary of existing evidence, Gaps in the literature, Candidate hypothesis, Supporting evidence, Contradicting evidence, Testable predictions, Proposed experiment, Required controls, Possible confounders, Confidence level, Citations. The example output (lines 27-54) uses 7 of the 11 (Hypothesis, Rationale, Contradictory Evidence, Testable Prediction, Experiment, Confidence — 6 labels plus implicit Citations). The number '7' is nowhere canonical. §3.3 then makes a 'final decision' mapping 7→6 to avoid a 'fork' — solving a problem manufactured by the miscount.

**Adición sugerida:** Replace every '7 campos' with the actual list from the guide. Show the explicit 11→6 mapping (which fields collapse into `evidence_cited`, which into `gap_flags`, which into `direct_answer` sub-fields). The fields Required Controls, Possible Confounders, and Gaps in the literature in particular need explicit destinations — they are non-trivial to fold into the Witt 6-field schema and the doc currently silently drops them.

#### C.2 — Test 1 substrate evidence — not operationalized

**Lo que falta:** §0 and §6.1 say Test 1 (Orchestration) receives 'indirect' evidence, but never define what counts. The substrate-evidence-guide at /c/Users/Emmanuel/dev/witt-organogenesis/skills/custom/organogenesis-agent-architect/references/substrate-evidence-guide.md §Test 1 specifies engineer-rated response quality on a question bank PLUS an HTML report at conclusion per ADR-0007. The proposal never says: who rates, against what bank, with what cadence, where the HTML lives, or how `hypothesis-generator` outputs comply with the HTML report contract.

**Adición sugerida:** Either explicitly defer Test 1 evidence to other agents and remove the 'indirect support' framing, OR specify: (a) integration with `html-report-contract.md` (which 4 TYPES — A/B/C/D — apply to a hypothesis output), (b) where the report files materialize (`reports/hypothesis-{id}.html`), (c) which composite-auditor check verifies `session_id` references an existing HTML file. Without this, the doc claims substrate evidence it cannot produce.

#### C.3 — Test 2 substrate evidence — not operationalized

**Lo que falta:** §0 says Test 2 (Agency) receives indirect evidence. §6.1 says coupling with `literature-monitor` could move the system from reactive to proactive. But agency in PROJECT_SCOPE.md is measured by workflow completion rates and checkpoint accuracy. The proposal never defines: what workflow boundary counts as 'a hypothesis-generation workflow', what its checkpoints are, what 'completion' means when the final outcome (wet-lab) is months away.

**Adición sugerida:** Either drop the Test 2 claim entirely, or specify the workflow checkpoints: (seed→generated→schema-validated→ethics-cleared→case-captured→rated→[escalated|archived]) with completion rate per checkpoint and a definition of 'agency event' (system-initiated query vs human-initiated).

#### C.4 — Test 3 substrate evidence — quantitative threshold missing

**Lo que falta:** §6.1 says Test 3 is 'directa y fuerte' but never specifies the curve's success criterion. autoresearch v1→v2→v3 had a number (12.5%→100% hit-rate, 26→2 exp budget). For witt the proposal needs: what improvement on what metric over what window proves compound-through-use? Currently the only thresholds mentioned are 'hit-rate <60% → auto-cap', which is an INPUT to calibration not a Test 3 success criterion.

**Adición sugerida:** Define explicitly: Test 3 PASS = `expert_score` mean rises by ≥EPS between two adjacent K=6 windows, AND the rise replicates across two sub-domains (signaling, morphogenesis), AND a same-config re-measurement (per §5.2) does NOT explain the rise. Without this, §6.1 'directa y fuerte' is a slogan.

#### C.5 — Test 4 substrate evidence — sub-domain count and ECE target missing

**Lo que falta:** §5.4 prescribes isotonic regression per sub-domain from day 1 but never says how many sub-domains (the guide names 3: signaling, morphogenesis, single-cell). PROJECT_SCOPE v1.2 defines defensive ECE<0.20 and ambitious ECE<0.10. The proposal never restates these targets per sub-domain. Per-subdomain ECE with N≤~10 hypotheses/week × 32 weeks / 3 subdomains ≈ 100 ratings each — borderline for stable isotonic fit.

**Adición sugerida:** State explicitly: target ECE<0.20 per sub-domain by month 8, minimum N per sub-domain to declare the curve valid, and what happens if a sub-domain doesn't reach N (e.g., bin pooled or sub-domain reported as 'insufficient data').

#### C.6 — Calibration ground truth — Proxy-2 drift not instrumented; inter-rater agreement absent

**Lo que falta:** §5.4 makes Proxy-2 (expert rate at T+48h) the 'ground truth interim canónico' for online calibration, but: (a) §8.5 acknowledges rater drift over 8 months WITHOUT a protocol to detect it; (b) no inter-rater agreement protocol despite 4 rotating raters; (c) no anchor-item set (a small frozen set of hypotheses re-rated by every rater every month); (d) no rule for what to do when Proxy-2 conflicts with Proxy-3 wet-lab outcome months later. The bottom-line risk: Proxy-2 is itself uncalibrated and the entire reactive calibration system §5.4 sits on it.

**Adición sugerida:** Add a 'rater calibration' sub-section: (a) 5-item anchor set re-rated monthly by all 4 raters, target Cohen's κ ≥0.6; (b) when κ drops below threshold, all Proxy-2 confidences in the window are flagged 'rater-uncertain'; (c) when Proxy-3 (wet-lab) arrives and disagrees with Proxy-2, the case-capture stream is retro-corrected and an audit log entry is created; (d) every rater training on a fixed onboarding set before counting toward the K=6 window.

#### C.7 — Budget realism — Method 1 multi-family API access not budgeted

**Lo que falta:** §4.3 lists ~8.6K eval calls/year + ~320 productive hypotheses, but Method 1 escalation requires N=3-5 generators from DIFFERENT FAMILIES (Claude+Gemini+GPT). Each wet-lab-escalated hypothesis therefore consumes 3-5x calls across 3 paid APIs. The doc never reserves budget for Gemini and OpenAI API access (currently only Claude is mentioned). Also: PubMed grows 3000 papers/day (per §4.4) → corpus snapshot regen + embedding pass has compute and storage costs not tabulated. Also: panel-rater 8h/week × 4 people × 32 weeks = 1024 hours of senior scientist time, never costed at fully-loaded rate against the $297K cap.

**Adición sugerida:** Add a sub-table to §4.3: 'Method 1 escalation budget' with explicit lines for Gemini API + OpenAI API + monthly corpus regen + rater hours at fully-loaded rate. Even an order-of-magnitude tabulation will surface whether the 'cabe en $297K con holgura' claim survives.

#### C.8 — Phase I cap accounting — Option A suspends ip-patent-watcher but PROJECT_SCOPE §13/§14 may need it

**Lo que falta:** ADR-XX (§7.2) recommends suspending `ip-patent-watcher` because it is 'no crítico a defensibilidad técnica'. But PROJECT_SCOPE.md frames defensibility as a 4-pillar moat including IP/patents (line 62). The investor-relations-drafter referenced in option B drafts the milestone packet for Phase II financing. The decision to suspend either of these in Phase I has implications beyond the agent catalog. The proposal does not reference §62 of PROJECT_SCOPE or check with `program-manager` and `budget-tracker`.

**Adición sugerida:** Add to ADR-XX: explicit consultation with founder-scientist + budget-tracker before suspending ip-patent-watcher. Provide a recovery plan: how is patent-watch coverage achieved during Phase I if the agent is suspended? Cross-link PROJECT_SCOPE §13-14.

#### C.9 — Missing integration with `experiment-designer`, `bwh-coordinator`, `regulatory-ethics-advisor` for wet-lab escalation

**Lo que falta:** The proposal mentions wet-lab escalation ~14 times but never specifies the handoff. agent-catalog.md `experiment-designer` (lines 154-170) translates pruned recipes to wet-lab protocols and feeds `bwh-coordinator` for IACUC. The proposal's `hypothesis-generator` claims to be upstream of `experiment-designer` but no handoff schema is defined. Specifically missing: (a) which sub-field of the contract becomes the input to experiment-designer; (b) at what point in the pipeline `regulatory-ethics-advisor` Capa 2 fires (post-display LLM-classifier — but BEFORE or AFTER experiment-designer touches the candidate?); (c) `bwh-coordinator` and IACUC submission lead time (zebrafish IACUC is ~4-8 weeks); (d) how `requires_ethics_review` boolean interacts with experiment-designer if the experiment is the very thing requiring review.

**Adición sugerida:** Add §7.13 PR-12 'experiment-designer handoff schema' specifying: input fields, ethics-review gating order (deny-list → schema-validate → experiment-design draft → ethics-Capa-2 → human gate → bwh-coordinator → IACUC submission), and timing constraints. The 'human gate before wet-lab escalation OBLIGATORIO 100%' has no chance of holding if `requires_ethics_review` can be raised AFTER experiment-designer has already drafted a protocol.

#### C.10 — Safety / unsafe-hypothesis taxonomy — deny-list underspecified

**Lo que falta:** §2.1 and §7.11 mention a Capa 1 deny-list (human embryo, germline humano, gain-of-function pathogens), but never: (a) the actual keyword/MeSH-pattern list; (b) who owns updates; (c) the FP/FN target rates; (d) what happens when the LLM phrases an unsafe experiment in oblique terms (e.g., 'chimeric blastocyst' instead of 'human embryo'); (e) review cadence. PROJECT_SCOPE.md line 152 says 'No human embryo experimentation, ever' per ISSCR 2025 — but the proposal's hook is a string-matcher with no semantic backup until Capa 2 (which is post-display!). The architecture has a window where a semantically-unsafe-but-textually-clean hypothesis is displayed to a rater before Capa 2 fires.

**Adición sugerida:** Either (a) move Capa 2 to PRE-display, making the LLM-classifier mandatory before any human sees the output (with caching to keep latency tolerable), OR (b) require Capa 1 deny-list to be machine-generated by an LLM-classifier in offline-batch mode that mirrors Capa 2's logic, refreshed weekly. Also add: explicit list of forbidden topics (ISSCR 2025 alignment), update cadence, owner (regulatory-ethics-advisor), and FP/FN review protocol.

#### C.11 — Reference to program.md §15 v3 does not exist

**Lo que falta:** §2.1, §3.2, §5.6, §7.9, §9.4 all reference 'regla §15 del program.md v3' for human-approval-of-method-switch. The actual program.md in this repo has 9 pillars (per STRATEGY_FINAL §4), not 15 sections. There is no §15. The closest analog is pillar 9 ('Cola asíncrona de human-gate + governance-proposal'). The repeated §15 citation is unverifiable.

**Adición sugerida:** Replace every '§15 v3' citation with the actual program.md reference (pillar 9 or the relevant numbered section once you check the exact program.md in the repo).

#### C.12 — framework_applied self-report is used as ground truth for one of the 4 governance triggers

**Lo que falta:** §5.6 governance trigger #3 ('citation-coverage-drift without local changes') uses `framework_applied` hash to determine if a drift is internal or external (model deprecation, wrapper API change). But §3.2 and Anexo A explicitly say `framework_applied` is self-report, NOT introspection. If self-report is unreliable, then 'without local changes' cannot be detected from `framework_applied` alone — the model could be wrong about its own pipeline state.

**Adición sugerida:** For trigger #3, add an external check: store `pipeline_config_hash` in an OUTSIDE-the-agent ledger (a Python computation over actual API endpoint + model ID + corpus hash from disk), and compare the agent's self-reported hash against the ledger. Only a mismatch between ledger and self-report (or a drift in the ledger) should fire the trigger.

#### C.13 — Knowledge-graph anti-pattern — partially sneaked in via `pipeline_config_hash`

**Lo que falta:** The proposal explicitly avoids upfront knowledge graphs (§4.1, §4.4) — good. But the `framework_applied` schema in §3.2 includes 7 sub-fields of pipeline state that effectively form a small graph of dependencies (llm→prompt→embedding→corpus→reranker→retrieval_k→rerank_top_n). If 'upgrade only with bottleneck evidence' is taken seriously, several of these fields will never exist in Phase I (no reranker, retrieval_k pinned). The schema is partially pre-committing to a future architecture without bottleneck evidence — mild violation of Magraner Aug 2025.

**Adición sugerida:** Trim the Phase I `framework_applied` schema to the fields that actually exist on day 1: {llm_model_id, embedding_model_version, corpus_snapshot_hash, prompt_hash, retrieval_k}. Add reranker_hash and rerank_top_n only when (a) a reranker is added per §5.6 trigger #1 cascade, AND (b) the schema migration is recorded in an ADR.

#### C.14 — Rollout timing — K=6 window doesn't populate by Month 4 gate

**Lo que falta:** §9.2 Month-4 gate requires 'EPS estable + hit-rate >60%' in the K=6 window. But §4.3 says ~10 hypotheses/week productive, with ~8h/week × 4 people rating capacity. K=6 = 6 outputs deep, rolling per output — minimum ~6 working hypotheses with completed ratings before the window is defined. With 2 months of bootstrap (§9.1) consumed before rating starts, ratings begin Month 3. Month 4 has at most ~4 weeks of K=6 data, with the window still in transient. Declaring EPS 'stable between two consecutive monthly runs' (§9.2) requires at minimum two stable K=6 windows = ~12 weeks. The Month-4 gate is unreachable as stated.

**Adición sugerida:** Push the EPS-stability gate to Month 5 or 6; let Month 4 only verify 'stream is producing data' not 'EPS is stable'. Alternatively reduce K to 4 in Phase I bootstrap and document the lower statistical power.

#### C.15 — Test 5 framing — kept honest in §6.1 and §6.3, but pipeline could be run cross-corpus accidentally

**Lo que falta:** The flag `EXPLORATORY-NOT-TEST-5` is explicitly defined and made immutable to `investor-relations-drafter`. Good. But the actual mechanism that ATTACHES the flag is not specified — it's framed as 'any cross-corpus run carries the flag' but no agent owns flag attachment. If `domain-knowledge-curator` (the pipeline owner per PR-09) is the only agent that can pivot the corpus, then the flag mechanism should be a `domain-knowledge-curator` side-effect: corpus pivot ⇒ flag stamped on the next K outputs.

**Adición sugerida:** In PR-09, specify: any corpus-source change in `domain-knowledge-curator` (e.g., add arXiv to a PubMed-only pipeline) emits a flag `EXPLORATORY-NOT-TEST-5` on all subsequent case-captures until the corpus is reverted OR until `program-manager` explicitly approves a Test 5 transition (which Phase I never approves).

#### C.16 — Self-consistency 'independent generators' assumption — partially acknowledged, but no operational mitigation

**Lo que falta:** §4.4 acknowledges that N=5 with same model and different seeds has 'independencia débil'. §3.4 and §5.3 prescribe 'familias distintas'. But the proposal does not require that the Self-Consistency runs use DIFFERENT prompts as well — only different model families. Same prompt across families still risks correlated mode collapse via prompt-induced framing. Also: §5.3 says 'if only one model available: anotar limitación in framework_applied' — but never says WHO decides 'available'.

**Adición sugerida:** Require Self-Consistency runs to vary BOTH (model family) AND (prompt phrasing — at least 2 surface forms drawn from the surface-perturbation set of §5.1). Specify: budget owner (`program-manager` via budget-tracker) decides model family availability monthly; the decision is logged in an ADR.

#### C.17 — Single-LLM auditor anti-pattern — partially re-introduced via `reasoning-exposer` schema validation

**Lo que falta:** §3.4 lists `reasoning-exposer` as the agent that validates the sub-schema. agent-catalog.md line 423 says reasoning-exposer is middleware that enforces output schema. So far so good. But the proposal says reasoning-exposer ALSO validates `contradictory_evidence_cited` is non-empty — a SEMANTIC check (does the cited paper actually contradict?). If reasoning-exposer is a single LLM doing semantic validation of contradictions, it's a single-LLM auditor doing a non-formalizable check. agent-catalog v2.2 §composite-auditor specifically replaced this anti-pattern.

**Adición sugerida:** Split the validation: (a) reasoning-exposer does ONLY the syntactic check (field exists, non-empty, has paper_id+finding) — formalizable, OK as single agent; (b) the SEMANTIC check (does the cited paper genuinely contradict?) goes to composite-auditor's Self-Consistency mode in Method 1, or is deferred to the human rater in Method 2. Explicitly state that no single-LLM semantic auditor exists in the pipeline.

#### C.18 — Cross-link to reasoning-frameworks-catalog and skill-md-templates absent

**Lo que falta:** agent-catalog references `reasoning-frameworks-catalog.md` and `skill-md-templates.md` for new agent SKILL.md creation. The proposal claims it follows Phase-4 of organogenesis-agent-architect (§3.2), but never demonstrates compliance with the SKILL.md template or the description-under-1024-chars rule. The draft frontmatter description for `hypothesis-generator` is not included.

**Adición sugerida:** Add Anexo C: the full draft SKILL.md frontmatter for `hypothesis-generator` (bilingüe trigger description ≤1024 chars per agent-catalog template) and references to specific sections of skill-md-templates.md applied. This is a checklist item that PR-01 reviewers will block on.

#### C.19 — No mechanism for retro-correcting Test 3/4 curves when Proxy-3 contradicts Proxy-2

**Lo que falta:** §5.4 has a fast stream and a slow stream, but never says what happens when they disagree. If a hypothesis was rated 5/5 by panel (Proxy-2) and then failed in wet-lab months later (Proxy-3), what happens to: (a) the historical calibration curve, (b) the affected rater's track record, (c) the prompt or pipeline that generated it? Without retro-correction, the calibration is a moving target that erases its own past errors.

**Adición sugerida:** Add to PR-06: when Proxy-3 arrives, the corresponding case-capture is retro-tagged with `wetlab_outcome`. Any calibration curve generated before that retro-tag is annotated 'pending wet-lab confirmation' until ≥80% of its constituent cases have Proxy-3 outcomes (or are explicitly closed as 'no wet-lab planned').

#### C.20 — Self-consistency within the §5 prescriptions: §5.1 says EPS=2σ; §5.3 says EPS=p25

**Lo que falta:** Anexo A explicitly notes both definitions ('EPS=2σ for deltas; EPS=p25 for thresholds in [0,1]'). This is a deliberate split but creates a naming collision: 'EPS' means two different things in the same doc. §5.5 PIVOT_AFTER uses 'mejora >EPS' without specifying which.

**Adición sugerida:** Rename one of them. Suggested: keep `EPS_delta = 2σ` for change detection and `EPS_pass = p25` for threshold-pass binary decisions. Then in §5.5 'plateau-revision' specify 'mejora > EPS_delta'. Update Anexo A and every internal reference.

---

**Fin de INTEGRATION_PROPOSAL.md** (synthesis + Anexo C).
