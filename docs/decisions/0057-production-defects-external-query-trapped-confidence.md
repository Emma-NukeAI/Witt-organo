# ADR-0057 — Defectos de producción de las dos corridas reales: la Ruta B buscaba en español (0 papers) y la confianza viajaba atrapada como texto (LOTE-03)

- **Status:** Accepted — brief `witt-webapp/docs/LOTE-BACKEND-03.md` (2026-08-16, tras el estreno de `witt-ai.com.mx`). Prioridad sobre features por instrucción de Emmanuel. Hallazgos 1 y 2 verificados antes de tocar (el 1 EN VIVO: `ES: 0 · EN: 3 · ENT: 3` contra Europe PMC); el 3 queda como **decisión de Emmanuel pendiente**; el 4 se registra como medición.
- **Relates:** ADR-0051 (el retry que corría pero no veía esta forma; el decisor por confianza que el hallazgo 4 confirma), ADR-0022 (never-stopper), CLAUDE.md §5 (el contrato dice `confidence` **OR** `confidence_by_subclaim` — la base del punto 2b), corridas `a361f566` (contrato 1.0) y `99986dbb` (contrato 1.1, AUDIT_REJECTED, USD 0.1558).
- **Affects:** `analysis/scripts/lib/{composite_auditor,answer_pipeline}.py` · `rag_index/query_service/runs.py` (`render_contract_version` 1.1→**1.2**). **Cero mutación DI.**

## Hallazgo 1 [ALTA] — La Ruta B enviaba la pregunta en ESPAÑOL verbatim a un índice en inglés

Verificado en vivo: la pregunta ES devuelve **0** resultados; keywords EN, **3**; entidades, **3**. La Ruta B estaba estructuralmente rota para el idioma del equipo, y "busqué mal" era indistinguible de "no hay nada".

**Fix:** (a) `build_external_query(question, entities)` — regla determinista: **entidades resueltas (símbolos EN, la señal más fuerte) primero; pregunta cruda solo como último recurso**, con la fuente declarada. (b) En el camino conf-gated, prioridad al **`search_query_en` del sintetizador** (campo nuevo del tool: keywords EN que el modelo emite incluso al declinar). (c) `path_b(query=…)` explícito, y **lo efectivamente enviado queda AUDITABLE**: `path_b.query_sent` + `query_source` (`synthesizer | entities | question-verbatim`) + `n_results_by_source`, en el bundle Y en el evento `stage.path_b`.

## Hallazgo 2 [ALTA] — `stated_confidence` no estaba ausente: estaba ATRAPADA como texto

2/2 corridas reales: `direct_answer` terminaba en `…</parameter>\n<parameter name="confidence">0.15` — el valor existía, el campo llegaba None, el retry corría y el modelo repetía el patrón, la prosa del médico terminaba en basura de serialización.

**Decisión: RECUPERACIÓN con procedencia declarada, jamás silenciosa** (el precedente de la casa: el regex de confianza fugada de ADR-0037 en el harness). `composite_auditor.recover_trapped_params()` — determinista, genérico para cualquier tool call, corre ANTES del required-check (no quema el retry): corta el artefacto del string (la prosa queda limpia), levanta los valores atrapados SOLO a campos ausentes, y lista lo recuperado en `_recovered_fields`. La procedencia viaja hasta el registro: **`confidence.source ∈ {stated, recovered-from-malformed-tool-call, derived-min-of-subclaims, null}`** (+`pass1_source`/`pass2_source`, +`fb_meta.pass1_confidence_source`) — un valor recuperado es un valor, nunca una medición limpia.

**2b — El escalar ya no es forzado cuando hay `by_subclaim`** (la hipótesis del descarrilamiento: el modelo evita promediar sub-claims asimétricos — justo lo que §5 prohíbe; y §5 mismo dice `confidence` OR `by_subclaim`): con `by_subclaim` presente y escalar ausente, el gate deriva **min-of-subclaims** (worst-of, la regla de agregación de la casa; conservador para el never-stopper) — declarado como `derived-min-of-subclaims`. Ausente de verdad = ni escalar ni subclaims.

## Hallazgo 3 [MEDIA] — **DECISIÓN DE EMMANUEL, PENDIENTE** (no se implementó nada)

Las dos corridas reales terminaron `AUDIT_REJECTED` por declinar honestamente ante ausencia de evidencia (gpt-4o: *"critiques the lack of evidence instead of deriving conclusions"*). Si es sistemático, todo hallazgo negativo nace objetado. Opciones planteadas (registradas aquí; la decisión se anota al tomarse): (a) instruir a las lentes que una declinación honesta con `absence_kind` declarado se juzga por si declinar era CORRECTO dada la evidencia; (b) distinguir en vocabulario *claim rechazado* vs *declinación correcta*; (c) dejar el veredicto como está y que la UI distinga por `absence_kind`+`gap_flags`.

## Hallazgo 4 [BAJA] — Medición registrada, no bug

`99986dbb`: `assess_sufficiency` dijo "suficiente" (any-chunk-present) y el decisor por confianza disparó la Ruta B de todos modos — ADR-0051 funcionando exactamente como se diseñó, segunda confirmación en vivo de la debilidad estructural documentada. Va a la calibración como evidencia; sin cambio de código.

## Consequences

- Los registros ya congelados (1.0/1.1) conservan su artefacto verbatim — inmutables, como debe ser; el fix aplica a corridas nuevas (contrato 1.2).
- La UI renderiza `confidence.source` con render propio para `recovered-…` y `derived-…` (el brief lo exigió: recuperado ≠ medición limpia).
- Residual honesto: `search_query_en` depende de que el modelo lo emita; el fallback determinista (entidades) siempre existe y todo queda auditado.

## Verification (offline, deterministic + live)

En vivo: `ES: 0 / EN: 3 / ENT: 3` (2026-08-16, pre-fix, confirma el hallazgo 1). Gates: `smoke_run_pipeline` **41/41** (+6: recuperación del artefacto EXACTO de producción · salida limpia intacta · procedencia en registro y fb_meta · derived-min con gate en 0.05 y final stated · build_external_query · query del sintetizador auditable en evento) · `smoke_query_service` 29/29 · `smoke_ingest_gate` 22/22 · `smoke_precedent` 15/15 · `smoke_degraded_envelope` 17/17 · coherencia 7/7.
