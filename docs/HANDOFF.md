# HANDOFF — GWT v1.1 (handoff único estable · al 2026-07-05)

> **Siguiente agente:** `CLAUDE.md` se auto-carga (contrato operativo — léelo primero). **Este** es el único
> handoff vigente: estado del sistema, cómo operarlo, decisiones, y qué sigue. Es la fusión de los dos
> handoffs previos (despliegue + sesión del loop); el detalle histórico vive en git.

---

## TL;DR — qué es el sistema hoy

La **DATA INAMOVIBLE** (fuente de verdad compartida del proyecto) está **desplegada y viva** en el Dokploy del
usuario, y es un **sistema que responde preguntas y se refuerza solo**, todo human-gated:

- **Guía:** Neo4j GraphRAG (documents + chunks + embeddings OpenAI 1536-dim + entidades verificadas).
- **Backing:** raw store híbrido — público = source-pointer (URL+sha256, re-descargable); privado/derivado = MinIO.
- **Front door:** MCP `data-inamovible` (`query_data_inamovible` semántico · `resolve_identifier` determinista · `fetch_raw` drill-a-crudo).
- **Loop auto-reforzante (ADR-0022):** `Path A (DI) → si insuficiente → Path B (EuropePMC / Tool Universe) → composite-auditor ≥3 → propose → GATE HUMANO → re-ingesta`. "No está en la DI" **no es stopper** — es disparador de aprendizaje. El store **crece con el uso**.

**Código home:** repo PRIVADO `Emma-NukeAI/Witt-organo` (`origin`). `master` = la última versión (**sesión 2026-07-05, audit total**; ver §Estado git).
**Nunca** pushear a `polimat-old` (repo viejo, además caído). Local se trabaja en `feat/gwt-v1.1-cycle1` (== master).

**Última sesión (2026-07-04/05) — ver la sección nueva abajo:** **auditoría de funcionalidad TOTAL** +
composite-auditor (3 auditores adversariales Opus). Se probó la maquinaria offline + en vivo (Neo4j retrieval,
ambas ramas del `answer_pipeline`, Path B Reactome, MinIO round-trip, sandbox DI mutation, squidiff Mode 0,
human gate del ingest_service). Entregables: **sync de contratos** (CLAUDE/SCOPE/README a la realidad) +
**gate anti-drift** `doc_coherence_check.py` + `smoke_contract.py` (30 offline / 34 live PASS) + **regla no-hang
MCP** (§6) + allowlist MCP + **ADR-0030** (`compute_ece` "satisfied"→"aggregate-captured", disciplina ADR-0005) +
Test 5 cross-field round-2 (case-capture). Veredicto: **APPROVE_MINOR** sobre "la maquinaria funciona como se
documenta"; **REVISE** sobre "totalidad" (cerrado en su mayoría; residuales abajo). El panel atrapó 2 over-claims
del operador — corregidos. **Cero mutación de la DATA INAMOVIBLE** (todo read-and-report / sandbox).

**Sesión previa (2026-06-22/23) — ver las 2 secciones más abajo:** MITAD_A **endurecida** tras validación
adversarial (ADR-0027: binding símbolo↔ENSDARG, gates §4/§11 reforzados) + **guard de validez-de-lente**
(ADR-0028) + la **DATA INAMOVIBLE creció 46→51** human-gated (ADR-0029) + **test E2E** (3 rounds, pronefros).

---

## Auditoría de funcionalidad total + composite-auditor (sesión 2026-07-04/05)

Se auditó **toda** la funcionalidad contra lo que dicen CLAUDE / SCOPE / HANDOFF. Resultados y artefactos:

