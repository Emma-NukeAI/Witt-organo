# ADR-0054 — Estreno e2e del gate hosted (push-back funcionando), el PRIMER prune human-gated, y el estado del gate al volumen

- **Status:** Accepted — gate humano ejercido por Emmanuel en vivo, 2026-08-10 (submit/reject/approve: "by Emmanuel"; prune: *"Adelante con la propuesta del prune"* tras especificación exacta previa a toda escritura, per ADR-0022).
- **Relates:** ADR-0045/0052 (el gate reformado que se estrenó), ADR-0022 (mutaciones DI human-gated + prune como propuesta), ADR-0050/0051 (la corrida #1 cuyo hueco motivó el registro ingestado), `docs/findings/2026-08-10-ingest-e2e-estreno-y-hallazgos.md` (detalle).
- **Affects:** DATA INAMOVIBLE (**+1 registro neto**: `CORPUS-2026-0009`; duplicado `0010` pruneado) · `rag_index/ingest_service/docker-compose.ingest.yml` (volumen `/data` completo + 4 rutas versionadas).

## Decisions / hechos registrados

1. **El ciclo completo del gate hosted quedó ejercido y funciona**: submit → vista completa → reject con razón → approve → manifest + Neo4j + **push-back a git** (primeros commits autónomos del servicio: `370b809`, `2718a33`). La DI ganó `CORPUS-2026-0009` (Perner 2007, PMID:17651719 verificado en vivo + crudo §7.9, RN11) — la evidencia funcional wt1a↔pronefros que la corrida #1 identificó como faltante.
2. **Primer prune human-gated ejecutado** (duplicado `CORPUS-2026-0010`, producto de la carrera de swap del autodeploy): detección → spec exacta → gate → `DETACH DELETE` de 1 nodo + 1 arista (`Document` 35→34) → manifest 10→9 → verificación (0009 intacto). El patrón "prune = propuesta, jamás automático" pasó de regla escrita a operación ejercida.
3. **Todo el estado del gate vive en el volumen** (fix del hallazgo de config): `ingest_queue:/data` + `INGEST_QUEUE_DIR/REJECTED_DIR/ACTIONS_LOG/LOCK_FILE` versionados en el compose — un redeploy ya no puede borrar la cola, el archivo de rechazos ni el histórico 9-bis.
4. **Reglas de operación nuevas** (hallazgos 2 y 3): configurar **Watch Paths** en Dokploy (solo cambios del propio servicio lo reconstruyen; ídem query service) y **verificar el rastro durable (git/Neo4j) antes de reintentar una mutación** que aparentó fallar — el push-back existe para eso.

## Consequences

- El flujo que usarán los médicos (CONTRIBUTING/GUIA) está validado en producción, incluida la corrección de una clasificación errónea por el humano (RN4→RN11) — el gate con vista de ADR-0052 demostró su valor en su primer uso real.
- Residual: el rechazo del paso intermedio (sid `15715bd63e2b`) se perdió con el redeploy (era pre-fix del volumen) — su registro es este ADR + el findings doc; los rechazos futuros sobreviven.
- El `documents.jsonl` del repo queda desincronizado del grafo por diseño (el contenedor regenera el suyo desde el manifest); el rebuild local corre cuando el dev lo necesite.

## Verification

Post-prune, en vivo (read-only): `Document` = **34**, `CORPUS-2026-0009` presente con 1 arista IN_NICHE→RN11, `CORPUS-2026-0010` ausente; manifest en git = **9 records** con `status` explicando el prune; store de identificadores **113 sin cambio**.
