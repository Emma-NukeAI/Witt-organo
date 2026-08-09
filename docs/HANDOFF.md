# HANDOFF — GWT v1.1 (handoff único estable · al 2026-07-21)

> **Siguiente agente:** `CLAUDE.md` se auto-carga (contrato operativo — léelo primero). **Este** es el único
> handoff vigente: estado del sistema, cómo operarlo, decisiones, y qué sigue. Es la fusión de los dos
> handoffs previos (despliegue + sesión del loop); el detalle histórico vive en git.

---

## TL;DR — qué es el sistema hoy

La **DATA INAMOVIBLE** (fuente de verdad compartida del proyecto) está **desplegada y viva** en el Dokploy del
usuario, y es un **sistema que responde preguntas y se refuerza solo**, todo human-gated:

- **Guía:** Neo4j GraphRAG (documents + chunks + embeddings OpenAI 1536-dim + entidades verificadas).
- **Backing:** raw store híbrido — público = source-pointer (URL+sha256, re-descargable); privado/derivado = MinIO.
- **Front door (híbrido, CLI-primario — ADR-0040):** el **CLI `witt-di`** (`rag_index/mcp_server/cli.py`: `query|resolve|fetch|health`) es el front door **robusto** (mismo backend, sin registro por-sesión); el **MCP `data-inamovible`** (`query_data_inamovible` semántico · `resolve_identifier` determinista · `fetch_raw` drill-a-crudo) es el enhancement agent-native, **read-only**. Ambos hablan al mismo `rag_backend`. Todo resultado lleva un marcador `degraded` — nunca sparse-disfrazado-de-semántico.
- **Loop auto-reforzante (ADR-0022):** `Path A (DI) → si insuficiente → Path B (EuropePMC / Tool Universe) → composite-auditor ≥3 → propose → GATE HUMANO → re-ingesta`. "No está en la DI" **no es stopper** — es disparador de aprendizaje. El store **crece con el uso**.

**Código home:** repo PRIVADO `Emma-NukeAI/Witt-organo` (`origin`). `master` = la última versión (**sesión 2026-07-19**, commit `aa4a61e`; ver §Estado git).
**Nunca** pushear a `polimat-old` (repo viejo, además caído). Local se trabaja en `feat/gwt-v1.1-cycle1` (== master).

**Sesiones 2026-07-20/21 (posteriores al cuerpo de este handoff; detalle en git + ADR-0041/0042):** re-ingest human-gated que materializó `tier`/`tier_weight` en el grafo + registro del feeder EuropePMC (ADR-0041); primer record RN3 (CORPUS-2026-0004) + colocación de datos relacionales bajo RN11 + crecimiento del corpus a 7+ records y del store **74→113** (GATE-2 para el stress-bank de MITAD_B + barrido S4 multi-paper CORPUS-2026-0005..0008, todo human-gated, ADR-0042). El estado vivo del store es SIEMPRE `analysis/outputs/verified_identifiers.json` (`store_version 2026-07-21.3`, **113 records**); los conteos citados en las secciones de abajo son históricos de cada sesión, no el estado actual.

**Última sesión documentada en el cuerpo (2026-07-18/19) — ver la sección nueva abajo:** (a) **banco de calibración v1** (07-18): 30 preguntas para que 4 médicos de Latido califiquen DOS ejes — input (objetividad/contexto/especificidad de las *preguntas*) y output (correcta-útil / usarías la *respuesta*); CSV→Google Sheets + `score_calibration.py` determinista, scoring a ciegas. Es el **gold-set humano** (el limitante real que ningún LLM/compute sustituye). (b) **data-inamovible MCP portable/reproducible** (ADR-0039: `uv run --locked` + `uv.lock`, cierra la causa raíz "intérprete sin neo4j") → **auditoría de perfección** (13-agente CoVe/composite-auditor) + **hardening** (ADR-0040): **marcador de degradación in-band** (cierra el sparse-disfrazado-de-semántico — el modo de fallo del incidente), **gate humano ESTRUCTURAL** (`is_approved`), `bge→openai` default en escritura, guardrail anti-contaminación del `.venv`, y **CLI `witt-di`** como front door robusto (**híbrido, CLI-primario**; el MCP sigue read-only, enhancement opcional). (c) **acceso del equipo (Opción A)**: `.secrets/deploy.env` local con **credencial compartida**, distribuido por Drive + `GUIA_MEDICOS.md` (guía + prompt para pegar); Opción B (MCP remoto hosted, bearer por médico — factible sin OAuth) **diferida**. Validado **read-only, 0 mutación**: DI sweep 20/20 · MCP handshake real 5/5 (semantic 0.804) · smoke 6/6. Pusheado a `master` FF (`aa4a61e`).