- **Sync de contratos (drift arreglado):** CLAUDE.md §12 (store 32→**51 records**, ADRs 0027–0030), PROJECT_SCOPE v1.3 (notas de estado §6/§7: los diagramas son intención de abril; el "Yes/No Auditor" está derogado por composite-auditor), README (versiones + 30 ADRs). Causa raíz: docs narrativos repiten datos que viven en fuentes de verdad y se pudren.
- **Gate anti-drift NUEVO:** `substrate_calibration/tools/doc_coherence_check.py` (7 invariantes doc↔fuente-de-verdad: store count/version, ADR más alto, versiones de scope/skill) + hook opt-in `.githooks/pre-commit` (`git config core.hooksPath .githooks`). Convierte el drift de "se descubre en audit" a "falla el commit".
- **Smoke de contrato NUEVO:** `substrate_calibration/tools/smoke_contract.py` — cada aserción cita el doc/§ que verifica; **30 PASS offline / 34 PASS live / 0 FAIL** (live: `SMOKE_CONTRACT_LIVE=1` + secrets). Cubre §7 gate, §4/§11 reflejos, write-spine (sandbox), squidiff Mode 0, MinIO, Neo4j, ambas ramas del pipeline, human gate del ingest_service.
- **Regla no-hang MCP (§6) + allowlist:** el MCP es mejora, nunca bloqueante (timeout→offline, salud se re-chequea 1×, no en bucle). Allowlist de tools MCP read-only + `execute_tool` en `.claude/settings.json` (compartido) para que no pidan aprobación cada vez. *Nota: cambios de permisos se leen al **reiniciar** Claude Code.*
- **ADR-0030** (`compute_ece`): un snapshot transversal ya **no** emite "satisfied" → `aggregate-captured`; reporta la sub-métrica ≥85% high-conf. "satisfied" requiere además el arco longitudinal (meses 0/4/8) — no establecible en un run. Vino de un catch del composite-auditor (lente overclaim).
- **Composite-auditor (Mode 1, 3 Opus adversariales):** metodología APPROVE_MINOR 0.86 · overclaim APPROVE_MINOR 0.82 · cobertura **REVISE** 0.86. Todos los findings MINOR corregidos; el REVISE de cobertura se cerró con round-2 (sandbox mutation, squidiff, MinIO, Path B Reactome, ingest gate). El panel atrapó 2 over-claims del operador ("single skill" vs mosaico 10×n=1; verbo "satisfied") — corregidos. Reporte TYPE D: `reports/2026-07-05_full-functionality-audit_composite.html`.
- **Test 5 cross-field round-2** (`analysis/outputs/poc_crossfield_test5_round2_20260705.json`): Path B Reactome sobre TFs compartidos riñón↔ojo → **todo renal, cero vías oculares** (PAX6/FOXC1/PITX2 incl.). Hallazgo honesto: la capacidad corre, pero **la lente Reactome está anotada asimétricamente** (kidney-biased) → convergencia no demostrable por esa ruta (consistente con Magraner 2025 + el artefacto-de-overlap previo). Case-capture, exploratorio.

**Residuales honestos (NO probados, por diseño):** MERGE real contra Neo4j vivo (sandbox por elección; el ingest_service se probó hasta el human gate submit→401, NO se corrió `/approve`) · `ingest_service` hosted no alcanzable desde local (sin tokens/URL en `.secrets/`) · squidiff **Mode 1** real (torch/pesos) · Test 4 longitudinal · Test 5 con lente ocular-específica (no hay API pública limpia zebrafish).

**Lección (repetida): el composite-auditor atrapa un over-claim en cada round, incl. del operador.** No leer "ausente de una lente" como "evidencia en contra".

---

## Qué está vivo (Dokploy — 3 stacks)

| Stack | Puertos host | Notas |
|---|---|---|
| **Neo4j** (grafo + HNSW vector index) | 7474 browser, 7687 bolt | ~27 docs / 44 entidades; índice `doc_embeddings` ONLINE; nodo `(:Meta {key:'data_inamovible'})` con embed_model/dim/doc_count/refreshed_at |
| **MinIO** (raw store S3) | 9100 API, 9101 consola | bucket `data-inamovible-raw`; **vacío** = correcto (todo lo cargado es público=source-pointer; MinIO solo guarda privado/derivado) |
| **ingest service** (FastAPI) | 8077 | submit token → admin `/approve` gate → ingest + git push-back |

