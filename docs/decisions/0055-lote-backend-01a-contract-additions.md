# ADR-0055 — LOTE BACKEND 01·A: adiciones de contrato reportadas por la webapp (M1–M3 construidos)

- **Status:** Accepted — ejecutado 2026-08-15 sobre el brief `witt-webapp/docs/LOTE-BACKEND-01.md` (la sesión constructora verificó cada gap contra el código vivo; esta sesión re-verificó 8/8 antes de tocar — la regla de verificación bidireccional funcionó en ambas direcciones). Continuación natural de ADR-0048 (superficie) y ADR-0050/0051 (run model / registro).
- **Relates:** ADR-0048/0050/0051 · registro-congelado.md (regla ERP: "registro de absolutamente todo" — cancelaciones con autor, el catálogo tiene historia) · ADR-0018 (taxonomía congelada human-gated) · ADR-0032 (`store_integrity_scan.py`).
- **Affects:** `rag_index/query_service/{app,db,runs}.py` (+migración aditiva de columnas — el Postgres vivo ya tenía `runs`) · **NUEVO** `rag_index/config_history.json` (append-only, fechas de ADRs). **Cero mutación DI.** El LOTE B del brief NO se ejecuta aquí (cada pieza con su módulo).

## Decisions (los 8 puntos del LOTE A)

1. **`GET /runs` (lista) pasa por `_run_view`** — latido, umbral, autoría de cancelación, `token_usage` y serialización de fechas idénticos al detalle. Una corrida atorada se distingue desde la lista.
2. **El umbral del latido viaja**: `heartbeat_stale_after_s` en toda vista de corrida (un aviso sin umbral no se puede juzgar).
3. **Cancelación con autoría**: body `{reason}` en `POST /runs/{id}/cancel`; `cancelled_by` = usuario de sesión + `cancel_reason` persistidos (columnas nuevas) y en el evento `run.cancel_requested`.
4. **El gasto sobrevive a todo camino de salida**: `usage_json` se escribe en éxito, `failed` y `cancelled` (acumulación parcial de pasadas + panel + embeddings); la API lo sirve parseado como `token_usage`. M8 cuadra: "lo gastado antes de morir" existe.
5. **`POST /runs` bloquea server-side con el índice OFFLINE**: 409 `{state: "index_offline", note, status_error}` por el mismo camino NO-SPEND del `/status` — "bloquea, no degrada" es estructura, no disciplina de UI. Override documentado para el loop local sparse-dev: `WITT_ALLOW_RUNS_OFFLINE=1`.
6. **`GET /taxonomia`** (read-only, TTL): `niches.json` + `databases.json` + `niche_database_crosswalk.json` servidos verbatim con **procedencia declarada** (ruta repo + mtime) — la única puerta; la UI no copia archivos (drift).
7. **Los ejes por entidad NUNCA van por `/resolve` — declarado, no silencio**: `taxonomy_axes: {served: false, why}` en cada respuesta. El store verificado es identidad+procedencia; nicho/dominio por entidad deriva del grafo (MENTIONS) — la operación browse (Rack fase 2, LOTE B).
8. **`/status` gana dos campos**: `integrity` (del artefacto real `analysis/outputs/store_integrity_scan_latest.json` por convención `--json`; sin artefacto → `scanned: false` declarado — un escaneo ausente jamás se pinta limpio) y `embed_model_changed_at` (de `rag_index/config_history.json`, append-only, fechas con fuente ADR — "el único caso en que un score viejo miente" ya es advertible). El docstring/README que decían 9 campos sirviendo 10 quedaron corregidos; README 19/19 → 32/32.

**Decisión de Emmanuel (2026-08-15, Método 2 — el único punto de producto del brief): `/status` se queda CON auth.** No hay puerta pública ni `/status-lite`: ninguna superficie del backend responde sin sesión. Consecuencia para la UI: el cintillo pre-login del boceto M1 no puede esperar estado del store antes del login — se rediseña a estado post-login (o a un indicador local de la propia webapp), y esa adaptación es del lado de `witt-webapp`.

## Consequences

- Migración aditiva idempotente en `db.init_db()` (`ALTER TABLE runs ADD COLUMN …` con skip silencioso) — el autodeploy la aplica al Postgres vivo sin intervención; additive-only por política.
- Los tipos exactos campo-por-campo van en el reporte de cierre a la sesión de la webapp (retira sus placas de gap con eso).
- Residual: `integrity.scanned` será `false` hasta que el escaneo corra con `--json` a la ruta convenida (correrlo es barato y read-only; queda como paso operativo, no de código).

## Verification (offline, deterministic)

`smoke_run_pipeline.py` → **32/32** (+5: lista con latido/umbral/usage · 409 OFFLINE sin override · cancel con autor+razón · usage visible en cancelled (100/50 de pass1) y en failed (0 medido, no ausente)) · `smoke_query_service.py` → **25/25** (+5: integrity honesto · embed_model_changed_at=2026-06-12 · /taxonomia con procedencia + 401 · taxonomy_axes declarado) · `smoke_precedent.py` 15/15 · coherencia 7/7.