**Sesión previa (2026-07-11) — ver la sección abajo:** primer **baseline held-out A1** medido + estudio del **fallback Tool Universe** + loop de re-ingesta + auto-auditoría de cierre. Titulares (todos con disciplina de honestidad — "medido + auditado-y-corregido", NO "validado"): Test 3 scaffold→**medido** (30/30), Test 4 degenerado→**no-degenerado** (n=20 corregido, ECE_raw 0.51); **Level-2 = tool-use estructurado de Tool Universe es el lever** del fallback (no la literatura), señal en n=6 favorable; **DATA INAMOVIBLE 51→74** human-gated (ADR-0035, +23 IDs cascada de inducción re-verificados vs Ensembl); gate `verify_output` gana `reingest_candidate` (ADR-0036); **composite-audit de cierre → 7/7 REVISE** (atrapó un bug real del parser + overclaims sistemáticos, todo corregido, ADR-0037); **paquete de honestidad** (ADR-0038): juez **cross-proveedor OpenAI/gpt-4o**, fix judge-fabrication, deterministic-first. La insuficiencia de la DI se decide por **umbral de confianza** (no estructural, no gate humano; el gate humano vive en la re-ingesta).

**Sesión previa (2026-07-04/05) — ver la sección más abajo:** **auditoría de funcionalidad TOTAL** +
composite-auditor (3 auditores adversariales Opus). Se probó la maquinaria offline + en vivo (Neo4j retrieval,
ambas ramas del `answer_pipeline`, Path B Reactome, MinIO round-trip, sandbox DI mutation, squidiff Mode 0,
human gate del ingest_service). Entregables: **sync de contratos** (CLAUDE/SCOPE/README a la realidad) +
**gate anti-drift** `doc_coherence_check.py` + `smoke_contract.py` (30 offline / 34 live PASS) + **regla no-hang
MCP** (§6) + allowlist MCP + **ADR-0030** (`compute_ece` "satisfied"→"aggregate-captured", disciplina ADR-0005) +
Test 5 cross-field round-2 (case-capture). Veredicto: **APPROVE_MINOR** sobre "la maquinaria funciona como se
documenta"; **REVISE** sobre "totalidad" (cerrado en su mayoría; residuales abajo). El panel atrapó 2 over-claims
del operador — corregidos. **Cero mutación de la DATA INAMOVIBLE** (todo read-and-report / sandbox). Cierre:
**auditor externo Fable 5** (sin flag) + sus 5 recomendaciones implementadas (**ADR-0031..0034**; 0033 seguridad
**DIFERIDA** por decisión del founder) + panel **multi-familia** (Opus+Fable+Sonnet) + 2 herramientas de medición
(`retrieval_eval.py` recall@k scaffold, `store_integrity_scan.py` 51 CLEAN).

**Sesión previa (2026-06-22/23) — ver las 2 secciones más abajo:** MITAD_A **endurecida** tras validación
adversarial (ADR-0027: binding símbolo↔ENSDARG, gates §4/§11 reforzados) + **guard de validez-de-lente**
(ADR-0028) + la **DATA INAMOVIBLE creció 46→51** human-gated (ADR-0029) + **test E2E** (3 rounds, pronefros).

---

## data-inamovible team-ready: MCP portable + auditoría de perfección + acceso del equipo (sesión 2026-07-18/19)