Endpoints + credenciales en `.secrets/deploy.env` (gitignored, en la máquina del usuario): `NEO4J_*`,
`OPENAI_API_KEY`, `MINIO_*`. Embeddings se computan client-side (la metodología vive en git `rag_index/graphrag/`;
se cambia ahí + re-ingesta, nunca editando el servidor). Corpus cargado: ZESTA (13 .h5ad, source-pointer) +
GSE218068 (ocular) + CORPUS-2026-0003 (paper prkci, abstract).

## Las 3 capas de la DATA INAMOVIBLE (dónde vive cada cosa, consultable SIN agente)

- **Índice + embeddings** → **Neo4j** (Browser/Cypher en `:7474`).
- **Raw público** → **en la fuente** (NCBI/CNGB/EuropePMC); guardamos solo URL+sha256. **Raw privado** → **MinIO** (`:9101`).
- **Catálogo + método** → **git** (`rag_index/corpus_manifest.json`, `analysis/outputs/verified_identifiers.json`, código).
- Cache de trabajo (descargas, bundles, papers crudos) → `mcp_cache/` (gitignored, local).

---

## Decisiones / principios (en CLAUDE.md §7 + memoria) — VINCULANTES

1. **Gasto autorizado; mejores modelos siempre.** Agentes usan `claude-opus-4-8` por defecto, `claude-fable-5`
   para lo más exigente; **NUNCA degradar a Sonnet/Haiku por costo**. Se optimiza la **respuesta**, no la factura.
   (Medidor chico = embeddings OpenAI; medidor grande = agentes Claude, p.ej. composite-auditor ≥3 ≈ $1–2.5/run.)
2. **Toda mutación de la DATA INAMOVIBLE es human-gated + especificada** — ADD/EDIT/DELETE × embedding/índice/raw.
   `ingest.py` = add/update-only (MERGE, **nunca borra**); pruning = propose→gate→execute; cambiar embed-model
   **se detiene** pidiendo confirmación. **Reads/refresh libres; mutaciones no.** Eso la hace *inamovible*.

---

## MITAD_A reforzada (R1–R4) + MITAD_B arrancada (ciclo 2026-06-18)

Del análisis concept-bridge (`reports/concept-bridge-{analysis,map}-v1.html`, composite-audited 3/3): Witt es
una "máquina epistémica recursiva" de **dos mitades**. **MITAD_A = rendición de cuentas** (este repo) — ya casi
completa, ahora reforzada. **MITAD_B = motor de generación** (energy layer, RL epistémica aprendida, motor
JAX-DSL diferenciable-evolutivo, program search) — las GAPs reales; vive **AISLADA en un repo separado**.

**MITAD_A — 4 workstreams reuse-first, read-and-report (cero mutación de la DI), cada uno con ADR + claim
record §5 + composite-auditor ≥3** (commit `8ba31a4`):
- **R1 (ADR-0023)** — cierre del loop de aprendizaje: `replay_and_regress.py` (detector Δv<0; atrapa la
  corrupción marker-ID 2026-06) + `governance_prefilter.py` (pre-filtro no-regresión **advisory**, antes del
  human-gate; Tarski/Gödel, H = held-out) + `build_regression_cases.py` (`failure_log` → guards replayables
  permanentes en `substrate_calibration/regression_cases/`).
- **R2 (ADR-0024)** — pureza + admisibilidad: `verify_output.admissible()` H(c)∈{0,1} (ningún score blando
  rescata un claim inadmisible) + `tier_weight` Bayes-purity (RAW=1.0/DERIVED=0.7/NOT_FOUND=0.0), estampado en
  `:Entity`/`:MENTIONS` en la próxima ingesta human-gated.
- **R3 (ADR-0025)** — gates verificables: `accountability_checks.py` (§4 framework-citation + §11
  agents_invoked); forward-enforcement del `framework_miscited` (marca los 4 records legacy "§Tier 2", inmutables).
