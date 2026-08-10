# ADR-0050 — Modelo de corrida + bitácora única de eventos + registro congelado persistido en el backend

- **Status:** Accepted — bloque 3 del plan webapp, ejecutado 2026-08-09/10 bajo ADR-0047 (decisión 2: el backend persiste, la webapp solo lee) y ADR-0049 (auditoría 100%).
- **Relates:** ADR-0048 (el query_service que hospeda esto), ADR-0043/0044 (sobre + identidad de bundle), ADR-0046 (el registro congelado como rastro de auditoría), §2.1/§2.2/§5.6 del handoff webapp (`witt-ui-lab/05-backend/faltantes-backend.md`).
- **Affects:** `rag_index/query_service/` (`db.py` +tablas `runs`/`run_events`, **NUEVO** `runs.py`, `app.py` +7 endpoints, compose +`ANTHROPIC_API_KEY`/`WITT_RUN_WORKERS`) · `analysis/scripts/lib/answer_pipeline.py` (+hook `on_stage`). **Cero mutación de la DATA INAMOVIBLE** (las corridas leen la DI y escriben solo en la BD del backend + `mcp_cache` gitignored; la evidencia externa aprobada sigue entrando a la DI únicamente por el gate humano de ingesta).

## Context

No existía modelo de corrida (`retrieve()` era síncrono, sin `run_id` persistente, sin cola, sin cancelación), ni stream de eventos (solo líneas de texto en un log de archivo del server), ni persistencia del veredicto. El consumidor real (`run_held_out.py`) **saltaba** la máquina de estados re-armando su propio bundle — por eso los ~30 registros históricos no tienen `decision_state` (§5.6). Y sin latido, una corrida atorada 1800s (el deadlock de sklearn) era indistinguible de una trabajando.

## Decision

1. **Estados de corrida:** `queued → running → awaiting_closure → closed`, con `failed` y **`cancelled` como terminal de primera clase** (un cancelado que se ve como muerto miente sobre el sistema). `planning` (el Plan de M3) queda para el bloque del planner. **Cierre explícito** (`POST /runs/{id}/close`): congela el registro (`frozen_at`, `closed_by`) — semilla del requisito "cierre para ser precedente"; las mediciones se congelan ahí, `ratings[]` (bloque futuro) crece append-only después.
2. **Una sola máquina de estados, instrumentada — nunca re-armada:** `answer_pipeline.retrieve()` gana el hook opcional `on_stage(name, payload)` (aditivo). El worker emite eventos DESDE el pipeline real; el anti-patrón §5.6 (re-ensamblar el bundle por fuera) queda estructuralmente innecesario.
3. **Una bitácora, dos lectores:** los eventos viven en la tabla `run_events` (`{run_id, seq monotónico, ts, type, agent, tool, level, degraded, payload}` — el estado epistémico viaja EN el evento). El **replay** (`GET /runs/{id}/events?after=`) y la **traza viva** (`GET /runs/{id}/stream`, SSE con keep-alive) leen las MISMAS filas en el MISMO orden — no pueden contradecirse. Sobreviven al contenedor (Postgres, no filesystem).
4. **Latido:** `last_event_at` se refresca con cada evento; la API expone `heartbeat_age_s` + `heartbeat_stale` (umbral `WITT_HEARTBEAT_STALE_SECONDS`, default 300) — "sin evento hace N min" distingue una corrida trabajando de una atorada.
5. **Cancelación:** flag (`cancel_requested`) chequeado en cada frontera de etapa; un run `queued` cancela inmediato. La corrida cancelada termina `cancelled`, jamás disfrazada de `failed`.
6. **Pipeline de ejecución** (worker in-process, `WITT_RUN_WORKERS` default 2, arranca DESPUÉS del preload de sklearn en main thread): retrieve (instrumentado) → **síntesis v1** single-pass (`claude-opus-4-8`, tool forzado `emit_answer`; el delta de dos pasadas es bloque 4) → **gate determinista** `verify_output.admissible` (resultados entregados al panel — ADR-0038) → **composite-audit** (ADR-0049, 100%) → terminal → **registro congelado** persistido (`render_contract_version`, `measured_at`, `store_at_retrieval {store_version, index_version}`, `retrieval_summary`, `decision_state`, `audit` con la tabla del panel, `answer`, `deterministic_checks`, `usage` síntesis+panel, `bundle_identity`, `question_matches_run`). **Una identidad de punta a punta:** el `run_id` de la cola ES el del bundle (re-estampado ADR-0044).
7. **Gasto por corrida** (autorizado, medido, sin caps — ADR-0047 d.3): 1 embed (path_a) + 1 síntesis (opus) + panel de 4 (~1–2.50 USD). El `usage` crudo queda en el registro congelado — semilla de la contabilidad de tokens del bloque 4.

## Consequences

- M3 (traza viva) y M6 (bitácora/replay) de la UI leen el mismo log por construcción; el recuadro de auditoría (M4) tiene contenido real por primera vez.
- La autoridad del gate de auditoría vive en el backend (Postgres), como decidió ADR-0047 — la webapp renderiza `GET /runs/{id}/record`.
- Residuales honestos → bloques 4+: dos pasadas con delta de confianza (`pass1/pass2`), `confidence_by_subclaim`, contabilidad de tokens formal (`TokenUsage` con embeddings), citas estructuradas, el `Plan` condicional de M3, migrar `run_held_out.py` al run model, y los artefactos de `path_b` fuera del árbol (§5.2). El worker es in-process (un solo contenedor); una cola cross-proceso solo si el volumen la exige (prueba pequeño).
- Deploy: el servicio necesita `ANTHROPIC_API_KEY` en su Environment de Dokploy (compose actualizado); `init_db()` crea las tablas nuevas en el arranque (aditivo).

## Verification (offline, deterministic)

`smoke_run_pipeline.py` → **19/19 PASS** (2026-08-09): e2e queued→running→awaiting_closure→closed con seq monotónico y eventos por etapa · registro congelado completo (contrato, audit, `store_at_retrieval`, identidad, `question_matches_run`) · latido expuesto · cancel inmediato (queued) y en vuelo (frontera de etapa) sin disfrazarse de failed · fallo honesto con error registrado · close único (409 al doble). SQLite tmp, panel/síntesis/backend stubbeados — cero red, cero spend, cero mutación DI. Gates re-corridos: `smoke_query_service` 20/20 · `smoke_degraded_envelope` 17/17.