### Banco de calibración v1 (2026-07-18)
30 preguntas para que **4 médicos de Latido** califiquen DOS ejes a ciegas: **input** (¿la pregunta es objetiva / tiene contexto / es específica?) y **output** (¿la respuesta es correcta-útil? ¿la usarías?). CSV → Google Sheets; scoring **determinista** con `score_calibration.py` (NO LLM). Respuestas híbridas (GoldSet + re-corridas Level-2 + baseline). Es el **ancla de verdad de tierra** que la sesión 07-11 marcó como EL limitante — ningún LLM-juez lo sustituye. (Artefactos en `evaluation/gold_set/`, `evaluation/scripts/`, `evaluation/workflows/banco_reframe.js`; ver memoria `banco-calibracion-v1`.)

### Incidente + recuperación del `.venv` (2026-07-19)
Tras reiniciar el cliente, el MCP **NO** tomó el `.mcp.json` versionado: un `claude.exe` viejo lo servía por config inline venv-python, y **esta sesión tuvo cero tools `data-inamovible` registradas** (fallo silencioso del registro por-sesión). Un `uv run --locked` diagnóstico chocó con el server vivo (locks del `.venv`) y **rompió el venv**. Causa raíz del drift: alguien hizo **`uv pip install tooluniverse` DENTRO del `.venv`** del server (~143 pkgs ajenos; ToolUniverse debe correr por `uvx`). Recuperado a 69 pkgs pristinos lock-matched (smoke 6/6). → gatilló el guardrail + la auditoría.

### ADR-0039 — MCP portable/reproducible (base, misma fecha)
Lanzado por `uv run --locked python rag_index/mcp_server/server.py` desde el `.mcp.json` **versionado** + `pyproject.toml`/`uv.lock` (mcp/neo4j/openai/scikit-learn/numpy/fastembed/minio). Cierra estructuralmente "intérprete sin neo4j". Gate `smoke_rag.py` **6/6** (venv vivo Y env limpio `uv run --locked`). Onboarding `rag_index/mcp_server/README.md` + `deploy.env.example`.

### Auditoría de perfección (13-agente CoVe) + hardening (ADR-0040)
El repo ahora es **compartido con Latido** (médicos no-técnicos) → debe funcionar impecable. Composite-auditor / Chain-of-Verification, **13 agentes** (6 pilares × audit + verify adversarial + síntesis), 0 errores. Hallazgos → fixes shipeados (`b902e1f`+`aa4a61e`):
- **Marcador de degradación in-band** (`rag_backend.HitList.degraded`; `server._query` + `witt-di` lo surfacean). `HybridRetriever` ya NO traga el fallo del denso con `except: pass`. Cierra el **sparse-disfrazado-de-semántico** — el modo de fallo del incidente 07-18/19.
- **Gate humano ESTRUCTURAL** (`rag_backend.is_approved()`): `gather_documents()` + el loop de entidades de `ingest.py` saltan records con `approval_chain` no-`approved` (default-deny). Antes era procedural (dependía del orden de comandos); ahora lo impone el código.
- **`bge→openai` default en las rutas de ESCRITURA** (`ingest.py`/`bootstrap.py`) cuando hay `NEO4J_URI` → un rebuild fresco no puede crear un índice 768-dim contra el query path OpenAI/1536.
- **Guardrail anti-contaminación del venv**: `skills/external/README.md` (uvx-only) + WARN en `smoke_rag.py`.
- **CLI `witt-di`** (`rag_index/mcp_server/cli.py`, NUEVO): `query|resolve|fetch|health`, mismo backend + garantía §6 no-hang, exit 3 si degrada. **Decisión MCP-vs-CLI = híbrido, CLI-primario**: el MCP no es hazard de datos (read-only, gate no evadible) sino de **confiabilidad** (registro por-sesión que falla en silencio, staleness del pipe stdio); el transporte es ortogonal a la calidad densa. **El MCP queda read-only** — la mutación NO se expuso como tool MCP (Opción B no se construyó).