- **R4 (ADR-0026)** — esquema World-State-Transition unificado: `world_state.py` `⟨S, do(a), Δŝ, W, F⟩` con
  do-typing (`causal_admissible` solo si `do`; conditioning ≠ causación) + `answer_pipeline.tool_universe_directive`
  (Path B nombra la consulta MCP de Tool Universe). *El audit de R4 dio REVISE→fixed: 2 bugs reales (crash con
  intervención non-dict + `UnicodeEncodeError` cp1252) corregidos; el guard cp1252 `sys.stdout.reconfigure` ahora
  está en los 5 tools.*

**MITAD_B — repo HERMANO separado `conciencia-universal`** (NO en este repo): `C:/Users/Emmanuel/dev/conciencia-universal`,
remoto privado propio **`Emma-NukeAI/conciencia-universal`** (génesis `868404a`). Aislado a propósito (puede
arriesgar la estructura de A): lee la DI **solo-lectura** vía el MCP `data-inamovible` (cero escritura), **nunca**
muta A; el conocimiento re-entra a A solo por su camino human-gated (`add_dataset`→`approve_dataset`). Default
**A1 proposal-only** (escalera Sakana A0–A6; máx A2 hasta validadores de B). Scaffold + contrato A↔B
(`docs/A_B_CONTRACT.md`) + primer target = la **Energy Layer**. **NO** construir el motor aún.

---

## MITAD_A — endurecimiento de detección + ajustes post-E2E (sesión 2026-06-22/23)

**Validación adversarial de MITAD_A (2026-06-22):** se probó a ROMPER la mitad de rendición de cuentas.
Resultado: la **capa de seguridad se defiende sola e irrefutable** (read-and-report, advisory, human-gated;
3 auditores no pudieron mutarla — SHA del store estable, cero camino de escritura). La **capa de detección
tenía bypasses reales**. Se endurecieron TODOS el mismo día.

**ADR-0027 — hardening de detección** (commit `ad9e102`; smoke durable `substrate_calibration/tools/smoke_adr0027_hardening.py` = 22/22; cerrado con composite-auditor 3/3 APPROVE_MINOR, REVISE aplicado en sesión):
- **N1** — `verify_output` valida el **binding símbolo↔ENSDARG** (pares estructurados, incl. la forma real `{marker,ens_id}` de `01_schoels` + reverse-binding key-agnóstico). Antes solo checaba que el ID *existiera*, no que estuviera *ligado* al símbolo correcto — la corrupción que motivó el gate.
- **W1** — agente requerido marcado `not-applicable` sobre señal **fuerte** → FAIL (antes WARN).
- **W2/N3** — generación detectada por **estructura** (campo de candidatos con forma de símbolo génico) o categoría auto-identificada; `claim_category` ya **NO es supresor** (cerró el mislabel `methodological`).
- **N6** — el quote de `framework_applied` se **valida contra el texto real del catálogo** (en §N → PASS; en otra parte → WARN; fuera → FAIL fabricado); escanea TODOS los quotes + longitud mínima + atribuye la tabla-resumen a su sección.
- **W5** — `world_state` da `causal_admissible` solo con bloque WSTS **explícito**; keyword-inferido → `candidate` (mató un over-fire del 66% sobre los propios R-records).
- **W3** — `build_regression_cases` acepta `id_corrections` estructurado (un fallo masivo → un guard por símbolo).
- **N2** — extractor ENSDARG tolerante (case/separador/versión) + canonicalización.
- **Bug latente arreglado:** `compute_ece.load_records` leía sin `encoding="utf-8"` (mojibake cp1252 que rompía N6) — es el loader compartido por los 4 R-tools.

