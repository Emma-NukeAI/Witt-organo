# Finding — Estreno e2e del gate de ingesta hosted: el ciclo funciona; 3 hallazgos accionables + el primer prune human-gated

**Fecha:** 2026-08-10 · **Operadores:** Emmanuel (gate) + agente (spec/verificación) · **ADR:** 0054

## Qué se probó (y funcionó)

Primer ejercicio de punta a punta contra el servicio de ingesta hosted, con mutación REAL de la DATA
INAMOVIBLE: `/submit` (source-pointer al REST de Europe PMC, PMID:17651719 verificado en vivo, crudo
§7.9 en `mcp_cache/raw_europepmc_PMID17651719_core_20260810.json`) → **gate con vista** (`/pending/{sid}`)
→ `/reject` con autor+razón → re-submit corregido → `/approve` → manifest + Neo4j (+1 Document, embedding
1536) + **estreno del push-back a git** (commits autónomos del servicio, autor `Emma-NukeAI`). El registro
canónico quedó como **CORPUS-2026-0009** (Perner 2007, RN11) — exactamente la evidencia funcional
wt1a↔pronefros cuya ausencia hizo declinar a la corrida #1 (`a361f566`).

## Hallazgo 1 — El gate con vista atrapó al clasificador (working-as-intended)

`corpus_classifier` v1 propuso **RN4** (microambiente bioquímico) para un paper de literatura funcional
curada (**RN11**). El aprobador lo vio en `/pending/{sid}` ANTES de firmar y lo rechazó con razón. Un
gate ciego (los 4 campos del listado) lo habría firmado. Validación directa de ADR-0052.

## Hallazgo 2 — Swap de contenedor a media operación del gate → duplicado

El autodeploy On-Push reconstruyó el servicio ENTRE el submit y el approve. El approve aparentó fallar
(404 en el contenedor nuevo, cola vacía) pero un reintento aterrizó en el contenedor viejo aún vivo →
`CORPUS-2026-0009` (19:30Z). El re-submit+approve posterior creó el duplicado `CORPUS-2026-0010` (19:36Z).
**Mitigación:** (a) Watch Paths en Dokploy para que solo cambios del propio servicio lo reconstruyan;
(b) regla de operación: no ejercer el gate con un deploy en vuelo (ver Deployments antes).

## Hallazgo 3 — Lección de proceso: verificar el registro DURABLE antes de reintentar una mutación

El agente aconsejó re-someter+aprobar tras el 404 sin consultar `git log` — y el push-back existe
exactamente para que el resultado de una mutación sea verificable. **Regla nueva:** ante un fallo ambiguo
de una operación que muta la DI, verificar primero el rastro durable (commits del servicio en git,
conteos de Neo4j) y solo entonces reintentar. (El duplicado fue el costo de no hacerlo: benigno aquí,
pero la clase de error es la que rompe inamovibilidad.)

## Hallazgo (config) — Estado del gate fuera del volumen

El compose montaba SOLO `/data/queue`; el archivo de rechazos, el `actions_log.jsonl` (histórico 9-bis) y
el lockfile vivían en el filesystem del contenedor → el redeploy borró el rechazo registrado del paso 2.
**Fix aplicado (ADR-0054):** el volumen monta `/data` completo y las cuatro rutas van versionadas en el
compose.

## El primer prune human-gated del sistema

Detección → propuesta con especificación exacta → **"Adelante" de Emmanuel** → ejecución → verificación:
`MATCH (d:Document {doc_id:'CORPUS-2026-0010'}) DETACH DELETE d` (1 nodo, 1 arista IN_NICHE) — `Document`
35→34, `CORPUS-2026-0009` intacto (1 arista) · manifest 10→9 records + `status` explicando el prune ·
`documents.jsonl` del repo sin cambio (no contenía el registro). El patrón ADR-0022 (prune = propuesta
gateada, jamás automático) quedó **ejercido por primera vez**, no solo escrito.