Validado **read-only, cero mutación de la DI**: complete DI sweep **20/20** (embedding 1536 query=ingest=índice · query/degraded/sparse · resolve ± · fetch ± · gate estructural · guards de ingest · **índice Neo4j ONLINE 1536, docs=27**) · MCP handshake real por `uv run --locked` **5/5** (semantic 0.804) · `smoke_rag.py` **6/6** · marker unit **4/4** · gate estructural **9/9** · `witt-di` e2e (degradación forzada → exit 3). Reporte `reports/2026-07-19_data-inamovible-mcp-perfection-audit_v1.html`.

### Acceso del equipo de Latido (Opción A — ADR-0040)
Los médicos son parte del loop (preguntan + califican + **son el gate humano** de la ingesta), así que necesitan **paridad total** con el founder (query/resolve/fetch/ingest), no un portal recortado. Modelo elegido: **`.secrets/deploy.env` local con credencial COMPARTIDA**, distribuido por el Drive del equipo (archivo suelto `deploy.env` + ZIP limpio del repo) + **`GUIA_MEDICOS.md`** (guía de 4 pasos + un prompt para pegar en Claude Code que instala `uv`, coloca las llaves y corre el smoke). Claude Code es el cliente. **Opción B** (MCP remoto hosted, secretos server-side, **bearer token por médico** — verificado factible SIN servidor OAuth, Streamable HTTP) considerada y **DIFERIDA** (sobre-ingeniería para 4 de confianza; backend idéntico → migrar luego sin rehacer). Residual honesto: credencial compartida = sprawl en ≤4 laptops + revocación gruesa (aceptado a esta escala; restringir el Drive a los 4 por correo). Diagrama: `reports/2026-07-19_data-inamovible-acceso-equipo-arquitectura_v1.html`.

**Lecciones para el próximo agente:** (a) el marcador `degraded` es la defensa estructural contra el sparse-silencioso — cualquier consumidor nuevo debe surfacearlo. (b) **NUNCA `uv pip install` en el `.venv` del MCP** (usa `uvx`); el smoke avisa. (c) el MCP puede quedar sin registrar en una sesión **sin error** — por eso el CLI es el front door primario. (d) el **gold-set humano** (banco de calibración) es la próxima inversión de mayor valor, no más instrumentación (ADR-0034 + review Fable-5).

---

## Held-out baseline + Tool Universe fallback + cierre auto-auditado (sesión 2026-07-11)

Ciclo "medir para validar" (Track A del roadmap `~/.claude/plans/`). Todo commiteado + **pusheado** (feat + master `7d43c94`). **Disciplina clave:** todos los titulares quedaron en **"medido + auditado-y-corregido", NO "validado"** — la auditoría de cierre lo forzó.