**ADR-0028 — guard de validez-de-lente** `substrate_calibration/tools/evidence_weighting.py`: convierte un catch del auditor en código determinista. `EVIDENCE_TIER` (native_perturbation 1.0 > native_expression 0.7 > ortholog_regulatory 0.5 > pathway_membership 0.2 > absence 0.0) + `rank_with_lens_validity()` con `overclaim_flag` cuando el top-crudo es sub-nativo mientras otro candidato tiene evidencia nativa. Companion: paneles Self-Consistency **perspectiva-diversos** (catálogo §4). **Límite conocido:** silencioso cuando NADIE tiene evidencia nativa de rol (debilidad uniforme) — refinamiento futuro.

**ADR-0029 — la DATA INAMOVIBLE creció 46→51** (`store_version` `2026-06-11.1`→`2026-06-23.1`; SHA `f070b40c…`→`5f4d0bf9…`), **HUMAN-GATED, ADD-only**: +5 marcadores de señalización/inducción del pronefros, tier **RAW**, ENSDARG resueltos **live de Ensembl REST** (raw cacheado §7.9): `osr1`=ENSDARG00000014091, `wnt8a`=…052910, `fgf8a`=…003399, `aldh1a2`=…053493, `cyp26a1`=…033999. Vía el único escritor `build_verified_store.py` + nuevo `analysis/outputs/signaling_markers_curated.json` + snapshot `verified_identifiers.v2026-06-11.1.json` (reversible). Commits `bb2671e`/`5782bad`.

---

## Test E2E de la pipeline completa (3 rounds, 2026-06-22/23)

Se probó la maquinaria COMPLETA con una pregunta real (within-niche N3/N4): **¿qué señal upstream induce/regula
el set mínimo de TFs del pronefros?** Recorrido: DATA INAMOVIBLE → Tool Universe → gate de adición de tool →
Self-Consistency → causal-pruner (matriz de dominios) → composite-auditor.

**Tools de lente nuevas** (en `.tooluniverse/tools/`, custom workspace, API directa, sin key; `profile.yaml` commiteado, `.env` gitignored):
- `zfin_zebrafish.py` — fenotipos zebrafish (ZFIN vía Alliance of Genome Resources, taxon 7955); resuelve símbolo→curie live + filtro de anatomía + PMIDs = lente de **perturbación nativa (LOF)**.
- `europepmc_literature.py` — lente de **literatura** (Europe PMC; PubMed+PMC+preprints; ranked por citas).
- **Gap documentado:** NO hay API JSON pública sin fricción para **expresión baseline zebrafish** (probadas Expression Atlas/Bgee/ZFIN/Alliance → 404/400/key/HTML). Mismo patrón "tooling zebrafish delgado".

**Tool Universe MCP SÍ conectó** esta sesión (`mcp__tooluniverse__execute_tool`: Reactome enrichment + OmniPath
signaling sobre ortólogos humanos). **Path B real ejercido.** Es **human-céntrico** (KEGG hsa, OmniPath/PANTHER
default 9606; RA invisible a PPI) → para zebrafish, ortología + las tools ZFIN/EuropePMC.

**Estado de la hipótesis biológica (causal-pruner HYPOTHESIS, human-gated — NO repetir, construir sobre ella):**
la inducción está **sustancialmente AFINADA pero NO resuelta**:
- Cascada dentro del IM competente: **RA → osr1 → wnt2b/pax2a/lhx1a** (osr1 = nodo TF proximal, downstream de RA — PMID:22129829/36359386).
- **FGF (fgf8/fgf24, redundante):** necesario para el campo mesodérmico posterior (compound-LOF, PMID:12925590) + **promueve fate pronéfrico vs sangre/endotelio, dosis-dependiente** dentro del campo (PMID:24008197/PMC3919442; dirección verificada vs texto primario). = asignación-de-fate instructiva, **NO** inducción ectópica, **NO** el nodo proximal. (Corrige tanto "FGF prescindible" como "FGF top inducer" — la verdad está en medio.)
- **Wnt (wnt8a):** permisivo/posteriorizante; wnt2b downstream de osr1.
- **Suficiencia (inducción ectópica por señal sola): NO TESTEADA** (sin dato GOF en estas lentes; absence-of-evidence, NO negativo demostrado) → solo la cierra **wet-lab GOF** (Fase II).

