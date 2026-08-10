# ADR-0052 — Cola de escritura serializada CROSS-PROCESO + el gate humano deja de firmar a ciegas (bloque 5)

- **Status:** Accepted — bloque 5 del plan webapp ("antes de que M7 tenga botón"), ejecutado 2026-08-10.
- **Relates:** ADR-0045 (rechazo archivado + lock in-process + `actions_log.jsonl` + `created_at`/FIFO — la mitad de este bloque ya entregada), decisión 9-bis del handoff (histórico de cambios a la DI), handoff §5.3/§5.4.
- **Affects:** `rag_index/ingest_service/app.py` (v1.2) + `.gitignore`. **La política de mutación de la DI no cambia** (mismo gate humano, mismo `ingest.py` MERGE-only); cambia la seguridad y la visibilidad del gate.

## Decision

1. **Lock de archivo cross-proceso** (`O_CREAT|O_EXCL`) envolviendo la sección crítica de `/approve` y `/reject`, además del `threading.Lock` de ADR-0045: la *"cola FIFO con concurrencia 1"* prometida es ahora **estructural**, no un artefacto de correr un solo worker de uvicorn. Si el lock no se adquiere en `INGEST_LOCK_TIMEOUT_S` (30s) → **503 honesto** ("write queue busy"), jamás una carrera silenciosa. Un holder muerto no puede atorar el gate: locks con mtime > `INGEST_LOCK_STALE_S` (900s) se toman por relevo.
2. **`GET /pending/{sid}` — la propuesta COMPLETA para el aprobador.** El listado traía 4 campos; aprobar con eso era firmar a ciegas — lo contrario de un gate humano (§5.4). Ahora el aprobador ve `confidence`, `reasoning`, `gap_flags`, `entities_extracted`, `raw_provenance` y la `approval_chain` ANTES de poner su nombre.
3. **`GET /actions` — el read path del histórico 9-bis** (`actions_log.jsonl` de ADR-0045): quién aprobó/rechazó qué, cuándo, con qué outcome (incl. `git_sync`), newest-first. La webapp puede renderizar el registro de cambios a la DI.
4. **El PAT del push-back a git sigue siendo paso de Emmanuel** (es un secreto: fine-grained PAT con `contents:write` sobre `Emma-NukeAI/Witt-organo` → env `GITHUB_TOKEN` del servicio). **Ejercer `/approve` e2e contra el servicio hosted queda gateado por el fundador** — muta la DI real (manifest + Neo4j); se hará con una propuesta chica y su gate explícito, no como smoke.

## Consequences

- M7 puede tener botón: aprobar/rechazar es serializado, con vista completa y con rastro consultable.
- Residual honesto: idempotency-keys formales por request no se implementaron (con 1 admin y respuestas 404-en-duplicado el valor es marginal); si algún día hay N aprobadores, se revisita. El lock es por-host (la realidad del deploy: un contenedor); multi-host requeriría lock en BD.

## Verification (offline, deterministic)

`smoke_ingest_gate.py` → **15/15 PASS** (5 nuevos): detalle completo con chain/provenance/created_at · 404 en sid desconocido · `/actions` con approve+reject newest-first · lock ocupado → 503 · lock stale → takeover y liberación. Neo4j/GitHub stubbeados — cero mutación DI.