- **A1 — baseline held-out `month_0`** (`evaluation/run_held_out.py`, NUEVO — pipeline 3 etapas: recuperar `answer_pipeline` → sintetizar §5 vía **Anthropic API urllib** (sin SDK) → puntuar). Test 3 scaffold→**medido** (30/30 respondidas, EPS real axes a/b + axis c semántico bge). Test 4 degenerado→**no-degenerado**. **OJO (bug corregido):** el parser filtró 8/30 `confidence` como texto en `direct_answer` → `compute_ece` los tiró; **corregido** (`_recover_leaked_confidence`) → n=20, accuracy 0.85, ECE_raw 0.51, 3 negativos (`reports/ece_month0_corrected_20260711.json` supersede al buggy). `EMBED_MODEL=openai` forzado en backend neo4j (índice 1536; si no, degrada silenciosamente a sparse).
- **Fallback Tool Universe (3 niveles):** DI-only vs **DI+TU-Level-1 (literatura)** vs **DI+TU-Level-2 (tool-use estructurado agéntico)**. L1 no mueve la aguja (indistinguible de cero); **Level-2 es el lever** (agente ejecuta ensembl/reactome/zfin vía MCP) — señal fuerte pero en **n=6 pre-seleccionado favorable** (case-capture, no las 30). Level-2 corre como **workflow** (`evaluation/workflows/level2_tooluniverse_fallback.js`). Insuficiencia = **umbral de confianza** (el estructural se engaña — Q07). MCP Tool Universe **verificado vivo** (2223 tools).
- **DATA INAMOVIBLE 51→74 (ADR-0035, HUMAN-GATED):** +23 IDs de la cascada de inducción (BMP/Nodal/RA/Wnt/FGF/Hox/paralogs), cada ENSDARG **re-verificado independientemente vs Ensembl** (23/23 MATCH, raw §7.9 `mcp_cache/raw_ensembl_l2-candidates_20260711.json`), vía el escritor único; snapshot `verified_identifiers.v2026-06-23.1.json`. `store_integrity_scan` CLEAN.
- **`verify_output` gana `reingest_candidate` (ADR-0036):** un ID out-of-store PERO respaldado por crudo §7.9 = candidato a re-ingesta (admisible, surfaced), NO fabricación. Default (`reingest_cache=None`) = veredicto pass/fail idéntico al previo.
- **Composite-audit de cierre (ADR-0037) — el gate hizo su trabajo:** 7 claims × 3 auditores adversariales (Opus/Sonnet/Haiku) → **7/7 REVISE, 0 CONFIRMED**. Atrapó el bug del parser (arriba) + overclaims sistemáticos que mi auto-revisión NO vio (confirma §7: la auto-auditoría NO es gate). Todos los titulares caminados hacia atrás. Reporte `reports/2026-07-11_closing-composite-audit_retrospective.html` + verdicts JSON.
- **Paquete de honestidad (ADR-0038):** (1) juez **cross-PROVEEDOR OpenAI/gpt-4o** (`openai_verdict()`, usa la `OPENAI_API_KEY` de embeddings) — el "34% divergencia within-Anthropic" era ruido de tier, no independencia; GPT concuerda 5/6 con la mayoría Anthropic > within-Anthropic 3/6. (2) **fix judge-fabrication**: al juez se le pasa el check determinista + se le prohíbe fingir verificación (antes fabricaba "verifiqué vs Ensembl"). (3) **deterministic-first**: `record.scoring.primary_signal` = store-grounded vs llm-judge-advisory.

**Lecciones para el próximo agente (CRÍTICAS):** (a) **LLM-juez ≠ verdad de tierra** — toda métrica de "calidad" esta sesión es LLM-juez, n chico, single-snapshot; no citar como validación. (b) `claude-fable-5` **rechaza tool-calls forzados** → panel Opus+Sonnet+Haiku+gpt-4o. (c) el composite-auditor atrapa un over-claim CADA vez, incl. del operador — no cometer el error de leer "medido" como "validado".

**Lo que sigue (del propio auditor; NO hecho):** (1) **gold set calificado por experto humano** (Martín) para preguntas de razonamiento abierto — el ancla de verdad de tierra que ningún LLM/compute sustituye; es EL limitante. (2) arreglar del todo el judge-fabrication (juez con verificación real). (3) escalar Level-2 a las 30 (~7M tokens). (4) autenticar la provenance por-binding (límite ADR-0036). (5) A3 del roadmap: re-correr `rolling_calibration`/`retrospect` (RIL stale desde 2026-06-11) + cerrar la propuesta de gobernanza abierta. **Recomendación de cierre:** el harness de eval está en punto sólido; la próxima inversión grande va a la biología (wet-lab GOF Fase II) o al gold set humano, no a más instrumentación (ADR-0034 + review Fable-5: no sobre-construir el substrato).

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

### Auditor externo Fable 5 + respuesta a sus 5 recomendaciones (2026-07-05)

Se armó un **brief neutral** (`docs/EXTERNAL_AUDIT_BRIEF.md`) — descripción del proyecto en lenguaje técnico-profesional para que un auditor externo lo revisara **sin flag**. Se corrió un agente **Fable 5** con solo ese brief (no el repo): **no se flageó** y dio una review candid (`docs/EXTERNAL_AUDIT_FABLE5_REVIEW.md`). Veredicto: diseño disciplinado, pero *"accountability layer alrededor de un resultado científico que aún no existe"* — el problema es **proporcionalidad** y **falta de medición** de que la maquinaria mejore respuestas.