**Lección recurrente (CRÍTICA para el próximo agente):** el composite-auditor atrapó un over-claim en **cada
uno de los 3 rounds** — incl. del operador 2× (violación §7.9 al cachear un *resumen* en vez del *crudo*;
whiplash de FGF). El fallo que reaparece: **leer "ausente de una lente" como "evidencia en contra"** (RA invisible
a PPI; suficiencia ausente de una búsqueda citation-sorted shallow). NO cometerlo; cachear SIEMPRE el crudo (§7.9).
Reportes: `reports/2026-06-22_pronephros-upstream-signal_e2e.html` (r1) · `…_e2e-round2.html` · `…GOF_e2e-round3.html`;
validación MITAD_A: `reports/2026-06-22_mitad-a-{adversarial-validation_retrospective,gate-coverage-matrix,hardening_retrospective}.html`.

---

## Archivos clave

| Concern | Archivo |
|---|---|
| Resolver determinista de IDs (anti-fabricación) | `analysis/scripts/lib/resolve_id.py` + `analysis/outputs/verified_identifiers.json` (**v2026-06-23.1, 51 records**; +5 señalización ADR-0029); gate `verify_output.py` (binding N1 + regex tolerante N2) |
| Raw store híbrido (MinIO/source-pointer) | `analysis/scripts/lib/raw_store.py` |
| Retrieval semántico (sparse Tfidf + Neo4j vector, RRF); **auto-refresh por mtime** | `analysis/scripts/lib/rag_backend.py` |
| Embeddings + carga a Neo4j; **ensure-index + dim-guard + model-halt + freshness stamp + rebuild sparse** | `rag_index/graphrag/{embeddings,bootstrap,ingest}.py` |
| **Loop (ADR-0022):** drill-a-paper · orquestador con state-machine · propose · prune | `analysis/scripts/lib/{fetch_paper,answer_pipeline,propose_from_external,propose_prune,approve_prune}.py` |
| **MITAD_A R1–R4 (ADR-0023–0026):** loop-regresión · admisibilidad+pureza · gates §4/§11 · esquema WSTS | `substrate_calibration/tools/{replay_and_regress,governance_prefilter,build_regression_cases,accountability_checks,world_state}.py` + extensiones de `verify_output.py`/`ingest.py`/`answer_pipeline.py` |
| **MITAD_A hardening + guard (ADR-0027/0028):** binding símbolo↔ENSDARG · gates §4/§11 endurecidos · validez-de-lente | `verify_output.py` (N1/N2) · `accountability_checks.py` (W1/W2/N3/N6) · `world_state.py` (W5) · `build_regression_cases.py` (W3) · `substrate_calibration/tools/{evidence_weighting,smoke_adr0027_hardening}.py` |
| **Lentes zebrafish (custom Tool Universe workspace):** perturbación nativa ZFIN · literatura EuropePMC | `.tooluniverse/tools/{zfin_zebrafish,europepmc_literature}.py` (+ `profile.yaml`) |
| Contribución (repo-side): propose → gate humano → ingest | `add_dataset.py` + `approve_dataset.py`; `CONTRIBUTING.md` |
| Chunking de papers/PDFs | `analysis/scripts/lib/chunk_document.py` |
| Liveness NO-SPEND | `rag_index/graphrag/liveness.py` |
| **Tool Universe (Path B) garantizado para el equipo** | `.mcp.json` (raíz, project-scope, `uvx tooluniverse@1.2.6`) + `mcp-config/README.md` |
| Decisiones | `docs/decisions/` (ADR-0020 GraphRAG, 0021 raw store, **0022 answer-pipeline loop**, **0023–0026 MITAD_A R1–R4**, **0027 detection-hardening**, **0028 lens-validity guard**, **0029 DI signaling-add**, …) |

---

## Cómo operar

