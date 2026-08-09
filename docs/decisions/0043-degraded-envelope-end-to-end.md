# ADR-0043 — El marcador `degraded` viaja en un SOBRE `{degraded, n_hits, hits}` de punta a punta (y el bundle carga un enum de 4 literales, nunca nullable)

- **Status:** Accepted — autorizado por Emmanuel en sesión 2026-08-09 ("arranquemos con esto"), como parte del paquete de correcciones pre-UI derivado del handoff de la webapp (2026-08-04, `witt-ui-lab/05-backend/`).
- **Relates:** ADR-0039/0040 (el marcador `degraded` in-band nació del incidente 2026-07-18/19: sparse-disfrazado-de-semántico), CLAUDE.md §6 (no-hang), el contrato del docstring de `HitList` ("consumers MUST surface a non-None marker").
- **Affects:** `rag_index/mcp_server/server.py` (`_query`, tool MCP `query_data_inamovible`, warmup) · `rag_index/mcp_server/cli.py` (`_cmd_query`, `_cmd_health`; se elimina `_degraded_of`) · `analysis/scripts/lib/answer_pipeline.py` (`path_a.retrieval`, `retrieve().retrieval_summary`) · `rag_index/mcp_server/smoke_rag.py` (asserts al nuevo contrato) · **NUEVO** gate `rag_index/mcp_server/smoke_degraded_envelope.py`. **Cero mutación de la DATA INAMOVIBLE** (código de lectura/serialización únicamente).

## Context

La verificación del 2026-08-09 (fase 1 del trabajo de backend pre-webapp) confirmó tres capas del mismo defecto:

1. **`answer_pipeline` tiraba el marcador**: `grep degraded answer_pipeline.py` = 0 ocurrencias. `path_a` serializaba solo `doc_id/type/score/text`; `HitList.degraded` moría ahí, violando el contrato explícito del docstring de `HitList`.
2. **Con 0 hits el marcador se perdía en `server._query`**: se estampaba iterando los hits (`_hit_dicts`); con lista vacía el `for` no entra. "Degradado y vacío" quedaba byte-idéntico a "sano y vacío" — conclusiones opuestas (hueco real de la DI que dispara Ruta B/aprendizaje vs. buscador roto que es un incidente).
3. **El sobre del CLI heredaba el mismo hueco**: `cli._degraded_of` derivaba el marcador de la metadata *por hit*, así que `{degraded, hits}` en `cli.py` también reportaba `null` con 0 hits degradados. (Matiz no detectado por el handoff de la UI, encontrado en la verificación.)

Además, un `degraded: null` es ambiguo para cualquier consumidor: no distingue "se midió y está limpio" de "no se midió", y la regla de derivación de la UI obliga a pintar el peor caso.

## Decision

**(a) Sobre uniforme en `server._query`, fuente única del marcador.** `_query` devuelve SIEMPRE un dict `{degraded, n_hits, hits}`; el marcador se toma de `HitList.degraded` (nunca re-derivado de metadata por hit) y sobrevive `n_hits == 0` por construcción. La ruta de error conserva su llave `error` y gana `degraded: "unavailable"`, `n_hits: 0`. El estampado por-hit se **conserva** por compatibilidad, pero el sobre es la fuente de verdad. Vocabulario crudo del sobre: `None | 'dense-failed:sparse-only' | 'sparse-by-config' | 'sparse' | 'unavailable'`.

**(b) La tool MCP `query_data_inamovible` devuelve el sobre.** Cambio de forma de retorno (antes: lista cruda). Es tolerable porque `_query` ya podía devolver dict en la ruta de error — todo consumidor correcto ya manejaba ambas formas — y porque dejar el hueco de 0-hits abierto en una sola superficie reintroduce el trap. **Consecuencia a coordinar: MITAD_B (`conciencia-universal`) lee la DI vía este MCP; hay que avisarle del cambio de forma** (su contrato A/B). El MCP sigue **read-only**.

**(c) El bundle de `answer_pipeline` carga el estado epistémico como enum de 4 literales, NUNCA nullable.** `path_a` emite `retrieval: {mode, raw_marker, n_hits, k_requested}` con `mode ∈ RETRIEVAL_MODES = (semantic | degraded-dense-failed | reduced-by-config | not-measured)`:
  - `semantic` ← marcador `None` (medición ocurrió, limpia)
  - `degraded-dense-failed` ← `'dense-failed:sparse-only'`, `'sparse'` (timeout-fallback del server) y **cualquier marcador truthy desconocido** (degradado-de-algún-modo jamás se pinta limpio)
  - `reduced-by-config` ← `'sparse-by-config'`
  - `not-measured` ← el resultado no traía atributo `degraded` (sentinela `_MARKER_MISSING`)
  `raw_marker` conserva el literal original sin traducir.

**(d) Agregado a nivel corrida: `retrieval_summary` worst-of-N declarado.** `{mode, retrievals, aggregation: "worst-of-n"}` — agregar por "el primero" o "mayoritario" pinta limpia una corrida que degradó a la mitad. Severidad: `semantic < reduced-by-config < not-measured < degraded-dense-failed`.

**(e) Gate determinista permanente:** `smoke_degraded_envelope.py` (12 checks, 100% offline por monkeypatch, cero red/spend) fuerza el fallo del denso, consulta con 0 hits y afirma que el sobre reporta degradado — en server, pipeline y CLI (exit-codes: degradado+vacío→3, sano+vacío→4, error→4). `smoke_rag.py` (el gate 6/6 live) actualizado al nuevo contrato.

## Consequences

- El criterio de aceptación del tapón 1 del handoff se cumple: `grep degraded answer_pipeline.py` > 0 y el bundle carga `retrieval.mode` con 4 literales explícitos; el del tapón 2 también (smoke de 0 hits).
- La capa HTTP futura (`query_service`, bloque 2) espejará **este** sobre — cambio de transporte, no semántica nueva.
- `_degraded_of` eliminado del CLI: nadie vuelve a derivar el marcador desde los hits.
- Residual honesto: los exit-codes del CLI conservan la conflación documentada `sano-vacío = 4 = unavailable` (contrato de exit codes intacto en esta corrección; el JSON del sobre sí los distingue — `degraded: null` + `n_hits: 0` vs. llave `error`).
- Residual honesto: `HybridRetriever.last_error` sigue solo en el log de archivo; subirlo al sobre ("Neo4j inalcanzable" vs. "degradado" genérico) queda para el bloque 1.4 del plan.

## Verification (offline, deterministic)

- `python rag_index/mcp_server/smoke_degraded_envelope.py` → **12/12 PASS** (2026-08-09).
- `smoke_rag.py` (6/6, live) re-corrido al cierre de la sesión — requiere Neo4j/OpenAI vivos.