Sus 5 recomendaciones → implementadas (ADR-0031..0034):
1. **Medir los controles** → `substrate_calibration/tools/retrieval_eval.py` (recall@k known-item; primera corrida recall@1=recall@5=MRR=1.0 en **solo 3 probes = SCAFFOLD**) + `store_integrity_scan.py` (**51 records CLEAN**). Calibración n=10 (chico). **ADR-0032.**
2. **Independencia de revisores** → **ADR-0031**: paneles composite-auditor mezclan familias (Claude Opus/Sonnet/Haiku + **Fable**). Demostrado con panel Opus+Fable+Sonnet (unánime **APPROVE_MINOR** 0.78/0.72/0.68); desacuerdo logueado (`substrate_calibration/records/panel_multifamily_20260705.json`). **Sonnet capturó un concern que Opus+Fable no** → evidencia empírica de la diversidad de familias. **Límite honesto: solo 2 familias reales (no un 3er proveedor).**
3. **Security hardening** → **ADR-0033 = Proposed, DEFERRED, SIN ACCIÓN** (dirección del founder 2026-07-05: "no le hagamos ningún cambio" a la DATA INAMOVIBLE). Hallazgo parqueado; nada tocado.
4. **Freeze del substrate** → **ADR-0034** (Accepted): ningún subsistema nuevo hasta que cada control feature-weight demuestre haber atrapado un error real; safety spine exenta; esfuerzo → medir + biología.
5. **Error-en-store** → `store_integrity_scan.py` (dup/colisión ENSDARG/malformado/provenance/staleness; read-and-report, propone, nunca auto-fix).