```bash
set -a; . .secrets/deploy.env; set +a; export RAG_BACKEND=neo4j

./.venv/Scripts/python.exe rag_index/graphrag/liveness.py                 # liveness NO-SPEND
./.venv/Scripts/python.exe analysis/scripts/lib/answer_pipeline.py "¿...?" --entities gA,gB
#   -> decision_state. Si FALLBACK_FETCHED: composite-auditor ≥3 sobre los papers -> record_audit;
#      si APPROVE -> propose_from_external -> approve_dataset (GATE HUMANO) -> ingest.
# fetch:   fetch_paper.py --external "PMID:..."  |  --internal CORPUS-2026-NNNN[#cNNN]
# ingest:  approve_dataset.py CORPUS-... --by <humano>   (corre ingest.py: re-embed + rebuild sparse + Meta)
# prune:   propose_prune.py -> revisar -> approve_prune.py <archivo> --by <humano>   (nunca auto-delete)
```

**Tool Universe:** reabrir Claude Code → aprobar el server `tooluniverse` del `.mcp.json` → `/mcp` confirma.
Primer arranque de `uvx` es lento (30–60s); si hace timeout: `MCP_TIMEOUT=120000 claude`. Claves (NCBI/NVIDIA/FDA)
opcionales, en el shell (no en git). *No conectó la última sesión hasta reabrir — es lo único del loop sin probar live.*

---

## POC del pronefro (validado, auditado)

Smoke test end-to-end cerrado: liveness ✓ · re-anclaje conjunto-mínimo (el gate atrapó 3/9 genes ausentes) ✓ ·
el loop respondió prkci (Gerlach & Wingert 2014, PMID 25446529, NO-OA; auditado 3/3; ingerido) ✓ · Test 5
cross-field (foxc1a↔foxc1b = **hipótesis**; overlap de 40 entidades = **artefacto de anotación**, no co-regulación).
El **composite-auditor de cierre votó 3/3 REVISE** y se corrigió (calibración real). **El sistema quedó validado
end-to-end; la suficiencia biológica del conjunto-mínimo sigue ABIERTA** (sin reconstitución). Reportes:
`reports/poc-pronephros-di-loop-crossfield-v1.html` · `analysis/outputs/poc_crossfield_test5_20260613.json`.

---

## Abierto / próximos pasos

1. **Tool Universe MCP — ya conectó** (Reactome/OmniPath usados esta sesión, Path B real). Pendiente: usarlo con su amplitud real de forma rutinaria; es **human-céntrico** → para zebrafish, ortología + las tools custom ZFIN/EuropePMC. Reabrir Claude Code + aprobar el `.mcp.json` si no aparece.
2. **Suficiencia de la inducción del pronefros → solo wet-lab GOF (Fase II):** ectopic Wnt/FGF en tejido no-IM → ¿osr1/pax2a ectópico? + compound-LOF fgf8+fgf24 graded. La cascada `RA→osr1→wnt2b` ya está anclada in-silico; lo único que falta para "inductor" es la suficiencia, que NO es in-silico. (Suficiencia del conjunto-mínimo de TFs también sigue ABIERTA, igual.)
3. **Lente de expresión baseline zebrafish — gap real:** ninguna API JSON pública limpia (Atlas/Bgee/ZFIN/Alliance). Futuro: ZFIN XHR endpoint o Bgee con api_key, o `fetch_raw` de h5ad de expresión. No bloqueante (la perturbación es la lente decisiva).
4. **Crecer corpus/store:** workflow de contribución + `candidate_store_additions` (genes frecuentes no-en-store → verificar live + agregar, **gated**). Candidato inmediato: `fgf24` (resuelto live este round, aún no anclado).
5. **Refinar `evidence_weighting` (ADR-0028):** emitir warning cuando el weighted_top tiene best-tier sub-nativo aunque NO haya conflicto (caso de debilidad uniforme — hoy es silencioso).
6. **Embed-cache en `ingest.py`** (re-embebe todo; ok con ~27 docs).
7. **Diferidos de despliegue:** git push-back (PAT), security hardening de puertos Dokploy, "universe" viz, RIL Cycle 3.
8. **MITAD_B (`conciencia-universal`):** primera corrida **A1** (Proposals de diseño de la Energy Layer); vendorizar los esquemas de objeto del bridge al pasar A1→A2; sandbox-validator antes de cualquier A3.
9. **Wiring diferido de MITAD_A:** `compute_ece` por-tier (hasta acumular records RAW resueltos); emisión nativa del bloque `world_state_transition` por cascade-sim/squidiff; EVPI calibrado (placeholder).

