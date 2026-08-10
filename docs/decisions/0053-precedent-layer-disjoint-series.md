# ADR-0053 — La capa de precedente: índice separado, admisibilidad distinta, series de citas disjuntas por construcción (bloque 6)

- **Status:** Accepted — bloque 6 del plan webapp, ejecutado 2026-08-10.
- **Relates:** decisión del handoff "precedente y evidencia: índices separados, admisibilidad distinta, valor equivalente" · ADR-0050 (cierre explícito = requisito para ser precedente) · handoff §2.4/§2.5 · la corrección del handoff sobre `verify_output` (es ciego a la procedencia — verificado en fase 1).
- **Affects:** **NUEVO** `rag_index/query_service/precedent.py` · `db.py` (+`closed_runs()`) · `app.py` (+`GET /precedent/search`). **Cero mutación DI.**

## Context

No existía capa de precedente (cero ocurrencias en código; lo único vecino era `resolve_id.lookup_prior`, que devuelve identificadores, no corridas). Y la justificación original del diseño de la UI era falsa: *"verify_output rechaza identificadores por venir de bitácora"* — el gate es **ciego a la procedencia** (un ENSDARG copiado de la bitácora pasa si resuelve). Por lo tanto `admissible_as_evidence: false` **no es un veredicto heredable del gate: es una decisión de producto** que el pipeline impone estructuralmente.

## Decision

1. **`PrecedentItem` = corrida CERRADA** (`state=closed`, `frozen_at` estampado — el cierre explícito de ADR-0050 es literalmente el requisito). Campos: `run_id`, `question`, `frozen_at`, `closed_by`, `verdict`, `decision_state`, `confidence_final`, `answer_excerpt`, `score`.
2. **Recuperación por relevancia** (*prueba pequeño*): TF-IDF sobre pregunta+respuesta de corridas cerradas (sklearn — ya precargado en main thread en el servicio); fallback determinista por token-overlap cuando sklearn no está. **El scorer usado se DECLARA siempre en la respuesta** (`scorer: sparse-tfidf | token-overlap-fallback`) — un fallback jamás se disfraza del camino semántico (la disciplina ADR-0039/0043 aplicada aquí). Score 0 se filtra: el ranking no rellena con ruido. Índice cacheado por (n_cerradas, última frozen_at); embeddings semánticos solo si el recall del sparse resulta insuficiente con corpus real.
3. **`admissible_as_evidence: false` ESTRUCTURAL** en cada item + `why_not_admissible`: el precedente informa a humanos y a la planeación; **su texto jamás entra al objeto de evidencia gateado** por ninguna etapa del pipeline. La regla vive en el producto porque el gate anti-fabricación no puede verla.
4. **Series de citas disjuntas POR CONSTRUCCIÓN** (§2.5): evidencia = números (`runs.py`, bloque 4); precedente = **letras** (`letter_label`: A…Z, AA…). `serialize_disjoint()` produce ambas series; `validate_disjoint()` es el chequeo determinista que rechaza una letra colada en la serie de evidencia (y viceversa) — estructura, no disciplina.
5. **`GET /precedent/search?q=&k=`** (auth) — la mitad de la tesis que faltaba en la superficie: evidencia y precedente como índices separados con valor equivalente.

## Consequences

- M6 (bitácora/precedente) tiene su índice; el `Plan` de M3 podrá citar precedente con letras sin poder lavarlas como evidencia.
- Residuales honestos: las corridas aún no CONSUMEN precedente en la síntesis (cuando lo hagan, `serialize_disjoint` + `validate_disjoint` ya son el contrato); el scorer es sparse (embeddings = mejora futura gateada por recall real); `n_closed_runs` hoy = 1 en producción (crece con el uso — como debe).

## Verification (offline, deterministic)

`smoke_precedent.py` → **15/15 PASS** (2026-08-10): índice vacío honesto · solo `closed` es precedente (`awaiting_closure` NO) · relevancia rankea wt1a primero · scorer declarado · `admissible_as_evidence: false` + porqué en cada item · score-0 filtrado · letras A/Z/AA · series disjuntas serializadas y VALIDADAS (rechaza letra en evidencia y número en precedente) · endpoint con 401/400. SQLite tmp, cero red/spend/mutación.
