# HANDOFF — GWT v1.1 (handoff único estable · al 2026-06-18)

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

**Código home:** repo PRIVADO `Emma-NukeAI/Witt-organo` (`origin`). `master` = la última versión. **Nunca**
pushear a `polimat-old` (repo viejo). Local se trabaja en `feat/gwt-v1.1-cycle1` (== master).

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

## Archivos clave

| Concern | Archivo |
|---|---|
| Resolver determinista de IDs (anti-fabricación) | `analysis/scripts/lib/resolve_id.py` + `analysis/outputs/verified_identifiers.json`; gate `verify_output.py` |
| Raw store híbrido (MinIO/source-pointer) | `analysis/scripts/lib/raw_store.py` |
| Retrieval semántico (sparse Tfidf + Neo4j vector, RRF); **auto-refresh por mtime** | `analysis/scripts/lib/rag_backend.py` |
| Embeddings + carga a Neo4j; **ensure-index + dim-guard + model-halt + freshness stamp + rebuild sparse** | `rag_index/graphrag/{embeddings,bootstrap,ingest}.py` |
| **Loop (ADR-0022):** drill-a-paper · orquestador con state-machine · propose · prune | `analysis/scripts/lib/{fetch_paper,answer_pipeline,propose_from_external,propose_prune,approve_prune}.py` |
| **MITAD_A R1–R4 (ADR-0023–0026):** loop-regresión · admisibilidad+pureza · gates §4/§11 · esquema WSTS | `substrate_calibration/tools/{replay_and_regress,governance_prefilter,build_regression_cases,accountability_checks,world_state}.py` + extensiones de `verify_output.py`/`ingest.py`/`answer_pipeline.py` |
| Contribución (repo-side): propose → gate humano → ingest | `add_dataset.py` + `approve_dataset.py`; `CONTRIBUTING.md` |
| Chunking de papers/PDFs | `analysis/scripts/lib/chunk_document.py` |
| Liveness NO-SPEND | `rag_index/graphrag/liveness.py` |
| **Tool Universe (Path B) garantizado para el equipo** | `.mcp.json` (raíz, project-scope, `uvx tooluniverse@1.2.6`) + `mcp-config/README.md` |
| Decisiones | `docs/decisions/` (ADR-0020 GraphRAG, 0021 raw store, **0022 answer-pipeline loop**, **0023–0026 MITAD_A R1–R4**, …) |

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

1. **Tool Universe LIVE** end-to-end (reabrir Claude Code, aprobar el MCP; Path B con la amplitud real de Tool Universe vs solo EuropePMC).
2. **Biología más profunda:** `fetch_raw` de expresión para el puente foxc1; Path-B de literatura para osr1/myh9a (siguen sin verificar); suficiencia del conjunto-mínimo → in-silico (Squidiff/Morpheus) o wet-lab.
3. **Crecer corpus/store:** workflow de contribución + los `candidate_store_additions` que el loop surface (genes frecuentes no-en-store → verificar+agregar, gated).
4. **Embed-cache en `ingest.py`** (hoy re-embebe todo; bien con ~27 docs, optimizar cuando crezca).
5. **Diferidos de despliegue:** git push-back (PAT), security hardening de puertos Dokploy, "universe" viz, RIL Cycle 3.
6. **MITAD_B (`conciencia-universal`):** primera corrida **A1** (Proposals de diseño de la Energy Layer); vendorizar los esquemas de objeto del bridge (Case/Proposal/…) al pasar A1→A2; construir el sandbox-validator antes de cualquier A3.
7. **Wiring diferido de MITAD_A:** `compute_ece` por-tier (pendiente hasta acumular records RAW resueltos); emisión nativa del bloque `world_state_transition` por cascade-sim/squidiff; EVPI calibrado (hoy placeholder).

## Gotchas

- Tool Universe MCP no queda activo hasta **reabrir Claude Code + aprobar** el `.mcp.json` (+ `MCP_TIMEOUT` si arranque en frío). El SDK no está en `.venv`.
- Consola Windows = cp1252 → `PYTHONIOENCODING=utf-8` (los scripts ya lo manejan; mojibake en consola, datos utf-8 OK en disco).
- `ingest.py` re-embebe TODO el corpus cada corrida (ok ahora). Los `answer_bundle`/papers crudos viven en `mcp_cache/` (gitignored) — el registro durable son los HTML/JSON commiteados + el código.
- EuropePMC full-text endpoint = `/{PMCID}/fullTextXML` (sin segmento source). `gh` CLI no instalado; usa `git` + REST.

## Estado git

**Dos repos privados, aislados estructuralmente** (MITAD_A y MITAD_B no comparten `.git` ni código):
- **MITAD_A** — `witt-organogenesis` → `origin` = `https://github.com/Emma-NukeAI/Witt-organo.git` (PRIVADO).
  **`master` = la última versión** (= `feat/gwt-v1.1-cycle1`, commit `8ba31a4` con R1–R4 + el análisis concept-bridge).
  Todo commiteado + pusheado (feat + master, FF). **Nunca** pushear a `polimat-old`.
- **MITAD_B** — `conciencia-universal` (repo HERMANO en `C:/Users/Emmanuel/dev/conciencia-universal`) → su propio
  remoto privado `https://github.com/Emma-NukeAI/conciencia-universal.git` (génesis `868404a`, `master`).