## Gotchas

- Tool Universe MCP no queda activo hasta **reabrir Claude Code + aprobar** el `.mcp.json` (+ `MCP_TIMEOUT` si arranque en frío). El SDK no está en `.venv`.
- Consola Windows = cp1252 → `PYTHONIOENCODING=utf-8` (los scripts ya lo manejan; mojibake en consola, datos utf-8 OK en disco).
- `ingest.py` re-embebe TODO el corpus cada corrida (ok ahora). Los `answer_bundle`/papers crudos viven en `mcp_cache/` (gitignored) — el registro durable son los HTML/JSON commiteados + el código.
- EuropePMC full-text endpoint = `/{PMCID}/fullTextXML` (sin segmento source). `gh` CLI no instalado; usa `git` + REST.
- **No hay API JSON limpia de expresión baseline zebrafish** (Atlas 404, Bgee 400/key, ZFIN HTML, Alliance `/expression*` 404). Usa fenotipos ZFIN (perturbación) + literatura; el lens de expresión es trabajo futuro.
- **§7.9 — cachear el CRUDO, no un resumen.** Las búsquedas EuropePMC default ordenan por citas (`sort=CITED`) → top-5 de miles de hits = reviews; úsalas con queries específicas o pagina por relevancia. **NO leas "ausente de la lente" como "evidencia en contra"** (RA invisible a PPI; sufficiency ausente de un search shallow) — es el fallo que el composite-auditor atrapó repetidamente.
- **Tools custom de Tool Universe** viven en `.tooluniverse/tools/*.py` (workspace auto-discover). Importables standalone (urllib, sin `tooluniverse` instalado); el SDK del MCP corre aislado en `uvx` (el test standalone ES la verificación). `.tooluniverse/.env` gitignored; `profile.yaml` sí se commitea.

## Estado git

**Dos repos privados, aislados estructuralmente** (MITAD_A y MITAD_B no comparten `.git` ni código):
- **MITAD_A** — `witt-organogenesis` → `origin` = `https://github.com/Emma-NukeAI/Witt-organo.git` (PRIVADO).
  **`master` = la última versión** (= `feat/gwt-v1.1-cycle1`). Todo commiteado + pusheado (feat + master, FF),
  working tree limpio (salvo 2 `reports/presentacion-witt-*.html` pre-existentes, no de estas sesiones). **Nunca**
  pushear a `polimat-old`. Cadena de la sesión **2026-07-04/05** (audit total): `66e6afc` (handoff previo) →
  **`ef0fc43`** (sync contratos + doc-coherence gate + no-hang MCP + ADR-0030 compute_ece) → **`afa2a1a`**
  (reporte TYPE D del audit + Test 5 round-2) → **este commit del HANDOFF**. Sesión previa 2026-06-22/23:
  `8ba31a4`→`ad9e102`(ADR-0027)→`bb2671e`/`5782bad`(ADR-0028/0029)→`4c0ea08`→`ba9dddc`(E2E rounds).
  *(`polimat-old` está caído — "Repository not found".)*
- **MITAD_B** — `conciencia-universal` (repo HERMANO en `C:/Users/Emmanuel/dev/conciencia-universal`) → su propio
  remoto privado `https://github.com/Emma-NukeAI/conciencia-universal.git` (génesis `868404a`, `master`).