**Segundo pase (panel multi-familia, con los números reales): unánime APPROVE_MINOR.** Concerns honestos vigentes: medición estadísticamente fina (por diseño, ADR-0034) y garantía "inamovible" condicional hasta el hardening (diferido, ADR-0033).

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
| Retrieval semántico (sparse Tfidf + Neo4j vector, RRF); **auto-refresh por mtime**; **`HitList.degraded` (marcador in-band, ADR-0040)** + **`is_approved()` (gate humano estructural)** | `analysis/scripts/lib/rag_backend.py` |
| **Front door (híbrido, CLI-primario, ADR-0040):** CLI robusto `witt-di` · MCP read-only opcional · gate `smoke_rag.py` 6/6 | `rag_index/mcp_server/{cli.py,server.py,smoke_rag.py}` (lanzado por `uv run --locked`, ADR-0039) |
| **Onboarding equipo Latido (no-técnico):** guía 4 pasos + prompt para pegar; acceso `.secrets` local credencial compartida (ADR-0040) | `GUIA_MEDICOS.md` (técnico/dev: `ONBOARDING.md`) |
| Embeddings + carga a Neo4j; **ensure-index + dim-guard + model-halt + freshness stamp + rebuild sparse** | `rag_index/graphrag/{embeddings,bootstrap,ingest}.py` |
| **Loop (ADR-0022):** drill-a-paper · orquestador con state-machine · propose · prune | `analysis/scripts/lib/{fetch_paper,answer_pipeline,propose_from_external,propose_prune,approve_prune}.py` |
| **MITAD_A R1–R4 (ADR-0023–0026):** loop-regresión · admisibilidad+pureza · gates §4/§11 · esquema WSTS | `substrate_calibration/tools/{replay_and_regress,governance_prefilter,build_regression_cases,accountability_checks,world_state}.py` + extensiones de `verify_output.py`/`ingest.py`/`answer_pipeline.py` |
| **MITAD_A hardening + guard (ADR-0027/0028):** binding símbolo↔ENSDARG · gates §4/§11 endurecidos · validez-de-lente | `verify_output.py` (N1/N2) · `accountability_checks.py` (W1/W2/N3/N6) · `world_state.py` (W5) · `build_regression_cases.py` (W3) · `substrate_calibration/tools/{evidence_weighting,smoke_adr0027_hardening}.py` |
| **Lentes zebrafish (custom Tool Universe workspace):** perturbación nativa ZFIN · literatura EuropePMC | `.tooluniverse/tools/{zfin_zebrafish,europepmc_literature}.py` (+ `profile.yaml`) |
| Contribución (repo-side): propose → gate humano → ingest | `add_dataset.py` + `approve_dataset.py`; `CONTRIBUTING.md` |
| Chunking de papers/PDFs | `analysis/scripts/lib/chunk_document.py` |
| Liveness NO-SPEND | `rag_index/graphrag/liveness.py` |
| **Tool Universe (Path B) garantizado para el equipo** | `.mcp.json` (raíz, project-scope, `uvx tooluniverse@1.2.6`) + `mcp-config/README.md` |
| Decisiones | `docs/decisions/` (ADR-0020 GraphRAG, 0021 raw store, **0022 answer-pipeline loop**, **0023–0026 MITAD_A R1–R4**, **0027 detection-hardening**, **0028 lens-validity guard**, **0029 DI signaling-add**, 0030–0034 (audit total + review externa Fable-5), **0035 DI+23 IDs**, 0036–0038 (gate reingest + closing-audit + honesty bundle), **0039 MCP portable (`uv.lock`)**, **0040 audit de perfección + CLI `witt-di` + acceso equipo**) |

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
  **`master` = la última versión**, ahora en **`aa4a61e`** (sesión 2026-07-19). Se trabaja en la rama
  `fix/data-inamovible-mcp-venv-portable` y se hizo **FF push a `master`** (`2c81dd4..aa4a61e`). **Nunca** pushear a `polimat-old`.
  Cadena **2026-07-18/19** (banco calibración + data-inamovible team-ready): `69e49a2` (handoff 07-11) →
  `2c81dd4` (RIL hygiene A3) → `95c54af` (**ADR-0039** MCP portable `uv run --locked` + `uv.lock`) →
  `d261a96` (MAX_PATH doc) → `b902e1f` (**ADR-0040** hardening: marcador degradación + `bge→openai` + guardrail venv + CLI `witt-di`) →
  **`aa4a61e`** (ADR-0040 gate estructural `is_approved` + README autocontenido). Docs al día de esta sesión
  (ADR-0040, HANDOFF/CLAUDE.md/PROJECT_SCOPE, `GUIA_MEDICOS.md`) commiteadas aparte. **Untracked (NO pusheados),
  revisar sin prisa:** artefactos del banco `evaluation/{gold_set,scripts,workflows/banco_reframe.js}` +
  reports `2026-07-{11,18,19}_*.html` (incl. la auditoría de perfección + el diagrama de arquitectura de hoy).
  Cadena previa **2026-07-11** (held-out + Tool Universe fallback + cierre auto-auditado): `75c11bb`
  (A1 baseline) → `3ed5c83` (DI+TU L1) → `76f3d62` (Level-2) → `50f97ff` (ADR-0035 DI 51→74) → `13910cb`
  (ADR-0036 gate) → `4363b24` (ADR-0037 closing audit + correcciones) → **`7d43c94`** (ADR-0038 honesty bundle).
  Sesión previa **2026-07-04/05** (audit total + review externa): `66e6afc`→`ef0fc43`→`afa2a1a`→`5b919a1`→
  `1ffe513`→`60e09b1`→`a28a149`. Previa 2026-06-22/23: `8ba31a4`→`ad9e102`→`bb2671e`/`5782bad`→`ba9dddc`.
  *(`polimat-old` está caído — "Repository not found".)*
- **MITAD_B** — `conciencia-universal` (repo HERMANO en `C:/Users/Emmanuel/dev/conciencia-universal`) → su propio
  remoto privado `https://github.com/Emma-NukeAI/conciencia-universal.git` (génesis `868404a`, `master`).
